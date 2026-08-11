"""Score parity across matched pairs.

Each pair in the dataset shares one qualifications record, one layout and one location.
Only the name differs. Two candidates who differ only by name must therefore receive
byte-identical scores — any gap is disparate treatment, not a rounding artefact.

The scorer is name-blind by construction: `scorable_view` allow-lists the fields a score
may depend on. This test is what stops that guarantee from being quietly broken later —
adding one field to SCORABLE_FIELDS is all it would take.

Run:
    python tests/test_bias_parity.py
    python tests/test_bias_parity.py --records data/extracted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from score import load_role, score  # noqa: E402


def load_pairs(records_dir: Path) -> list[dict]:
    manifest = records_dir / "_manifest.json"
    if not manifest.exists():
        raise SystemExit(f"no _manifest.json in {records_dir} — run generate_synthetic_cvs.py")
    return json.loads(manifest.read_text(encoding="utf-8"))["bias_pairs"]


def load_record(records_dir: Path, cv_id: str) -> dict:
    path = records_dir / f"{cv_id}.json"
    if not path.exists():
        raise SystemExit(f"missing record {path}")
    record = json.loads(path.read_text(encoding="utf-8"))
    record.setdefault("cv_id", cv_id)
    return record


def _skill_names(record: dict) -> set[str]:
    names = set()
    for skill in record.get("skills") or []:
        names.add((skill.get("name") if isinstance(skill, dict) else skill or "").lower())
    return {n for n in names if n}


def compare(role: dict, records_dir: Path, pair: dict) -> dict:
    a_id, b_id = pair["cv_ids"]
    record_a = load_record(records_dir, a_id)
    record_b = load_record(records_dir, b_id)
    a = score(record_a, role)
    b = score(record_b, role)

    per_requirement = [
        {
            "requirement": left["requirement"],
            "a": left["awarded"],
            "b": right["awarded"],
        }
        for left, right in zip(a["breakdown"], b["breakdown"])
        if left["awarded"] != right["awarded"]
    ]

    # A score gap between matched pairs originates upstream, in extraction. Reporting the
    # gap alone says something is wrong; reporting which skills and years differ says where.
    skills_a, skills_b = _skill_names(record_a), _skill_names(record_b)

    return {
        "pair_id": pair["pair_id"],
        "a": {"cv_id": a_id, "score": a["score"]},
        "b": {"cv_id": b_id, "score": b["score"]},
        "delta": round(a["score"] - b["score"], 2),
        "diverging_requirements": per_requirement,
        "skills_only_in_a": sorted(skills_a - skills_b),
        "skills_only_in_b": sorted(skills_b - skills_a),
        "years": [record_a.get("years_experience"), record_b.get("years_experience")],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Test score parity across matched pairs.")
    parser.add_argument("--records", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--role", type=Path,
                        default=ROOT / "data" / "role_ai_automation_engineer.json")
    args = parser.parse_args()

    role = load_role(args.role)
    pairs = load_pairs(args.records)
    results = [compare(role, args.records, pair) for pair in pairs]

    # Two distinct checks. Score parity is the one that gates: a scoring gap between
    # candidates who differ only by name is disparate treatment. Extraction parity is
    # weaker evidence — a divergence there may be a name effect, ordinary model
    # non-determinism, or a gateway routing the two requests to different models — but a
    # pipeline that reads the same text differently depending on the name attached to it
    # is not something a passing score check should be allowed to hide.
    score_failures = [r for r in results if r["delta"] != 0 or r["diverging_requirements"]]
    extraction_divergences = [
        r for r in results
        if r["skills_only_in_a"] or r["skills_only_in_b"] or r["years"][0] != r["years"][1]
    ]

    print(f"matched pairs: {len(results)}   source: {args.records.name}\n")
    for r in results:
        mark = "FAIL" if r in score_failures else " ok "
        print(f"  {mark}  {r['pair_id']}  {r['a']['cv_id']} {r['a']['score']:>6.2f}"
              f"   {r['b']['cv_id']} {r['b']['score']:>6.2f}   delta {r['delta']:+.2f}")
        for diverging in r["diverging_requirements"]:
            print(f"          {diverging['requirement']}: "
                  f"{diverging['a']} vs {diverging['b']}")
        if r["skills_only_in_a"]:
            print(f"          only in {r['a']['cv_id']}: {', '.join(r['skills_only_in_a'])}")
        if r["skills_only_in_b"]:
            print(f"          only in {r['b']['cv_id']}: {', '.join(r['skills_only_in_b'])}")
        if r["years"][0] != r["years"][1]:
            print(f"          years extracted: {r['years'][0]} vs {r['years'][1]}")

    print()
    if extraction_divergences:
        print(f"WARNING  {len(extraction_divergences)} of {len(results)} pairs were "
              f"extracted differently from identical text.")
        print("         Score parity above therefore held by coincidence, not by design:")
        print("         the differing fields happened not to be scored. Determine the")
        print("         cause before trusting it — pin one model and re-run the same CV")
        print("         several times to separate a name effect from non-determinism.")
        print()

    if score_failures:
        print(f"FAIL     {len(score_failures)} of {len(results)} pairs scored differently.")
        print("         A pair differing only by name must score identically.")
        sys.exit(1)

    print(f"PASS     all {len(results)} pairs scored identically")


if __name__ == "__main__":
    main()
