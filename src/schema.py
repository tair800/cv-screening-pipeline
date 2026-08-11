"""Extraction contract: the JSON Schema every extractor must satisfy, plus validation
and evidence verification helpers."""

from __future__ import annotations

from jsonschema import Draft202012Validator

NULLABLE_STRING = {"type": ["string", "null"]}

CANDIDATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ExtractedCandidate",
    "type": "object",
    "additionalProperties": False,
    "required": ["cv_id", "name", "email", "phone", "location",
                 "years_experience", "skills", "education", "experience", "languages"],
    "properties": {
        "cv_id": {"type": "string"},
        "name": NULLABLE_STRING,
        "email": NULLABLE_STRING,
        "phone": NULLABLE_STRING,
        "location": NULLABLE_STRING,
        "years_experience": {"type": ["number", "null"], "minimum": 0, "maximum": 60},
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "evidence"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "evidence": {"type": "string", "minLength": 1},
                },
            },
        },
        "education": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["degree", "field", "institution", "year"],
            "properties": {
                "degree": NULLABLE_STRING,
                "field": NULLABLE_STRING,
                "institution": NULLABLE_STRING,
                "year": {"type": ["integer", "null"], "minimum": 1950, "maximum": 2030},
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["role", "company", "start_year", "end_year"],
                "properties": {
                    "role": NULLABLE_STRING,
                    "company": NULLABLE_STRING,
                    "start_year": {"type": ["integer", "null"], "minimum": 1950, "maximum": 2030},
                    "end_year": {"type": ["integer", "null"], "minimum": 1950, "maximum": 2030},
                },
            },
        },
        "languages": {"type": "array", "items": {"type": "string"}},
    },
}

_validator = Draft202012Validator(CANDIDATE_SCHEMA)

_UNSUPPORTED_BY_API = ("minimum", "maximum", "minLength", "maxLength", "multipleOf")


def api_schema() -> dict:
    """Return the schema with keywords the structured-output API rejects removed.

    Bounds stay in CANDIDATE_SCHEMA and are enforced locally by validate_record."""
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in _UNSUPPORTED_BY_API}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    schema = strip(CANDIDATE_SCHEMA)
    schema.pop("$schema", None)
    return schema


def validate_record(record: dict) -> list[str]:
    """Return a list of schema violations. Empty list means the record is valid."""
    return [
        f"{'.'.join(str(p) for p in error.path) or '<root>'}: {error.message}"
        for error in _validator.iter_errors(record)
    ]


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def verify_evidence(record: dict, source_text: str) -> list[str]:
    """Return skills whose evidence span does not appear in the source CV.

    A non-empty result means the extractor claimed a skill it cannot point at.

    Blank evidence is treated as unsupported rather than as a trivial pass. The empty
    string is a substring of every string, so a naive containment check accepts a skill
    backed by nothing at all — which is the exact failure this function exists to catch."""
    haystack = _normalise(source_text)
    unsupported = []
    for skill in record.get("skills", []):
        evidence = _normalise(skill.get("evidence") or "")
        if not evidence or evidence not in haystack:
            unsupported.append(skill.get("name", ""))
    return unsupported
