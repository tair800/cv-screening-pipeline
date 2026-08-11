"""Decision log behaviour: append-only history, mandatory provenance, safe retries.

Runs against a throwaway log so the real one is never touched.

Run:
    python tests/test_decisions.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from decisions import DecisionError, apply_overrides, latest_by_cv, load, record  # noqa: E402

SCORED = {"score": 80.0, "role_id": "ai_automation_engineer", "unmet_must_haves": []}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "decisions.jsonl"

        record("cv_0001", "advance", "a@example.com", "strong automation background",
               SCORED, log=log)
        assert len(load(log)) == 1
        print("  ok  a decision is appended")

        # A change of mind must not erase the earlier decision.
        record("cv_0001", "reject", "b@example.com", "second review disagreed",
               SCORED, log=log)
        entries = load(log)
        assert len(entries) == 2, f"expected both entries retained, got {len(entries)}"
        assert entries[0]["decision"] == "advance"
        assert latest_by_cv(log)["cv_0001"]["decision"] == "reject"
        print("  ok  a reversal appends; the superseded entry is retained")
        print("  ok  the most recent entry is the effective decision")

        # Provenance is mandatory, not advisory.
        for label, kwargs in [
            ("blank reason", {"reason": "   "}),
            ("blank actor", {"actor": ""}),
            ("unknown decision", {"decision": "maybe"}),
        ]:
            args = {"cv_id": "cv_0002", "decision": "advance",
                    "actor": "a@example.com", "reason": "because", **kwargs}
            try:
                record(**args, log=log)
            except DecisionError:
                print(f"  ok  refused: {label}")
            else:
                raise AssertionError(f"{label} should have been refused")

        assert len(load(log)) == 2, "a refused decision must not be written"
        print("  ok  a refused decision leaves no entry behind")

        # A retry with the same key is a no-op; a different key is a new decision.
        first = record("cv_0003", "hold", "a@example.com", "awaiting portfolio",
                       SCORED, log=log, idempotency_key="req-9f2")
        again = record("cv_0003", "hold", "a@example.com", "awaiting portfolio",
                       SCORED, log=log, idempotency_key="req-9f2")
        assert len(load(log)) == 3, "a retry with the same key must not append"
        assert again["recorded_at"] == first["recorded_at"], "the retry must return the original"
        print("  ok  a retry with the same idempotency key is a no-op")

        record("cv_0003", "advance", "a@example.com", "portfolio arrived, it is good",
               SCORED, log=log, idempotency_key="req-a41")
        assert len(load(log)) == 4, "a different key is a genuine new decision"
        print("  ok  a different key appends a new decision")

        # The score is snapshotted, so a later rubric change is visible rather than silent.
        ranking = [{"cv_id": "cv_0003", "score": 55.0, "unmet_must_haves": []}]
        annotated = apply_overrides(ranking, log=log)[0]
        assert annotated["decision"] == "advance"
        assert annotated["score_at_decision"] == 80.0
        assert annotated["score_moved_since"] is True
        print("  ok  a score that moved since the decision is flagged, not hidden")

        # A candidate with no decision is annotated as such, not omitted.
        untouched = apply_overrides([{"cv_id": "cv_9999", "score": 10.0,
                                      "unmet_must_haves": []}], log=log)[0]
        assert untouched["decision"] is None and untouched["score_moved_since"] is False
        print("  ok  an undecided candidate is annotated, not dropped")

    print("\nall decision tests passed")


if __name__ == "__main__":
    main()
