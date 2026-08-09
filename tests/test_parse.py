"""Failure-path tests for the OpenAI-compatible extractor's JSON recovery.

Run:
    python tests/test_parse.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from extract_llm import ExtractionError, _parse

FENCED = "```json\n{\"name\": \"Anna\"}\n```"
FENCED_BARE = "```\n{\"name\": \"Anna\"}\n```"
PREAMBLE = "Sure! Here is the extracted record:\n{\"name\": \"Anna\"}"
TRAILING = "{\"name\": \"Anna\"}\n\nLet me know if you need anything else."
CLEAN = "{\"name\": \"Anna\"}"
NESTED = "{\"a\": {\"b\": 1}}"


def main() -> None:
    for label, payload in [
        ("fenced json", FENCED),
        ("fenced bare", FENCED_BARE),
        ("preamble", PREAMBLE),
        ("trailing prose", TRAILING),
        ("clean", CLEAN),
    ]:
        assert _parse(payload) == {"name": "Anna"}, label
        print(f"  ok  {label}")

    assert _parse(NESTED) == {"a": {"b": 1}}, "nested braces"
    print("  ok  nested braces")

    for label, payload in [("empty", ""), ("prose only", "I cannot do that.")]:
        try:
            _parse(payload)
        except ExtractionError:
            print(f"  ok  {label} raises ExtractionError")
        else:
            raise AssertionError(f"{label} should have raised")

    print("all parse tests passed")


if __name__ == "__main__":
    main()
