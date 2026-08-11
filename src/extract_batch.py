"""Extract a set of CVs and persist the records, so downstream stages can run without
re-spending tokens.

Resumable: a CV whose record already exists in the output directory is skipped, so an
interrupted run costs nothing to continue.

Usage:
    python src/extract_batch.py --pairs-only          # just the bias-pair CVs
    python src/extract_batch.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from extract_llm import extract

ROOT = Path(__file__).resolve().parents[1]


def pair_ids(source: Path) -> list[str]:
    manifest = json.loads((source / "_manifest.json").read_text(encoding="utf-8"))
    return [cv_id for pair in manifest["bias_pairs"] for cv_id in pair["cv_ids"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract CVs and write the records to disk.")
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "extracted")
    parser.add_argument("--pairs-only", action="store_true",
                        help="only the CVs that belong to a matched bias pair")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.source / "_manifest.json", args.out / "_manifest.json")

    if args.pairs_only:
        targets = [args.source / f"{cv_id}.txt" for cv_id in pair_ids(args.source)]
    else:
        targets = sorted(args.source.glob("cv_*.txt"))
    if args.limit:
        targets = targets[:args.limit]

    written = skipped = failed = 0
    for position, cv_path in enumerate(targets, start=1):
        destination = args.out / f"{cv_path.stem}.json"
        if destination.exists():
            skipped += 1
            print(f"  {position}/{len(targets)} {cv_path.stem} — already extracted",
                  file=sys.stderr, flush=True)
            continue

        print(f"  {position}/{len(targets)} {cv_path.stem}", file=sys.stderr, flush=True)
        try:
            record = extract(cv_path.stem, cv_path.read_text(encoding="utf-8"))
        except Exception as error:
            failed += 1
            print(f"      failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            continue

        destination.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                               encoding="utf-8")
        written += 1

    print(f"\nwritten {written}   skipped {skipped}   failed {failed}   -> {args.out}")


if __name__ == "__main__":
    main()
