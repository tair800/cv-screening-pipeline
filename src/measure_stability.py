"""Measure how much extraction varies when the input does not.

A parity test across matched pairs cannot attribute a difference to the name until it
knows how much the pipeline varies on its own. Extracting one CV repeatedly establishes
that floor: any pair difference at or below it is indistinguishable from noise.

Usage:
    python src/measure_stability.py --cv cv_0011 --runs 5
    python src/measure_stability.py --cv cv_0011 --runs 5 --model aug/claude-haiku-4.5
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from extract_llm import extract

ROOT = Path(__file__).resolve().parents[1]

FIELDS = ("name", "email", "phone", "location", "years_experience")


def _skill_set(record: dict) -> frozenset[str]:
    return frozenset(
        (s.get("name") if isinstance(s, dict) else s or "").lower()
        for s in record.get("skills") or []
    ) - {""}


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure extraction variation on fixed input.")
    parser.add_argument("--cv", required=True, help="cv_id, e.g. cv_0011")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--model", help="pin a model; default is whatever LLM_MODEL resolves to")
    args = parser.parse_args()

    text = (args.source / f"{args.cv}.txt").read_text(encoding="utf-8")

    records = []
    for run in range(1, args.runs + 1):
        print(f"  run {run}/{args.runs}", file=sys.stderr, flush=True)
        try:
            records.append(extract(args.cv, text, model=args.model))
        except Exception as error:
            print(f"      failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)

    if len(records) < 2:
        raise SystemExit("need at least two successful runs to measure variation")

    skill_sets = [_skill_set(r) for r in records]
    union = frozenset().union(*skill_sets)
    stable = frozenset.intersection(*skill_sets)
    unstable = union - stable

    print(f"\ncv: {args.cv}   successful runs: {len(records)}   model: "
          f"{args.model or 'unpinned (LLM_MODEL)'}\n")

    print(f"distinct skill sets   {len(set(skill_sets))} of {len(records)}")
    print(f"skills every run found  {len(stable)}")
    print(f"skills only some runs   {len(unstable)}"
          + (f"  -> {', '.join(sorted(unstable))}" if unstable else ""))
    if unstable:
        print()
        for skill in sorted(unstable):
            hits = sum(1 for s in skill_sets if skill in s)
            print(f"    {hits}/{len(records)}  {skill}")

    print("\nscalar fields:")
    for field in FIELDS:
        values = Counter(json.dumps(r.get(field), ensure_ascii=False) for r in records)
        mark = " " if len(values) == 1 else "!"
        detail = "stable" if len(values) == 1 else " / ".join(
            f"{v}×{c}" for v, c in values.most_common())
        print(f"  {mark} {field:<18} {detail}")

    print()
    if len(set(skill_sets)) == 1 and all(
        len({json.dumps(r.get(f), ensure_ascii=False) for r in records}) == 1 for f in FIELDS
    ):
        print("Extraction is stable on fixed input. A difference across a matched pair "
              "therefore\ncannot be explained by run-to-run variation.")
    else:
        print("Extraction varies on fixed input. A matched-pair difference of this size "
              "is\nindistinguishable from noise — it is not evidence of a name effect.")


if __name__ == "__main__":
    main()
