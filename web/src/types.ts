export type Decision = "advance" | "reject" | "hold";

export interface Health {
  ok: boolean;
  role: string;
  candidates: number;
  records: string;
  has_evidence: boolean;
}

export interface CandidateSummary {
  cv_id: string;
  name: string | null;
  score: number;
  unmet_must_haves: string[];
  unmet_labels: string[];
  decision: Decision | null;
  decided_by: string | null;
  score_moved_since: boolean;
  score_at_decision: number | null;
}

export interface CandidateList {
  role: { role_id: string; title: string };
  count: number;
  candidates: CandidateSummary[];
}

export interface Match {
  skill: string;
  written_as: string | null;
  evidence: string | null;
  /** Character offsets into source_text, or null when the span could not be located. */
  span: [number, number] | null;
}

export interface BreakdownLine {
  requirement: string;
  label: string;
  weight: number;
  must_have: boolean;
  awarded: number;
  matched: Match[];
  reason: string;
}

export interface CandidateDetail {
  cv_id: string;
  identity: { name: string | null; email: string | null; location: string | null };
  score: number;
  max_score: number;
  unmet_must_haves: string[];
  breakdown: BreakdownLine[];
  decision: {
    decision: Decision | null;
    decided_by: string | null;
    decided_at: string | null;
    reason: string | null;
    score_at_decision: number | null;
    score_moved_since: boolean;
  };
  source_text: string | null;
  integrity: { schema_violations: string[]; unsupported_skills: string[] };
}

export interface AuditRequirement {
  requirement: string;
  label: string;
  weight: number;
  award_rate: number;
  distinct_awards: number;
  modal_share: number;
  discriminates: boolean;
}

export interface Audit {
  candidates: number;
  distinct_scores: number;
  top_score: number;
  tied_at_top: number;
  dead_weight: number;
  requirements: AuditRequirement[];
}

export interface DecisionEntry {
  recorded_at: string;
  cv_id: string;
  decision: Decision;
  actor: string;
  reason: string;
  pipeline: {
    score: number | null;
    role_id: string | null;
    unmet_must_haves: string[] | null;
    model: string | null;
  };
  idempotency_key: string | null;
}

export interface DecisionLog {
  count: number;
  superseded: number;
  entries: DecisionEntry[];
}
