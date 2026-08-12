"""Failure paths for the two checks the rest of the pipeline trusts.

`validate_record` and `verify_evidence` are the safety net: every claim about surviving a
provider that ignores a schema, and about detecting invented skills, rests on them. An
untested safety net is an assumption.

Each case below is a violation actually observed from a model or a plausible next one, and
several are violations the structured-output API *cannot* catch — `api_schema()` strips
`minimum`, `maximum` and `minLength` before sending, so bounds are enforced only here.

Run:
    python tests/test_validation.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from schema import api_schema, validate_record, verify_evidence  # noqa: E402

VALID = {
    "cv_id": "cv_0001",
    "name": "Anna Weber",
    "email": "anna.weber@example.com",
    "phone": "+49 151 1234567",
    "location": "Berlin, Germany",
    "years_experience": 4,
    "skills": [{"name": "Python", "evidence": "Python"}],
    "education": {
        "degree": "MSc",
        "field": "Computer Science",
        "institution": "Technical University of Munich",
        "year": 2019,
    },
    "experience": [
        {"role": "Automation Engineer", "company": "Northwind Logistics",
         "start_year": 2022, "end_year": None},
    ],
    "languages": ["English (C1)"],
}


def mutated(**changes) -> dict:
    record = copy.deepcopy(VALID)
    record.update(changes)
    return record


def drop(field: str) -> dict:
    record = copy.deepcopy(VALID)
    record.pop(field)
    return record


# Each entry: label, record, substring expected somewhere in the reported errors.
MUST_FAIL = [
    # Shape drift actually observed from a gateway that accepted the schema and ignored it
    ("education returned as an array", mutated(education=[VALID["education"]]), "education"),
    ("experience uses 'title' instead of 'role'",
     mutated(experience=[{"title": "Engineer", "company": "X",
                          "start_year": 2020, "end_year": None}]), "experience"),
    ("languages returned as objects",
     mutated(languages=[{"language": "English", "proficiency": "C1"}]), "languages"),
    ("unknown top-level field", mutated(seniority="mid"), "Additional properties"),

    # Missing required fields
    ("cv_id missing", drop("cv_id"), "cv_id"),
    ("skills missing", drop("skills"), "skills"),
    ("education missing entirely", drop("education"), "education"),

    # Bounds — the API cannot enforce these, api_schema() strips them
    ("years_experience above the maximum", mutated(years_experience=200), "years_experience"),
    ("years_experience negative", mutated(years_experience=-3), "years_experience"),
    ("graduation year implausibly early",
     mutated(education={**VALID["education"], "year": 1742}), "year"),
    ("empty skill name",
     mutated(skills=[{"name": "", "evidence": "Python"}]), "name"),
    ("skill with no evidence span",
     mutated(skills=[{"name": "Python"}]), "evidence"),

    # Type errors
    ("years_experience as a string", mutated(years_experience="four"), "years_experience"),
    ("skills as a list of strings", mutated(skills=["Python", "SQL"]), "skills"),
]

SOURCE = (
    "Anna Weber\nBerlin, Germany\n\n"
    "Tech: Python | SQL | REST APIs\n"
    "Experience (4 yrs): Automation Engineer at Northwind Logistics (2022 - Present)\n"
)

EVIDENCE_CASES = [
    ("exact span", [{"name": "Python", "evidence": "Python"}], []),
    ("span with surrounding text", [{"name": "SQL", "evidence": "Python | SQL | REST APIs"}], []),
    ("different case", [{"name": "Python", "evidence": "PYTHON"}], []),
    ("collapsed whitespace",
     [{"name": "REST APIs", "evidence": "REST     APIs"}], []),
    ("invented skill", [{"name": "Kubernetes", "evidence": "Kubernetes"}], ["Kubernetes"]),
    ("plausible but absent",
     [{"name": "Docker", "evidence": "containerised the service with Docker"}], ["Docker"]),
    ("empty evidence", [{"name": "Go", "evidence": ""}], ["Go"]),
    ("one real, one invented",
     [{"name": "Python", "evidence": "Python"},
      {"name": "Rust", "evidence": "Rust"}], ["Rust"]),
    # Ground-truth fixtures list skills as plain strings. They claim no evidence, so there
    # is nothing to verify — reporting them as invented would be a category error. Whether
    # this shape is permitted is validate_record's question.
    ("plain-string skills claim nothing", ["Python", "Kubernetes"], []),
    ("mixed shapes", ["Python", {"name": "Rust", "evidence": "Rust"}], ["Rust"]),
]


def main() -> None:
    assert validate_record(VALID) == [], f"the baseline record must validate: {validate_record(VALID)}"
    print("  ok  baseline record validates")

    print()
    for label, record, expected in MUST_FAIL:
        errors = validate_record(record)
        assert errors, f"{label}: expected a violation, got none"
        joined = " | ".join(errors)
        assert expected in joined, f"{label}: no error mentioned {expected!r} — got {joined}"
        print(f"  ok  caught: {label}")

    print()
    stripped = api_schema()
    import json as _json
    text = _json.dumps(stripped)
    for keyword in ("minimum", "maximum", "minLength"):
        assert keyword not in text, f"api_schema() still sends {keyword}"
    assert "minimum" in _json.dumps(
        __import__("schema").CANDIDATE_SCHEMA), "bounds must survive in the local schema"
    print("  ok  bounds stripped from the API schema, retained for local validation")

    print()
    for label, skills, expected in EVIDENCE_CASES:
        invented = verify_evidence({"skills": skills}, SOURCE)
        assert invented == expected, f"{label}: expected {expected}, got {invented}"
        verdict = "flagged" if expected else "accepted"
        print(f"  ok  {verdict}: {label}")

    print("\nall validation tests passed")


if __name__ == "__main__":
    main()
