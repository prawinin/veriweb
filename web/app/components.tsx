"use client";

import {
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  FileText,
  GitCompareArrows,
  Layers3,
  Link2,
  ScanLine,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { Citation, ResearchResult, RunEvent, Source } from "@/lib/types";

export function Brand({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand ${small ? "brand-small" : ""}`}>
      <svg viewBox="0 0 36 36" fill="none" aria-hidden="true">
        <path d="M5 8h7l7 20h-7L5 8Z" fill="currentColor" opacity=".5" />
        <path d="m19 8 6 17 6-17h-7l-3 8-3-8h1Z" fill="currentColor" />
        <path d="m12 8 7 20 4-10-4-10h-7Z" fill="currentColor" />
      </svg>
      <span>
        veriweb<span className="brand-period">.</span>
      </span>
    </span>
  );
}

export function domain(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Source";
  }
}
export function sourceNumber(id: string) {
  return id.replace(/^s/, "").padStart(2, "0");
}

export function CitationBadge({
  citation,
  onSelect,
}: {
  citation: Citation;
  onSelect: (citation: Citation) => void;
}) {
  return (
    <button
      className="citation"
      onClick={() => onSelect(citation)}
      aria-label={`Inspect source ${sourceNumber(citation.source_id)} quote`}
    >
      <Link2 size={11} />
      {sourceNumber(citation.source_id)}
    </button>
  );
}

const stages = [
  { key: "plan", title: "Understand the question", icon: Layers3 },
  { key: "search", title: "Find the sources", icon: Search },
  { key: "extract", title: "Read the full articles", icon: ScanLine },
  { key: "rank", title: "Keep relevant evidence", icon: ListIcon },
  { key: "verify", title: "Compare and synthesize", icon: GitCompareArrows },
];
function ListIcon({ size = 16 }: { size?: number }) {
  return <FileText size={size} />;
}

export function Activity({
  events,
  busy,
  elapsed,
  queries,
}: {
  events: RunEvent[];
  busy: boolean;
  elapsed: number;
  queries: string[];
}) {
  const last = events.at(-1);
  const current =
    last?.type === "result"
      ? stages.length
      : Math.max(
          -1,
          stages.findIndex((stage) => stage.key === last?.stage),
        );
  return (
    <aside className="activity-pane">
      <div className="pane-heading">
        <span className="heading-with-icon">
          <span className={`live-dot ${busy ? "pulsing" : ""}`} />
          Research activity
        </span>
        <span className="muted small">
          {events.length ? `${elapsed.toFixed(1)}s` : "Ready"}
        </span>
      </div>
      <div className="stage-list">
        {stages.map((stage, index) => {
          const Icon = stage.icon;
          const done = current > index;
          const active = current === index && busy;
          return (
            <div
              key={stage.key}
              className={`stage ${done ? "done" : ""} ${active ? "active" : ""}`}
            >
              <div className="stage-icon">
                {done ? <Check size={14} /> : <Icon size={15} />}
              </div>
              <span>{stage.title}</span>
              {active && <span className="stage-spinner" />}
            </div>
          );
        })}
      </div>
      <div className="trace-label">
        Run log{" "}
        <span>
          {events.filter((e) => e.type !== "heartbeat").length || "—"}
        </span>
      </div>
      <div
        className="event-list"
        tabIndex={0}
        role="region"
        aria-label="Research event log"
        aria-live="polite"
        aria-relevant="additions"
      >
        {events.length ? (
          events
            .filter((e) => e.type !== "heartbeat")
            .map((event, index) => (
              <div className={`event event-${event.level}`} key={index}>
                <time>{event.elapsed.toFixed(1).padStart(4, "0")}</time>
                <div>
                  <span className="event-symbol">
                    {event.level === "warning"
                      ? "!"
                      : event.level === "error"
                        ? "×"
                        : "+"}
                  </span>
                  {event.message}
                </div>
              </div>
            ))
        ) : (
          <div className="trace-empty">
            <span className="terminal-cursor" />
            <p>The research trail starts here.</p>
            <span>
              Searches, article reads, and evidence checks appear as they
              happen.
            </span>
          </div>
        )}
      </div>
      {!!queries.length && (
        <details className="query-details">
          <summary>
            {queries.length} search queries <ChevronRight size={13} />
          </summary>
          <ol>
            {queries.map((query) => (
              <li key={query}>{query}</li>
            ))}
          </ol>
        </details>
      )}
      <div className="activity-note">
        <ShieldCheck size={15} />
        <p>
          Article text, not search snippets.
          <br />
          Every extraction stays traceable.
        </p>
      </div>
    </aside>
  );
}

const sourceTypeLabels: Record<Source["source_type"], string> = {
  public_institution: "Public institution",
  research: "Research",
  technical: "Technical documentation",
  other: "Other source",
};

export function Coverage({
  result,
  onSelect,
}: {
  result: ResearchResult;
  onSelect: (citation: Citation) => void;
}) {
  if (!result.coverage.length) return null;
  const subjects = [
    ...new Set(
      result.coverage.flatMap((row) => row.cells.map((cell) => cell.subject)),
    ),
  ];
  return (
    <section className="coverage-section" aria-label="Requested coverage">
      <h3>Requested coverage</h3>
      <p className="coverage-note">
        Source-reported values for the requested dimensions. Scoped estimates
        may not be comparable; inspect the quotes for units, definitions, and
        measurement dates. Publication dates describe the source, not when a
        value was measured.
      </p>
      <div
        className="coverage-scroll"
        role="region"
        aria-label="Requested coverage table, scroll to view all subjects"
        tabIndex={0}
      >
        <table className="coverage-table">
          <caption className="coverage-caption">
            Requested dimensions and supporting source values by subject
          </caption>
          <thead>
            <tr>
              <th scope="col">Dimension</th>
              {subjects.map((subject) => (
                <th scope="col" key={subject}>
                  {subject}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.coverage.map((row) => (
              <tr key={row.dimension}>
                <th scope="row">{row.label}</th>
                {subjects.map((subject) => {
                  const cell = row.cells.find(
                    (entry) => entry.subject === subject,
                  );
                  return (
                    <td key={subject}>
                      {cell?.status === "supported" && cell.values.length ? (
                        <ul className="coverage-values">
                          {cell.values.map((entry, index) => (
                            <li key={index}>
                              <span className="coverage-value">
                                {entry.value}
                              </span>{" "}
                              <CitationBadge
                                citation={entry.citation}
                                onSelect={onSelect}
                              />
                              <span className="coverage-date">
                                {entry.published_at
                                  ? `Published ${entry.published_at.slice(0, 10)}`
                                  : "Date unavailable"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="coverage-missing">Not found</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Report({
  result,
  onSelect,
}: {
  result: ResearchResult | null;
  onSelect: (citation: Citation) => void;
}) {
  if (!result)
    return (
      <div className="report-empty">
        <div className="document-emblem">
          <FileText size={27} strokeWidth={1.2} />
          <span>
            <Check size={11} />
          </span>
        </div>
        <h2>Room for a better answer.</h2>
        <p>
          Start with a question. Your report will take shape here, with a source
          behind every claim.
        </p>
        <div className="empty-report-sample">
          <div>
            <ShieldCheck size={17} />
            <span>Evidence you can inspect</span>
          </div>
          <div>
            <GitCompareArrows size={17} />
            <span>Disagreements you can see</span>
          </div>
          <div>
            <BookOpen size={17} />
            <span>A report you can take with you</span>
          </div>
        </div>
        <span className="empty-footnote">
          Built for questions that need more than one source.
        </span>
      </div>
    );
  const summaries = result.claims.filter((c) => c.section === "summary");
  const findings = result.claims.filter((c) => c.section === "finding");
  return (
    <article className="report-document">
      <div className="report-meta">
        {result.status !== "complete" && (
          <span className={`report-state ${result.status}`}>
            {result.status === "excerpts"
              ? "Evidence excerpts"
              : "Incomplete analysis"}
          </span>
        )}
        <span className="report-date">
          {new Date(result.created_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
          })}
        </span>
      </div>
      <h2>{result.question}</h2>
      <div className="report-byline">
        {result.sources.length} sources read
        <span />
        {result.passages.length} passages retained
        <span />
        {result.telemetry.ranking}
      </div>
      <Coverage result={result} onSelect={onSelect} />
      {!!summaries.length && (
        <section className="report-summary">
          <h3>Executive summary</h3>
          {summaries.map((claim, index) => (
            <p key={index}>
              {claim.text}{" "}
              <span className="citation-group">
                {claim.citations.map((citation, i) => (
                  <CitationBadge
                    key={i}
                    citation={citation}
                    onSelect={onSelect}
                  />
                ))}
              </span>
            </p>
          ))}
        </section>
      )}
      {!!findings.length && (
        <section className="findings">
          <h3>What the evidence says</h3>
          {findings.map((claim, index) => (
            <div className="finding" key={index}>
              <span className="finding-marker" />
              <p>
                {claim.text}{" "}
                <span className="citation-group">
                  {claim.citations.map((citation, i) => (
                    <CitationBadge
                      key={i}
                      citation={citation}
                      onSelect={onSelect}
                    />
                  ))}
                </span>
              </p>
            </div>
          ))}
        </section>
      )}
      {!result.claims.length && (
        <section className="excerpt-section">
          <div className="section-heading">
            <h3>From the sources</h3>
            <span>Exact passages</span>
          </div>
          <p className="section-description">
            Retrieved evidence is shown verbatim. These excerpts have not been
            synthesized or checked for contradictions.
          </p>
          {result.passages.map((passage) => {
            const source = result.sources.find(
              (s) => s.id === passage.source_id,
            );
            return (
              <div className="excerpt" key={passage.id}>
                <button
                  className="excerpt-source"
                  onClick={() =>
                    onSelect({
                      source_id: passage.source_id,
                      quote: passage.quote,
                    })
                  }
                >
                  <span className="source-mini">
                    {sourceNumber(passage.source_id)}
                  </span>
                  {source ? domain(source.url) : passage.source_id}
                  <ArrowUpRight size={12} />
                </button>
                <blockquote>{passage.quote}</blockquote>
              </div>
            );
          })}
        </section>
      )}
      {!!result.gaps.length && (
        <section className="limitations">
          <h3>
            <CircleHelp size={16} />
            What remains uncertain
          </h3>
          <ul>
            {result.gaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </section>
      )}
      <div className="report-disclaimer">
        <CheckCheck size={15} />
        <span>
          Quotes are matched to extracted source text. A matching quote
          establishes provenance, not independent verification of a claim.
        </span>
      </div>
    </article>
  );
}

export function ConflictMatrix({
  result,
  onSelect,
}: {
  result: ResearchResult;
  onSelect: (citation: Citation) => void;
}) {
  return (
    <section className="conflict-matrix">
      <div className="matrix-heading">
        <div>
          <GitCompareArrows size={18} />
          <h3>Where sources diverge</h3>
        </div>
        <span
          className={result.conflicts.length ? "amber-label" : "neutral-label"}
        >
          {result.conflicts.length
            ? `${result.conflicts.length} to review`
            : "No candidates returned"}
        </span>
      </div>
      {result.conflicts.length ? (
        <>
          <p className="matrix-description">
            Candidate disagreements, paired with the passages behind them.
            Review scope and reporting dates before drawing a conclusion.
          </p>
          {result.conflicts.map((conflict, index) => (
            <div className="conflict-row" key={index}>
              <div className="conflict-title">
                <span className="conflict-kind">{conflict.kind}</span>
                <h4>{conflict.title}</h4>
              </div>
              <div className="conflict-pair">
                {[conflict.left, conflict.right].map((citation, side) => {
                  const source = result.sources.find(
                    (s) => s.id === citation.source_id,
                  );
                  return (
                    <button key={side} onClick={() => onSelect(citation)}>
                      <span>
                        <span className="source-mini">
                          {sourceNumber(citation.source_id)}
                        </span>
                        {source ? domain(source.url) : citation.source_id}
                        <ArrowUpRight size={12} />
                      </span>
                      {(side === 0
                        ? conflict.left_quantity
                        : conflict.right_quantity) && (
                        <div className="comparison-quantity">
                          {side === 0
                            ? conflict.left_quantity
                            : conflict.right_quantity}
                        </div>
                      )}
                      <q>{citation.quote}</q>
                    </button>
                  );
                })}
              </div>
              <p className="conflict-explanation">
                <strong>
                  {conflict.kind === "unresolved"
                    ? "Review note: "
                    : "Model interpretation: "}
                </strong>
                {conflict.explanation}
              </p>
            </div>
          ))}
        </>
      ) : (
        <div className="no-conflicts">
          <GitCompareArrows size={22} />
          <p>
            {result.status === "excerpts"
              ? "Connect a model to compare source claims."
              : "The model returned no supported disagreement candidates."}
            <span>This does not establish that the sources agree.</span>
          </p>
        </div>
      )}
    </section>
  );
}

export function Sources({
  sources,
  onSelect,
}: {
  sources: Source[];
  onSelect: (citation: Citation) => void;
}) {
  return (
    <div className="source-catalog">
      <h2>The source record</h2>
      <p>
        Full article extraction. Retrieval times and publication dates stay
        attached to each source. Source kinds describe context, not reliability.
      </p>
      {sources.length ? (
        sources.map((source) => (
          <button
            className="source-row"
            key={source.id}
            onClick={() => onSelect({ source_id: source.id, quote: "" })}
          >
            <span className="source-mini">{sourceNumber(source.id)}</span>
            <div>
              <span>{domain(source.url)}</span>
              <h3>{source.title}</h3>
              <p>
                {sourceTypeLabels[source.source_type]}
                {` · ${source.text.length.toLocaleString()} characters read`}
                {source.published_at
                  ? ` · Published ${source.published_at.slice(0, 10)}`
                  : " · Publication date unavailable"}
              </p>
            </div>
            <ArrowUpRight size={17} />
          </button>
        ))
      ) : (
        <div className="sources-empty">
          <BookOpen size={25} />
          <p>Sources appear here as articles are read.</p>
        </div>
      )}
    </div>
  );
}

export function Inspector({
  sources,
  selected,
  onSelect,
  result,
}: {
  sources: Source[];
  selected: Citation | null;
  onSelect: (citation: Citation) => void;
  result: ResearchResult | null;
}) {
  const source = sources.find((s) => s.id === selected?.source_id);
  return (
    <aside className="inspector">
      <div className="pane-heading">
        <span className="heading-with-icon">
          <BookOpen size={15} />
          Evidence inspector
        </span>
        <span className="count-chip">{sources.length}</span>
      </div>
      {source ? (
        <div className="inspector-content">
          <div className="inspector-domain">
            <span className="source-mini">{sourceNumber(source.id)}</span>
            {domain(source.url)}
          </div>
          <h3>{source.title}</h3>
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="source-external"
          >
            Open original article <ArrowUpRight size={13} />
          </a>
          <div className="inspector-metadata">
            <span>Source kind</span>
            <span>{sourceTypeLabels[source.source_type]}</span>
            <span>Retrieved</span>
            <span>
              {new Date(source.retrieved_at).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <span>Published</span>
            <span>{source.published_at?.slice(0, 10) ?? "Not available"}</span>
          </div>
          <p className="source-kind-note">
            Source kind describes context, not reliability.
          </p>
          {selected?.quote ? (
            <>
              <div className="quote-heading">
                <Link2 size={13} />
                Supporting passage
              </div>
              <blockquote className="selected-quote">
                {selected.quote}
              </blockquote>
              <div className="quote-verified">
                <CheckCheck size={13} />
                {source.text.includes(selected.quote)
                  ? "Exact match in extracted text"
                  : "Quote not found in stored article text"}
              </div>
            </>
          ) : (
            <div className="source-preview">
              <div className="quote-heading">Extracted article</div>
              <p tabIndex={0} aria-label="Extracted article preview">
                {source.text.slice(0, 3500)}
                {source.text.length > 3500 ? " [Preview ends]" : ""}
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="inspector-empty">
          <div className="linked-pages">
            <div />
            <div>
              <Link2 size={22} strokeWidth={1.3} />
            </div>
          </div>
          <h3>Keep the source in sight.</h3>
          <p>
            Select a citation to read the exact passage behind a claim, without
            leaving the report.
          </p>
          <div className="inspector-example">
            <span className="example-citation">
              <Link2 size={11} />
              01
            </span>
            <span>Look for these citation badges.</span>
          </div>
        </div>
      )}
      {!!sources.length && (
        <div className="inspector-source-list">
          <h4>Sources in this research</h4>
          {sources.map((s) => (
            <button
              className={source?.id === s.id ? "selected" : ""}
              key={s.id}
              onClick={() => onSelect({ source_id: s.id, quote: "" })}
            >
              <span className="source-mini">{sourceNumber(s.id)}</span>
              <span>{domain(s.url)}</span>
              <ChevronRight size={13} />
            </button>
          ))}
        </div>
      )}
      <div className="trust-note">
        <ShieldCheck size={17} />
        <div>
          <h4>Trust is a paper trail.</h4>
          <p>
            {result
              ? `${result.claims.length} cited claims. ${result.conflicts.length} candidate disagreements. Inspect the evidence before relying on a conclusion.`
              : "We preserve the passage, the source, and the uncertainty. You make the final call."}
          </p>
        </div>
      </div>
    </aside>
  );
}
