import type { CandidateSummary } from "../types";

interface Props {
  candidates: CandidateSummary[];
  selected: string | null;
  onSelect: (cvId: string) => void;
}

export function RankingList({ candidates, selected, onSelect }: Props) {
  return (
    <ol className="ranking">
      {candidates.map((candidate, index) => (
        <li key={candidate.cv_id}>
          <button
            type="button"
            className={`rank-row${selected === candidate.cv_id ? " selected" : ""}`}
            onClick={() => onSelect(candidate.cv_id)}
          >
            <span className="rank-pos">{index + 1}</span>
            <span className="rank-main">
              <span className="rank-name">{candidate.name ?? candidate.cv_id}</span>
              <span className="rank-id">{candidate.cv_id}</span>
            </span>
            <span className="rank-meta">
              {candidate.decision && (
                <span className={`chip ${candidate.decision}`}>{candidate.decision}</span>
              )}
              {candidate.unmet_must_haves.length > 0 && (
                <span
                  className="chip warn"
                  title={`unmet: ${candidate.unmet_labels.join(", ")}`}
                >
                  {candidate.unmet_must_haves.length} unmet
                </span>
              )}
              <span className="rank-score">{candidate.score.toFixed(1)}</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
