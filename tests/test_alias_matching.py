"""Alias matching: surface forms that should match, and near-misses that should not.

Both directions matter equally. A missed alias silently drops a real skill and costs a
candidate points they earned. An over-broad alias silently awards points for a skill the
candidate does not have — and that is the worse failure, because it is invisible in the
score and indefensible in a review.

Run:
    python tests/test_alias_matching.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from score import canonical, load_aliases, load_role, score  # noqa: E402

ALIASES = load_aliases()
ROLE = load_role(ROOT / "data" / "role_ai_automation_engineer.json")

SHOULD_CANONICALISE = [
    ("Postgres", "PostgreSQL"),
    ("psql", "PostgreSQL"),
    ("POSTGRES", "PostgreSQL"),
    ("  Postgres  ", "PostgreSQL"),
    ("REST API", "REST APIs"),
    ("RESTful APIs", "REST APIs"),
    ("HuggingFace", "Hugging Face"),
    ("Retrieval-Augmented Generation", "RAG"),
    ("Apache Airflow", "Airflow"),
    ("Microsoft Power Automate", "Power Automate"),
    ("Mongo", "MongoDB"),
    ("Python3", "Python"),
]

SHOULD_STAY_DISTINCT = [
    ("T-SQL", "SQL"),
    ("JSON Schema", "JSON"),
    ("LangGraph", "LangChain"),
    ("MySQL", "PostgreSQL"),
    ("Zapier", "Make"),
]


def record_with(skills: list[str], years: int = 3) -> dict:
    return {
        "cv_id": "synthetic",
        "years_experience": years,
        "skills": [{"name": s, "evidence": s} for s in skills],
        "experience": [],
        "education": None,
        "languages": [],
    }


def main() -> None:
    for written, expected in SHOULD_CANONICALISE:
        got = canonical(written, ALIASES)
        assert got == expected, f"{written!r} -> {got!r}, expected {expected!r}"
        print(f"  ok  {written!r} -> {expected!r}")

    print()
    for written, other in SHOULD_STAY_DISTINCT:
        got = canonical(written, ALIASES)
        assert got != other, f"{written!r} wrongly canonicalised to {other!r}"
        print(f"  ok  {written!r} stays distinct from {other!r}")

    print()
    # A skill written in an alias form must earn the same points as the canonical form,
    # and the explanation must say which form was written.
    canonical_score = score(record_with(["Python", "n8n", "REST APIs", "PostgreSQL"]), ROLE, ALIASES)
    alias_score = score(record_with(["Python3", "n8n.io", "REST API", "Postgres"]), ROLE, ALIASES)

    assert canonical_score["score"] == alias_score["score"], (
        f"alias forms scored {alias_score['score']}, canonical scored {canonical_score['score']}"
    )
    print(f"  ok  alias forms score identically to canonical forms "
          f"({alias_score['score']})")

    api_line = next(l for l in alias_score["breakdown"] if l["requirement"] == "req_api")
    assert any(m["written_as"] for m in api_line["matched"]), \
        "an alias match must record the surface form that was written"
    print(f"  ok  explanation records the surface form: {api_line['reason']}")

    # An unknown skill must not match anything by accident.
    unknown = score(record_with(["Kotlin", "Figma", "Jira"]), ROLE, ALIASES)
    matched = [l["label"] for l in unknown["breakdown"] if l["awarded"] > 0 and l["matched"]]
    assert not matched, f"unrelated skills matched requirements: {matched}"
    print("  ok  unrelated skills match nothing")

    print("\nall alias tests passed")


if __name__ == "__main__":
    main()
