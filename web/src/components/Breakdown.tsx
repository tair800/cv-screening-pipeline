import type { BreakdownLine } from "../types";

interface Props {
  lines: BreakdownLine[];
  activeRequirement: string | null;
  pinnedRequirement: string | null;
  onHover: (requirement: string | null) => void;
  onPin: (requirement: string | null) => void;
}

export function Breakdown({
  lines,
  activeRequirement,
  pinnedRequirement,
  onHover,
  onPin,
}: Props) {
  return (
    <div className="breakdown">
      {lines.map((line) => {
        const earned = line.awarded > 0;
        const locatable = line.matched.some((match) => match.span !== null);
        const isActive = activeRequirement === line.requirement;
        const isPinned = pinnedRequirement === line.requirement;

        return (
          <div
            key={line.requirement}
            className={[
              "req",
              earned ? "earned" : "missed",
              isActive ? "active" : "",
              locatable ? "locatable" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onMouseEnter={() => onHover(line.requirement)}
            onMouseLeave={() => onHover(null)}
            onClick={locatable ? () => onPin(isPinned ? null : line.requirement) : undefined}
            onKeyDown={
              locatable
                ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onPin(isPinned ? null : line.requirement);
                    }
                  }
                : undefined
            }
            role={locatable ? "button" : undefined}
            tabIndex={locatable ? 0 : undefined}
            aria-pressed={locatable ? isPinned : undefined}
          >
            <div className="req-points">
              <span className="req-awarded">{line.awarded.toFixed(line.awarded % 1 ? 1 : 0)}</span>
              <span className="req-weight">/{line.weight}</span>
            </div>

            <div className="req-body">
              <div className="req-title">
                {line.label}
                {line.must_have && <span className="tag">must have</span>}
                {isPinned && <span className="tag pinned">pinned</span>}
              </div>
              <div className="req-reason">{line.reason}</div>
              {line.matched.some((m) => m.written_as) && (
                <div className="req-alias">
                  matched through an alias —{" "}
                  {line.matched
                    .filter((m) => m.written_as)
                    .map((m) => `“${m.written_as}” accepted as ${m.skill}`)
                    .join("; ")}
                </div>
              )}
              {line.matched.length > 0 && !locatable && (
                <div className="req-alias">
                  no evidence span could be located in the CV text
                </div>
              )}
            </div>

            <div className="req-bar">
              <div
                className="req-fill"
                style={{ width: `${(line.awarded / line.weight) * 100}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
