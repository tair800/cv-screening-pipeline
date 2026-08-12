interface Props {
  text: string;
  /** Character ranges to highlight. May arrive unsorted and overlapping. */
  spans: Array<[number, number]>;
  label: string | null;
}

/** Merge overlapping or touching ranges so a character is never wrapped twice — nested
 *  <mark> elements double the background and read as a darker, meaningless band. */
function merge(spans: Array<[number, number]>): Array<[number, number]> {
  const sorted = [...spans]
    .filter(([start, end]) => Number.isFinite(start) && end > start)
    .sort((a, b) => a[0] - b[0]);

  const merged: Array<[number, number]> = [];
  for (const [start, end] of sorted) {
    const last = merged[merged.length - 1];
    if (last && start <= last[1]) {
      last[1] = Math.max(last[1], end);
    } else {
      merged.push([start, end]);
    }
  }
  return merged;
}

export function SourceText({ text, spans, label }: Props) {
  const ranges = merge(spans);

  const parts: Array<{ text: string; hit: boolean }> = [];
  let cursor = 0;
  for (const [start, end] of ranges) {
    const from = Math.max(cursor, Math.min(start, text.length));
    const to = Math.max(from, Math.min(end, text.length));
    if (from > cursor) parts.push({ text: text.slice(cursor, from), hit: false });
    if (to > from) parts.push({ text: text.slice(from, to), hit: true });
    cursor = to;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), hit: false });

  return (
    <div className="source">
      <div className="source-head">
        <span className="eyebrow">CV as submitted</span>
        {label ? (
          <span className="source-hint">
            highlighting evidence for <strong>{label}</strong>
          </span>
        ) : (
          <span className="source-hint muted">
            hover a requirement to see the text that earned it
          </span>
        )}
      </div>
      <pre className="source-body">
        {parts.map((part, index) =>
          part.hit ? (
            <mark key={index}>{part.text}</mark>
          ) : (
            <span key={index}>{part.text}</span>
          ),
        )}
      </pre>
    </div>
  );
}
