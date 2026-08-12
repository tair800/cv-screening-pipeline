import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Breakdown } from "./components/Breakdown";
import { DecisionForm } from "./components/DecisionForm";
import { RankingList } from "./components/RankingList";
import { SourceText } from "./components/SourceText";
import type { CandidateDetail, CandidateList, Health } from "./types";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [list, setList] = useState<CandidateList | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actor, setActor] = useState(
    () => localStorage.getItem("review.actor") ?? "",
  );

  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const active = pinned ?? hovered;

  const refreshList = useCallback(async () => {
    try {
      const next = await api.candidates();
      setList(next);
      setSelected((current) => current ?? next.candidates[0]?.cv_id ?? null);
    } catch (caught) {
      setError(String(caught));
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    void refreshList();
  }, [refreshList]);

  useEffect(() => {
    if (!selected) return;
    setPinned(null);
    setHovered(null);
    api.candidate(selected).then(setDetail).catch((caught) => setError(String(caught)));
  }, [selected]);

  useEffect(() => {
    localStorage.setItem("review.actor", actor);
  }, [actor]);

  const onRecorded = useCallback(async () => {
    await refreshList();
    if (selected) setDetail(await api.candidate(selected));
  }, [refreshList, selected]);

  const spans = useMemo(() => {
    if (!detail || !active) return [];
    const line = detail.breakdown.find((entry) => entry.requirement === active);
    if (!line) return [];
    return line.matched
      .map((match) => match.span)
      .filter((span): span is [number, number] => span !== null);
  }, [detail, active]);

  const activeLabel = useMemo(() => {
    if (!detail || !active) return null;
    return detail.breakdown.find((entry) => entry.requirement === active)?.label ?? null;
  }, [detail, active]);

  const unmetLabels = useMemo(() => {
    if (!detail) return [];
    return detail.unmet_must_haves.map(
      (id) => detail.breakdown.find((entry) => entry.requirement === id)?.label ?? id,
    );
  }, [detail]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-main">
          <h1>{list?.role.title ?? "Candidate review"}</h1>
          <p className="topbar-sub">
            {list ? `${list.count} candidates ranked` : "loading…"}
            {health && (
              <>
                {" · records: "}
                <span className="mono">{health.records}</span>
                {!health.has_evidence && (
                  <span className="topbar-warn">
                    no evidence spans in this source — highlighting unavailable
                  </span>
                )}
              </>
            )}
          </p>
        </div>
        <p className="topbar-note">
          Scoring never reads a name, a contact detail, a location or an institution.
          Those fields are shown here for the reviewer only.
        </p>
      </header>

      {error && <p className="banner">{error}</p>}

      <div className="split">
        <aside className="pane pane-list">
          {list ? (
            <RankingList
              candidates={list.candidates}
              selected={selected}
              onSelect={setSelected}
            />
          ) : (
            <p className="empty">Loading candidates…</p>
          )}
        </aside>

        <main className="pane pane-detail">
          {detail ? (
            <>
              <div className="detail-head">
                <div>
                  <h2>{detail.identity.name ?? detail.cv_id}</h2>
                  <p className="detail-meta mono">
                    {detail.cv_id}
                    {detail.identity.location && <> · {detail.identity.location}</>}
                  </p>
                </div>
                <div className="detail-score">
                  <span className="detail-score-value">{detail.score.toFixed(1)}</span>
                  <span className="detail-score-max">/ {detail.max_score}</span>
                </div>
              </div>

              {detail.unmet_must_haves.length > 0 && (
                <p className="notice warn">
                  Unmet must-have{detail.unmet_must_haves.length > 1 ? "s" : ""}:{" "}
                  {unmetLabels.join(", ")}. The pipeline does not reject — it flags, and
                  you decide.
                </p>
              )}

              {(detail.integrity.schema_violations.length > 0 ||
                detail.integrity.unsupported_skills.length > 0) && (
                <p className="notice bad">
                  {detail.integrity.schema_violations.length > 0 && (
                    <>
                      {detail.integrity.schema_violations.length} schema violation
                      {detail.integrity.schema_violations.length > 1 ? "s" : ""} in this
                      record.{" "}
                    </>
                  )}
                  {detail.integrity.unsupported_skills.length > 0 && (
                    <>
                      Skills claimed without evidence in the CV:{" "}
                      {detail.integrity.unsupported_skills.join(", ")}.
                    </>
                  )}
                </p>
              )}

              <Breakdown
                lines={detail.breakdown}
                activeRequirement={active}
                pinnedRequirement={pinned}
                onHover={setHovered}
                onPin={setPinned}
              />

              {detail.source_text && (
                <SourceText
                  text={detail.source_text}
                  spans={spans}
                  label={spans.length ? activeLabel : null}
                />
              )}

              <DecisionForm
                candidate={detail}
                actor={actor}
                onActorChange={setActor}
                onRecorded={onRecorded}
              />
            </>
          ) : (
            <p className="empty">Select a candidate.</p>
          )}
        </main>
      </div>
    </div>
  );
}
