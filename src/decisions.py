"""Recruiter decisions and the audit trail behind them.

The pipeline ranks; a person decides. Every decision is appended to a log that is never
rewritten, so the record of what was decided — and what the pipeline was saying at the
time — survives later changes to the rubric, the model, or the code.

Usage:
    python src/decisions.py --list
    python src/decisions.py --cv cv_0003 --decision advance --actor recruiter@example.com \
        --reason "career changer; claims handling background is relevant"
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from config import load_env
from score import load_records, load_role, rank

load_env()

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "decisions.jsonl"

DECISIONS = ("advance", "reject", "hold")


class DecisionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(cv_id: str, decision: str, actor: str, reason: str,
           scored: dict | None = None, log: Path = LOG,
           idempotency_key: str | None = None) -> dict:
    """Append one decision. Existing entries are never modified — a change of mind is a
    new entry, which is what makes the log an audit trail rather than a status field.

    `idempotency_key` makes a retry safe. Without one, a caller that retries after a
    timeout appends a second entry, and nothing downstream can tell that duplicate from a
    genuine repeated decision — an append-only log cannot infer intent. Supplying a key
    moves that judgement to the caller, which is the only place it exists."""
    if idempotency_key:
        for entry in load(log):
            if entry.get("idempotency_key") == idempotency_key:
                return entry

    if decision not in DECISIONS:
        raise DecisionError(f"decision must be one of {DECISIONS}, got {decision!r}")
    if not reason.strip():
        raise DecisionError("a reason is required: an override with no stated reason is "
                            "not reviewable")
    if not actor.strip():
        raise DecisionError("an actor is required: a decision with no author cannot be audited")

    entry = {
        "recorded_at": _now(),
        "cv_id": cv_id,
        "decision": decision,
        "actor": actor,
        "reason": reason.strip(),
        # The score is snapshotted, not referenced. Weights change, models change, code
        # changes — without the value as it stood, a past decision cannot be reconstructed
        # and "the pipeline said 80" becomes unverifiable.
        "pipeline": {
            "score": scored.get("score") if scored else None,
            "role_id": scored.get("role_id") if scored else None,
            "unmet_must_haves": scored.get("unmet_must_haves") if scored else None,
            "model": os.environ.get("LLM_MODEL"),
        },
        "idempotency_key": idempotency_key,
    }

    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load(log: Path = LOG) -> list[dict]:
    if not log.exists():
        return []
    return [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def latest_by_cv(log: Path = LOG) -> dict[str, dict]:
    """The effective decision per candidate: the most recent entry wins, while every
    superseded entry stays in the log."""
    effective: dict[str, dict] = {}
    for entry in load(log):
        effective[entry["cv_id"]] = entry
    return effective


def apply_overrides(ranking: list[dict], log: Path = LOG) -> list[dict]:
    """Attach the effective decision to each ranked candidate.

    Overrides annotate the ranking; they do not silently reorder it. A recruiter who
    advances a low-scoring candidate should see both the score and their own decision,
    not a reshuffled list that hides the disagreement."""
    effective = latest_by_cv(log)
    annotated = []
    for result in ranking:
        entry = effective.get(result["cv_id"])
        annotated.append({
            **result,
            "decision": entry["decision"] if entry else None,
            "decided_by": entry["actor"] if entry else None,
            "decided_at": entry["recorded_at"] if entry else None,
            "decision_reason": entry["reason"] if entry else None,
            "score_at_decision": entry["pipeline"]["score"] if entry else None,
            "score_moved_since": (
                entry is not None
                and entry["pipeline"]["score"] is not None
                and entry["pipeline"]["score"] != result["score"]
            ),
        })
    return annotated


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and inspect recruiter decisions.")
    parser.add_argument("--cv", help="cv_id to decide on")
    parser.add_argument("--decision", choices=DECISIONS)
    parser.add_argument("--actor", default=os.environ.get("DECISION_ACTOR", ""))
    parser.add_argument("--reason", default="")
    parser.add_argument("--key", help="idempotency key: re-running with the same key is a no-op")
    parser.add_argument("--list", action="store_true", help="show the audit trail")
    parser.add_argument("--records", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--role", type=Path,
                        default=ROOT / "data" / "role_ai_automation_engineer.json")
    args = parser.parse_args()

    if args.list:
        entries = load()
        if not entries:
            print(f"no decisions recorded yet ({LOG})")
            return
        print(f"{len(entries)} entries in {LOG.name}\n")
        for entry in entries:
            score = entry["pipeline"]["score"]
            print(f"  {entry['recorded_at']}  {entry['cv_id']:<9} "
                  f"{entry['decision']:<8} score {score}  by {entry['actor']}")
            print(f"      {entry['reason']}")
        superseded = len(entries) - len(latest_by_cv())
        if superseded:
            print(f"\n  {superseded} entries superseded by a later decision "
                  f"(retained — the log is append-only)")
        return

    if not (args.cv and args.decision):
        raise SystemExit("need --cv and --decision, or --list")

    role = load_role(args.role)
    ranking = rank(load_records(args.records), role)
    scored = next((r for r in ranking if r["cv_id"] == args.cv), None)
    if scored is None:
        raise SystemExit(f"no record with cv_id {args.cv} in {args.records}")

    before = len(load())
    try:
        entry = record(args.cv, args.decision, args.actor, args.reason, scored,
                       idempotency_key=args.key)
    except DecisionError as error:
        raise SystemExit(f"refused: {error}")

    verb = "recorded" if len(load()) > before else "already recorded (idempotent no-op)"
    print(f"{verb}: {entry['cv_id']} {entry['decision']} "
          f"(pipeline score {entry['pipeline']['score']}) by {entry['actor']}")


if __name__ == "__main__":
    main()
