"""Score and rank extracted candidate records against a role definition.

Pure Python, no model call: the same record and role always produce the same score,
and every point traces back to a named requirement and the CV span that satisfied it.

Usage:
    python src/score.py --records data/synthetic --top 10
    python src/score.py --records data/synthetic --explain cv_0003
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLE = ROOT / "data" / "role_ai_automation_engineer.json"

SCORABLE_FIELDS = ("years_experience", "skills", "experience", "education")
SCORABLE_EDUCATION_FIELDS = ("degree", "field", "year")


class RoleError(ValueError):
    pass


def load_role(path: Path) -> dict:
    role = json.loads(path.read_text(encoding="utf-8"))
    total = sum(r["weight"] for r in role["requirements"])
    if total != 100:
        raise RoleError(f"{path.name}: weights sum to {total}, expected 100")
    return role


def scorable_view(record: dict) -> dict:
    """Reduce a record to the fields a score may depend on.

    An allow-list, not a deny-list: a field that is not named here cannot reach the
    scorer at all, so no future edit can accidentally make a score depend on a name,
    a contact detail, a location, or an institution."""
    view = {field: record.get(field) for field in SCORABLE_FIELDS}
    education = view.get("education")
    if isinstance(education, dict):
        view["education"] = {k: education.get(k) for k in SCORABLE_EDUCATION_FIELDS}
    return view


def _skills(view: dict) -> list[tuple[str, str | None]]:
    """Normalise skills to (name, evidence). Extraction emits objects with an evidence
    span; ground-truth fixtures emit plain strings."""
    pairs = []
    for skill in view.get("skills") or []:
        if isinstance(skill, dict):
            pairs.append((str(skill.get("name", "")), skill.get("evidence")))
        else:
            pairs.append((str(skill), None))
    return [(name, evidence) for name, evidence in pairs if name]


def _match(requirement: dict, skills: list[tuple[str, str | None]]) -> list[dict]:
    wanted = [w.lower() for w in requirement["accepted_evidence"]]
    held = {name.lower(): (name, evidence) for name, evidence in skills}
    return [
        {"skill": held[w][0], "evidence": held[w][1]}
        for w in wanted
        if w in held
    ]


def _score_requirement(requirement: dict, view: dict) -> dict:
    weight = requirement["weight"]
    line = {
        "requirement": requirement["id"],
        "label": requirement["label"],
        "weight": weight,
        "must_have": requirement.get("must_have", False),
        "awarded": 0.0,
        "matched": [],
        "reason": "",
    }

    kind = requirement["type"]

    if kind in ("skill", "skill_any_of"):
        matched = _match(requirement, _skills(view))
        line["matched"] = matched
        needed = len(requirement["accepted_evidence"]) if kind == "skill" else 1
        if len(matched) >= needed:
            line["awarded"] = float(weight)
            line["reason"] = "satisfied by " + ", ".join(m["skill"] for m in matched)
        else:
            line["reason"] = (
                "not stated: none of " + ", ".join(requirement["accepted_evidence"])
                if not matched
                else f"needs all of {requirement['accepted_evidence']}, found only "
                     + ", ".join(m["skill"] for m in matched)
            )
        return line

    if kind == "years":
        years = view.get("years_experience")
        target = requirement["target_years"]
        if years is None:
            line["reason"] = "years of experience not stated"
            return line
        ratio = min(float(years) / target, 1.0) if target else 1.0
        line["awarded"] = round(weight * ratio, 2)
        line["reason"] = f"{years} of {target} target years"
        return line

    raise RoleError(f"unknown requirement type: {kind}")


def score(record: dict, role: dict) -> dict:
    view = scorable_view(record)
    breakdown = [_score_requirement(r, view) for r in role["requirements"]]
    awarded = round(sum(line["awarded"] for line in breakdown), 2)

    return {
        "cv_id": record.get("cv_id"),
        "role_id": role["role_id"],
        "score": awarded,
        "max_score": 100,
        "unmet_must_haves": [
            line["requirement"] for line in breakdown
            if line["must_have"] and line["awarded"] == 0
        ],
        "breakdown": breakdown,
    }


def rank(records: list[dict], role: dict) -> list[dict]:
    """Rank highest first. Ties break on cv_id so the order is reproducible."""
    scored = [score(record, role) for record in records]
    return sorted(scored, key=lambda s: (-s["score"], s["cv_id"] or ""))


def load_records(directory: Path) -> list[dict]:
    files = sorted(p for p in directory.glob("cv_*.json"))
    if not files:
        raise SystemExit(f"no cv_*.json records in {directory}")
    records = []
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        record.setdefault("cv_id", path.stem)
        records.append(record)
    return records


def audit_rubric(ranking: list[dict], role: dict) -> dict:
    """Measure whether the rubric separates candidates, rather than assuming it does.

    A requirement awarded to every candidate carries no information: its weight is
    spent identically on everyone and only inflates scores. A ranking whose top is a
    large tie is ordered by the tie-break, not by the rubric."""
    total = len(ranking)
    scores = [r["score"] for r in ranking]
    top = max(scores) if scores else 0

    rates = []
    for requirement in role["requirements"]:
        awards = [
            line["awarded"] for r in ranking for line in r["breakdown"]
            if line["requirement"] == requirement["id"]
        ]
        # A requirement discriminates when it awards different amounts to different
        # candidates. Counting "scored above zero" is the wrong test for a curve-scored
        # requirement — partial credit means almost everyone scores above zero while the
        # requirement may still separate them perfectly well.
        modal_share = max(awards.count(v) for v in set(awards)) / total if awards else 1.0
        rates.append({
            "requirement": requirement["id"],
            "label": requirement["label"],
            "weight": requirement["weight"],
            "award_rate": round(sum(1 for a in awards if a > 0) / total, 3) if total else 0,
            "distinct_awards": len(set(awards)),
            "modal_share": round(modal_share, 3),
            "discriminates": modal_share < 0.95,
        })

    return {
        "candidates": total,
        "distinct_scores": len(set(scores)),
        "top_score": top,
        "tied_at_top": sum(1 for s in scores if s == top),
        "dead_weight": sum(r["weight"] for r in rates if not r["discriminates"]),
        "requirements": rates,
    }


def format_audit(audit: dict) -> str:
    lines = [
        f"candidates       {audit['candidates']}",
        f"distinct scores  {audit['distinct_scores']}",
        f"tied at top      {audit['tied_at_top']} at {audit['top_score']}",
        f"dead weight      {audit['dead_weight']} of 100 points score everyone the same",
        "",
        "  held  levels  same   weight  requirement",
    ]
    for row in audit["requirements"]:
        mark = " " if row["discriminates"] else "!"
        lines.append(
            f"{mark} {row['award_rate']:>4.0%}  {row['distinct_awards']:>6}"
            f"  {row['modal_share']:>4.0%}  {row['weight']:>6}   {row['label']}"
        )
    lines += [
        "",
        "  held   = share scoring above zero",
        "  levels = distinct award values",
        "  same   = share receiving the most common award  (95%+ is dead weight)",
    ]
    return "\n".join(lines)


def format_explanation(result: dict) -> str:
    lines = [
        f"{result['cv_id']} — {result['score']} / {result['max_score']}",
        "",
    ]
    for line in result["breakdown"]:
        flag = " (must-have)" if line["must_have"] else ""
        lines.append(f"  {line['awarded']:>6.2f} / {line['weight']:<3} {line['label']}{flag}")
        lines.append(f"         {line['reason']}")
        for match in line["matched"]:
            if match["evidence"]:
                lines.append(f"         evidence: \"{match['evidence']}\"")
    if result["unmet_must_haves"]:
        lines += ["", "  unmet must-haves: " + ", ".join(result["unmet_must_haves"])]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score and rank candidate records.")
    parser.add_argument("--records", type=Path, default=ROOT / "data" / "synthetic",
                        help="directory of cv_*.json records")
    parser.add_argument("--role", type=Path, default=DEFAULT_ROLE)
    parser.add_argument("--top", type=int, default=10, help="how many to list")
    parser.add_argument("--explain", help="cv_id to show a full breakdown for")
    parser.add_argument("--audit", action="store_true",
                        help="report whether the rubric actually separates candidates")
    parser.add_argument("--json", action="store_true", help="emit the ranking as JSON")
    args = parser.parse_args()

    role = load_role(args.role)
    records = load_records(args.records)
    ranking = rank(records, role)

    if args.audit:
        print(format_audit(audit_rubric(ranking, role)))
        return

    if args.explain:
        result = next((r for r in ranking if r["cv_id"] == args.explain), None)
        if result is None:
            raise SystemExit(f"no record with cv_id {args.explain}")
        print(format_explanation(result))
        return

    if args.json:
        print(json.dumps(ranking[:args.top], indent=2, ensure_ascii=False))
        return

    from decisions import apply_overrides
    ranking = apply_overrides(ranking)

    print(f"{role['title']} — {len(records)} candidates, top {args.top}\n")
    for position, result in enumerate(ranking[:args.top], start=1):
        notes = []
        if result["unmet_must_haves"]:
            notes.append("⚠ " + ",".join(result["unmet_must_haves"]))
        if result["decision"]:
            notes.append(f"[{result['decision']} by {result['decided_by']}]")
        if result["score_moved_since"]:
            notes.append(f"score was {result['score_at_decision']} when decided")
        suffix = "  " + "  ".join(notes) if notes else ""
        print(f"{position:>3}. {result['cv_id']}  {result['score']:>6.2f}{suffix}")

    decided = sum(1 for r in ranking if r["decision"])
    if decided:
        print(f"\n{decided} of {len(ranking)} candidates have a recorded decision "
              f"(src/decisions.py --list)")


if __name__ == "__main__":
    main()
