"""Tests for what the evaluation metric does and does not forgive.

The name comparison was deliberately loosened to case-insensitive after an exact-match test
scored a faithful ALL-CAPS extraction as wrong. Loosening a metric raises numbers, which is
the direction that hides regressions, so the boundary is pinned here: the cases below assert
both that formatting is forgiven and that nothing else is.

Run:
    python tests/test_evaluation_metric.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evaluate import CASE_INSENSITIVE_FIELDS, _field_match

MUST_MATCH = [
    ("caps name from a classic-layout header", "name", "ANNA BAKKER", "Anna Bakker"),
    ("lower-case name", "name", "anna bakker", "Anna Bakker"),
    ("surrounding whitespace", "name", "  Anna Bakker ", "Anna Bakker"),
    ("upper-case email", "email", "ANNA@EXAMPLE.COM", "anna@example.com"),
    ("city in caps", "location", "BAKU, AZERBAIJAN", "Baku, Azerbaijan"),
    ("identical strings", "name", "Anna Bakker", "Anna Bakker"),
    ("identical numbers", "years_experience", 10, 10),
]

MUST_NOT_MATCH = [
    ("a different person", "name", "Anna Bakker", "Anna Baker"),
    ("first name only", "name", "Anna", "Anna Bakker"),
    ("missing name", "name", None, "Anna Bakker"),
    ("empty name", "name", "", "Anna Bakker"),
    ("internal spacing is not formatting", "name", "AnnaBakker", "Anna Bakker"),
    ("a different mailbox", "email", "anna.b@example.com", "anna@example.com"),
    ("a different city", "location", "Berlin, Germany", "Baku, Azerbaijan"),
    # years and phone stay exact: a digit is not a formatting choice.
    ("off-by-one years", "years_experience", 9, 10),
    ("phone is compared exactly", "phone", "+49 164 999 6414", "+49 164 9996414"),
]


def main() -> None:
    for label, field, predicted, truth in MUST_MATCH:
        assert _field_match(field, predicted, truth), f"should match: {label}"

    for label, field, predicted, truth in MUST_NOT_MATCH:
        assert not _field_match(field, predicted, truth), f"should not match: {label}"

    assert "years_experience" not in CASE_INSENSITIVE_FIELDS
    assert "phone" not in CASE_INSENSITIVE_FIELDS

    print(f"{len(MUST_MATCH)} forgiven, {len(MUST_NOT_MATCH)} still caught")


if __name__ == "__main__":
    main()
