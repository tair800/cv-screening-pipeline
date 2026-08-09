"""Diagnose the LLM connection one layer at a time, so a failure names its own cause.

Run:
    python src/check_connection.py
"""

from __future__ import annotations

import os
import socket
import sys
from urllib.parse import urlparse

from config import ENV_FILE, load_env, mask

OK, FAIL, WARN = "[ ok ]", "[fail]", "[warn]"


def _fail(message: str, fix: str) -> None:
    print(f"{FAIL} {message}")
    print(f"       fix: {fix}")
    sys.exit(1)


def main() -> None:
    load_env()
    print(f"Diagnosing LLM connection\n{'-' * 60}")

    if ENV_FILE.exists():
        print(f"{OK} .env found at {ENV_FILE}")
    else:
        print(f"{WARN} no .env file — using shell environment only")

    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")

    if not api_key:
        _fail("LLM_API_KEY is empty", f"paste the key after LLM_API_KEY= in {ENV_FILE}")
    print(f"{OK} LLM_API_KEY   {mask(api_key)}")

    if not base_url:
        _fail("LLM_BASE_URL is empty", "set it to your gateway's OpenAI-compatible URL")
    print(f"{OK} LLM_BASE_URL  {base_url}")
    print(f"{OK} LLM_MODEL     {model or '<not set>'}")

    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        _fail(f"LLM_BASE_URL is not a valid URL: {base_url}", "it must look like http://host:port/v1")

    print(f"\nReaching {host}:{port} …")
    try:
        with socket.create_connection((host, port), timeout=5):
            print(f"{OK} TCP connection established")
    except OSError as error:
        _fail(
            f"cannot reach {host}:{port} ({error})",
            "start the gateway, or point LLM_BASE_URL at a running endpoint",
        )

    try:
        from openai import OpenAI
    except ImportError:
        _fail("the openai package is not installed", "pip install -r requirements.txt")

    # A client's effective wait is timeout x (retries + 1) — the two multiply. Retries are
    # off here so a slow endpoint is reported as slow rather than silently waited on.
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=45.0, max_retries=0)
    prober = OpenAI(base_url=base_url, api_key=api_key, timeout=20.0, max_retries=0)

    print("\nListing models …")
    available: list[str] = []
    try:
        available = sorted(m.id for m in client.models.list().data)
        print(f"{OK} {len(available)} models available")
        for name in available[:15]:
            print(f"       {name}")
        if len(available) > 15:
            print(f"       … and {len(available) - 15} more")
    except Exception as error:
        print(f"{WARN} could not list models: {type(error).__name__}: {error}")
        print("       (some gateways do not expose /models — continuing)")

    if available and model and model not in available:
        print(f"\n{WARN} LLM_MODEL '{model}' is not in the list above")
        print(f"       set LLM_MODEL to one of them in {ENV_FILE}")

    print(f"\nSending a 1-token test request to '{model}' …")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=10,
        )
    except Exception as error:
        _fail(
            f"{type(error).__name__}: {error}",
            "check that LLM_MODEL is one the gateway actually serves, and that the key has access",
        )

    reply = (response.choices[0].message.content or "").strip()
    print(f"{OK} model replied: {reply!r}")

    print("\nProbing schema-enforcement support (20s each, no retries) …")
    for label, response_format in [
        ("json_schema", {"type": "json_schema", "json_schema": {
            "name": "Probe", "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                       "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}}}),
        ("json_object", {"type": "json_object"}),
    ]:
        try:
            prober.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": 'Return {"ok": true}'}],
                max_tokens=50,
                response_format=response_format,
            )
            print(f"{OK} {label} supported")
        except Exception as error:
            print(f"{WARN} {label} unavailable ({type(error).__name__}) — extractor will fall back")

    print(f"\n{'-' * 60}\nConnection is working. Next:")
    print("  python src/extract_llm.py data/samples/cv_0003.txt")


if __name__ == "__main__":
    main()
