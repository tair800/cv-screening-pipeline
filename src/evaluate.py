"""Score an extractor against the generated ground truth.

Usage:
    python src/evaluate.py --extractor baseline
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from schema import validate_record, verify_evidence

SIMPLE_FIELDS = ["name", "email", "phone", "location", "years_experience"]


def _load_extractor(name: str):
    if name == "baseline":
        from extract_baseline import extract
        return extract
    if name == "llm":
        from extract_llm import extract
        return extract
    raise SystemExit(f"unknown extractor: {name}")


def _skill_scores(predicted: dict, truth: dict) -> tuple[int, int, int]:
    predicted_skills = {s["name"].lower() for s in predicted.get("skills", [])}
    true_skills = {s.lower() for s in truth.get("skills", [])}
    hits = len(predicted_skills & true_skills)
    return hits, len(predicted_skills) - hits, len(true_skills) - hits


def evaluate(extractor_name: str, data_dir: Path, limit: int | None = None) -> dict:
    extract = _load_extractor(extractor_name)

    cv_files = sorted(data_dir.glob("cv_*.txt"))
    if not cv_files:
        raise SystemExit(f"no CVs in {data_dir} — run generate_synthetic_cvs.py first")
    if limit:
        cv_files = cv_files[:limit]

    field_hits = defaultdict(int)
    by_layout = defaultdict(lambda: {"total": 0, "name_hits": 0, "experience_hits": 0})
    schema_failures, hallucinations, extraction_errors = [], [], []
    skill_hits = skill_false = skill_missed = 0
    experience_hits = 0

    for cv_path in cv_files:
        text = cv_path.read_text(encoding="utf-8")
        truth = json.loads(cv_path.with_suffix(".json").read_text(encoding="utf-8"))
        try:
            predicted = extract(cv_path.stem, text)
        except Exception as error:
            extraction_errors.append((cv_path.stem, f"{type(error).__name__}: {error}"))
            continue

        errors = validate_record(predicted)
        if errors:
            schema_failures.append((cv_path.stem, errors[0]))

        invented = verify_evidence(predicted, text)
        if invented:
            hallucinations.append((cv_path.stem, invented))

        for field in SIMPLE_FIELDS:
            if predicted.get(field) == truth.get(field):
                field_hits[field] += 1

        hits, false_positives, missed = _skill_scores(predicted, truth)
        skill_hits += hits
        skill_false += false_positives
        skill_missed += missed

        experience_match = len(predicted.get("experience", [])) == len(truth.get("experience", []))
        experience_hits += experience_match

        layout = truth.get("_meta", {}).get("layout", "unknown")
        by_layout[layout]["total"] += 1
        by_layout[layout]["name_hits"] += predicted.get("name") == truth.get("name")
        by_layout[layout]["experience_hits"] += experience_match

    total = len(cv_files) - len(extraction_errors)
    if total == 0:
        raise SystemExit(f"every extraction failed; first error: {extraction_errors[0][1]}")

    return {
        "extractor": extractor_name,
        "cvs": total,
        "extraction_errors": extraction_errors[:5],
        "schema_valid": total - len(schema_failures),
        "schema_failures": schema_failures[:5],
        "hallucinated_skills": hallucinations[:5],
        "field_accuracy": {f: round(field_hits[f] / total, 3) for f in SIMPLE_FIELDS},
        "experience_count_accuracy": round(experience_hits / total, 3),
        "skills": {
            "recall": round(skill_hits / (skill_hits + skill_missed), 3) if skill_hits + skill_missed else 0,
            "precision": round(skill_hits / (skill_hits + skill_false), 3) if skill_hits + skill_false else 0,
        },
        "by_layout": {
            layout: {
                "cvs": stats["total"],
                "name_accuracy": round(stats["name_hits"] / stats["total"], 3),
                "experience_accuracy": round(stats["experience_hits"] / stats["total"], 3),
            }
            for layout, stats in sorted(by_layout.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an extractor against ground truth.")
    parser.add_argument("--extractor", default="baseline", help="baseline | llm")

    parser.add_argument("--limit", type=int, help="only evaluate the first N CVs")
    parser.add_argument("--data", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data" / "synthetic",
                        help="directory holding cv_*.txt and cv_*.json")
    args = parser.parse_args()

    report = evaluate(args.extractor, args.data, limit=args.limit)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
