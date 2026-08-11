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


def compare(role: dict, records_dir: Path, pair: dict) -> dict:
    a_id, b_id = pair["cv_ids"]
    a = score(load_record(records_dir, a_id), role)
    b = score(load_record(records_dir, b_id), role)

    per_requirement = [
        {
            "requirement": left["requirement"],
            "a": left["awarded"],
            "b": right["awarded"],
        }
        for left, right in zip(a["breakdown"], b["breakdown"])
        if left["awarded"] != right["awarded"]
    ]

    return {
        "pair_id": pair["pair_id"],
        "a": {"cv_id": a_id, "score": a["score"]},
        "b": {"cv_id": b_id, "score": b["score"]},
        "delta": round(a["score"] - b["score"], 2),
        "diverging_requirements": per_requirement,
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

    failures = [r for r in results if r["delta"] != 0 or r["diverging_requirements"]]

    print(f"matched pairs: {len(results)}   source: {args.records.name}\n")
    for r in results:
        mark = "FAIL" if r in failures else " ok "
        print(f"  {mark}  {r['pair_id']}  {r['a']['cv_id']} {r['a']['score']:>6.2f}"
              f"   {r['b']['cv_id']} {r['b']['score']:>6.2f}   delta {r['delta']:+.2f}")
        for diverging in r["diverging_requirements"]:
            print(f"          {diverging['requirement']}: "
                  f"{diverging['a']} vs {diverging['b']}")

    print()
    if failures:
        print(f"{len(failures)} of {len(results)} pairs scored differently.")
        print("A pair differing only by name must score identically. Investigate before")
        print("this pipeline goes near a real applicant.")
        sys.exit(1)

    print(f"all {len(results)} pairs scored identically — no disparate treatment detected")


if __name__ == "__main__":
    main()
