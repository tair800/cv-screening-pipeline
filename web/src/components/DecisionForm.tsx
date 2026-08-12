import { useState } from "react";
import { ApiError, api } from "../api";
import type { CandidateDetail, Decision } from "../types";

interface Props {
  candidate: CandidateDetail;
  actor: string;
  onActorChange: (actor: string) => void;
  onRecorded: () => void;
}

const OPTIONS: Array<{ value: Decision; label: string }> = [
  { value: "advance", label: "Advance" },
  { value: "hold", label: "Hold" },
  { value: "reject", label: "Reject" },
];

export function DecisionForm({ candidate, actor, onActorChange, onRecorded }: Props) {
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const existing = candidate.decision;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!decision) return;
    setBusy(true);
    setError(null);
    try {
      await api.decide(candidate.cv_id, { decision, actor, reason });
      setDecision(null);
      setReason("");
      onRecorded();
    } catch (caught) {
      // The server enforces the same rules; surface its refusal rather than a generic one.
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="decide" onSubmit={submit}>
      <div className="decide-head">
        <span className="eyebrow">Your decision</span>
        {existing.decision && (
          <span className="decide-existing">
            currently <span className={`chip ${existing.decision}`}>{existing.decision}</span>
            {existing.decided_by && <> by {existing.decided_by}</>}
            {existing.score_moved_since && (
              <span className="decide-moved">
                score was {existing.score_at_decision} when decided
              </span>
            )}
          </span>
        )}
      </div>

      <div className="decide-options">
        {OPTIONS.map((option) => (
          <label key={option.value} className={decision === option.value ? "on" : ""}>
            <input
              type="radio"
              name="decision"
              value={option.value}
              checked={decision === option.value}
              onChange={() => setDecision(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>

      <label className="field">
        <span>Reason</span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={2}
          placeholder="Why this decision — recorded verbatim in the audit log"
        />
      </label>

      <label className="field">
        <span>Your name or address</span>
        <input
          type="text"
          value={actor}
          onChange={(event) => onActorChange(event.target.value)}
          placeholder="recruiter@example.com"
        />
      </label>

      {error && <p className="decide-error">{error}</p>}

      <div className="decide-actions">
        <button type="submit" disabled={busy || !decision || !reason.trim() || !actor.trim()}>
          {busy ? "Recording…" : "Record decision"}
        </button>
        <span className="decide-note">
          A reason and an author are required. Recording appends — it never rewrites the
          earlier entry.
        </span>
      </div>
    </form>
  );
}
