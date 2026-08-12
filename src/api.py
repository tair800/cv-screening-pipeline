"""HTTP surface for the review UI.

Thin by design: every endpoint delegates to the modules the CLI already uses, so the API
and the command line cannot drift into scoring a candidate differently.

Run:
    uvicorn api:app --reload --app-dir src
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import load_env
from decisions import DECISIONS, DecisionError, apply_overrides, load, latest_by_cv, record
from schema import locate_evidence, validate_record, verify_evidence
from score import load_aliases, load_records, load_role, rank

load_env()

ROOT = Path(__file__).resolve().parents[1]
ROLE_PATH = ROOT / "data" / "role_ai_automation_engineer.json"
SOURCE_DIR = ROOT / "data" / "synthetic"


def _records_dir() -> Path:
    """Prefer real extractions, fall back to ground truth.

    Only extracted records carry evidence spans, so the review UI can highlight the CV text
    that earned each point. Ground truth lists skills as plain strings — it ranks fine and
    shows no highlights, which is the honest degradation rather than a fabricated one."""
    override = os.environ.get("REVIEW_RECORDS")
    if override:
        return Path(override)
    extracted = ROOT / "data" / "extracted"
    if extracted.exists() and any(extracted.glob("cv_*.json")):
        return extracted
    return SOURCE_DIR

app = FastAPI(title="CV screening review", version="1.0")


def _state() -> tuple[dict, list[dict], dict[str, dict]]:
    """Reload on every request. The dataset is small and a stale cache in a review tool is
    a worse failure than the cost of re-reading it."""
    role = load_role(ROLE_PATH)
    records = load_records(_records_dir())
    ranking = apply_overrides(rank(records, role, load_aliases()))
    return role, ranking, {r["cv_id"]: r for r in records}


def _source_text(cv_id: str) -> str | None:
    """The CV always comes from the source directory: an extraction directory holds records,
    not the documents they were read from."""
    path = SOURCE_DIR / f"{cv_id}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None


class DecisionIn(BaseModel):
    decision: str = Field(description="one of advance, reject, hold")
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str | None = None


@app.get("/api/role")
def get_role() -> dict:
    role = load_role(ROLE_PATH)
    return {
        "role_id": role["role_id"],
        "title": role["title"],
        "seniority": role["seniority"],
        "location": role["location"],
        "requirements": [
            {"id": r["id"], "label": r["label"], "weight": r["weight"],
             "must_have": r.get("must_have", False), "type": r["type"]}
            for r in role["requirements"]
        ],
        "excluded_from_scoring": role["excluded_from_scoring"],
        "exclusion_rationale": role["exclusion_rationale"],
    }


@app.get("/api/candidates")
def list_candidates() -> dict:
    role, ranking, records = _state()
    labels = {r["id"]: r["label"] for r in role["requirements"]}
    return {
        "role": {"role_id": role["role_id"], "title": role["title"]},
        "count": len(ranking),
        "candidates": [
            {
                "cv_id": r["cv_id"],
                # Shown to the reviewer, never read by the scorer. The API keeps the two
                # apart so the separation is visible rather than merely documented.
                "name": records[r["cv_id"]].get("name"),
                "score": r["score"],
                "unmet_must_haves": r["unmet_must_haves"],
                "unmet_labels": [labels.get(i, i) for i in r["unmet_must_haves"]],
                "decision": r["decision"],
                "decided_by": r["decided_by"],
                "score_moved_since": r["score_moved_since"],
                "score_at_decision": r["score_at_decision"],
            }
            for r in ranking
        ],
    }


@app.get("/api/candidates/{cv_id}")
def get_candidate(cv_id: str) -> dict:
    _, ranking, records = _state()
    scored = next((r for r in ranking if r["cv_id"] == cv_id), None)
    if scored is None:
        raise HTTPException(404, f"no candidate {cv_id}")

    record_data = records[cv_id]
    source = _source_text(cv_id)

    breakdown = []
    for line in scored["breakdown"]:
        matches = []
        for match in line["matched"]:
            span = locate_evidence(source, match.get("evidence")) if source else None
            matches.append({
                "skill": match["skill"],
                "written_as": match.get("written_as"),
                "evidence": match.get("evidence"),
                "span": list(span) if span else None,
            })
        breakdown.append({**line, "matched": matches})

    return {
        "cv_id": cv_id,
        "identity": {
            "name": record_data.get("name"),
            "email": record_data.get("email"),
            "location": record_data.get("location"),
        },
        "score": scored["score"],
        "max_score": scored["max_score"],
        "unmet_must_haves": scored["unmet_must_haves"],
        "breakdown": breakdown,
        "decision": {
            "decision": scored["decision"],
            "decided_by": scored["decided_by"],
            "decided_at": scored["decided_at"],
            "reason": scored["decision_reason"],
            "score_at_decision": scored["score_at_decision"],
            "score_moved_since": scored["score_moved_since"],
        },
        "source_text": source,
        "integrity": {
            "schema_violations": validate_record(record_data),
            "unsupported_skills": verify_evidence(record_data, source) if source else [],
        },
    }


@app.post("/api/candidates/{cv_id}/decision")
def post_decision(cv_id: str, body: DecisionIn) -> dict:
    _, ranking, _ = _state()
    scored = next((r for r in ranking if r["cv_id"] == cv_id), None)
    if scored is None:
        raise HTTPException(404, f"no candidate {cv_id}")
    if body.decision not in DECISIONS:
        raise HTTPException(422, f"decision must be one of {list(DECISIONS)}")

    before = len(load())
    try:
        entry = record(cv_id, body.decision, body.actor, body.reason, scored,
                       idempotency_key=body.idempotency_key)
    except DecisionError as error:
        raise HTTPException(422, str(error)) from error

    return {"entry": entry, "appended": len(load()) > before}


@app.get("/api/decisions")
def get_decisions() -> dict:
    entries = load()
    effective = latest_by_cv()
    return {
        "count": len(entries),
        "superseded": len(entries) - len(effective),
        "entries": list(reversed(entries)),
    }


@app.get("/api/audit")
def get_audit() -> dict:
    from score import audit_rubric
    role, ranking, _ = _state()
    return audit_rubric(ranking, role)


@app.get("/api/health")
def health() -> dict:
    try:
        role, ranking, _ = _state()
    except Exception as error:
        raise HTTPException(500, f"{type(error).__name__}: {error}") from error
    directory = _records_dir()
    return {
        "ok": True,
        "role": role["role_id"],
        "candidates": len(ranking),
        "records": directory.name,
        "has_evidence": directory.name != SOURCE_DIR.name,
    }
