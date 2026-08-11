"""LLM extractor. Speaks the OpenAI chat-completions protocol, so it works against any
gateway, hosted provider, or local runtime that exposes /v1/chat/completions.

Configured entirely from .env — LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.

Usage:
    python src/extract_llm.py data/samples/cv_0003.txt
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI

from config import load_env
from schema import api_schema, validate_record

load_env()

DEFAULT_BASE_URL = "http://localhost:20128/v1"
DEFAULT_MODEL = "auto/best-free"

SYSTEM = """You extract structured candidate records from CV text.

Extract every field the CV states. Read the whole document before answering — facts
appear under headings in some CVs, inline in others, and inside prose in the rest.

Use null only when the CV genuinely does not state the field. Null means "the document
is silent on this", not "I am unsure". Do not infer, complete, or invent a value that
the document does not contain.

- Every skill needs an `evidence` span copied verbatim from the CV. Quote the shortest
  span that contains the skill, not the whole line. If no span can be quoted, omit the skill.
- years_experience is the total professional experience the CV claims, in years.
- end_year is null for a role the candidate still holds.

Return a single JSON object and nothing else. No prose, no markdown fences."""


class ExtractionError(RuntimeError):
    pass


def _log(message: str) -> None:
    """Progress goes to stderr so stdout stays a clean JSON stream."""
    print(f"[extract_llm] {message}", file=sys.stderr, flush=True)


_client: OpenAI | None = None
_mode: str | None = None

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _connect() -> OpenAI:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise ExtractionError("LLM_API_KEY is not set — see .env and run src/check_connection.py")
    # timeout and max_retries multiply into the worst-case wait per call. A repair doubles
    # the calls again, so a CV can take 4x this in the worst case.
    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
        api_key=key,
        timeout=float(os.environ.get("LLM_TIMEOUT", "120")),
        max_retries=1,
    )


def _response_format(mode: str) -> dict | None:
    """Schema enforcement is a capability, not a guarantee — gateways and models differ."""
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {"name": "ExtractedCandidate", "strict": True, "schema": api_schema()},
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def _parse(payload: str) -> dict:
    fenced = _FENCE_RE.search(payload)
    if fenced:
        payload = fenced.group(1)
    start, end = payload.find("{"), payload.rfind("}")
    if start == -1 or end == -1:
        raise ExtractionError("response contained no JSON object")
    return json.loads(payload[start:end + 1])


def _schema_prompt() -> str:
    """The schema goes in the prompt on every call, not only in the fallback tiers.

    An endpoint can accept `response_format: json_schema` and still not honour it, and it
    does not say which it is doing — so the request is written to be correct whether or
    not the transport enforces anything."""
    return (
        "\n\nThe object must match this JSON Schema exactly. Use these field names and "
        "types and no others — do not rename, add, or omit a field:\n"
        + json.dumps(api_schema(), separators=(",", ":"))
    )


def _call(model: str, messages: list[dict]) -> str:
    """Send one request, negotiating schema enforcement downward on the first call."""
    global _mode
    modes = [_mode] if _mode else ["json_schema", "json_object", "none"]
    last_error: Exception | None = None

    payload = list(messages)
    payload[0] = {**payload[0], "content": payload[0]["content"] + _schema_prompt()}

    for mode in modes:
        kwargs = {"model": model, "messages": payload, "temperature": 0}
        response_format = _response_format(mode)
        if response_format:
            kwargs["response_format"] = response_format
        try:
            response = _client.chat.completions.create(**kwargs)
        except Exception as error:
            last_error = error
            continue

        if _mode != mode:
            _mode = mode
            _log(f"schema enforcement requested: {mode}")
        return response.choices[0].message.content or ""

    raise ExtractionError(f"every request mode failed. Last error: {last_error}")


def extract(cv_id: str, text: str, model: str | None = None) -> dict:
    """Extract a candidate record, validating locally and repairing once if needed.

    An endpoint may accept a schema parameter and then not honour it, so the record is
    validated here rather than trusted."""
    global _client
    if _client is None:
        _client = _connect()

    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"cv_id: {cv_id}\n\n{text}"},
    ]

    record = _parse(_call(model, messages))
    record["cv_id"] = cv_id

    errors = validate_record(record)
    if not errors:
        return record

    _log(f"{cv_id}: {len(errors)} schema violations, repairing")
    messages += [
        {"role": "assistant", "content": json.dumps(record, ensure_ascii=False)},
        {"role": "user", "content":
            "That record does not match the required schema:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nReturn the same extracted information as a corrected JSON object. "
              "Keep every value you already extracted; change only names and types so "
              "they match the schema. Do not drop or invent information."},
    ]

    repaired = _parse(_call(model, messages))
    repaired["cv_id"] = cv_id

    remaining = validate_record(repaired)
    if remaining:
        _log(f"{cv_id}: {len(remaining)} violations remain after repair")
    return repaired


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LLM extractor on one CV.")
    parser.add_argument("cv_path", type=Path, help="path to a CV .txt file")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    text = args.cv_path.read_text(encoding="utf-8")
    record = extract(args.cv_path.stem, text, model=args.model)
    print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
