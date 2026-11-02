"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent,
} from "react";
import {
  ArrowDown,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BookOpen,
  ChevronDown,
  CircleHelp,
  Command,
  Cpu,
  FileText,
  GitCompareArrows,
  History,
  LoaderCircle,
  Menu,
  PanelLeft,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Square,
  X,
} from "lucide-react";
import { z } from "zod";
import { readEvents } from "@/lib/stream";
import { markdownReport } from "@/lib/export";
import { introProgress } from "@/lib/presentation";
import {
  resultSchema,
  statusSchema,
  type Citation,
  type ResearchResult,
  type RunEvent,
  type ServiceStatus,
  type Source,
} from "@/lib/types";
import {
  Activity,
  Brand,
  ConflictMatrix,
  Inspector,
  Report,
  Sources,
} from "./components";

const examples = [
  {
    title: "Follow the money",
    question:
      "Compare semiconductor manufacturing subsidies in India and the United States. Distinguish announced funding from actual disbursements.",
  },
  {
    title: "Test a claim",
    question:
      "How much electricity do AI data centers use, and why do recent estimates disagree? Compare reporting dates and measurement scopes.",
  },
  {
    title: "See both sides",
    question:
      "What does current evidence say about sodium-ion batteries versus lithium-ion batteries for grid storage? Compare costs, lifetimes, and commercial availability.",
  },
];
type Tab = "report" | "sources" | "conflicts";
const HISTORY_KEY = "veriweb.research.v1";

export default function Workbench() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [queries, setQueries] = useState<string[]>([]);
  const [selected, setSelected] = useState<Citation | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [tab, setTab] = useState<Tab>("report");
  const [history, setHistory] = useState<ResearchResult[]>([]);
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [navigationMode, setNavigationMode] = useState<
    "closed" | "hover" | "pinned"
  >("closed");
  const sidebarOpen = navigationMode !== "closed";
  function setSidebarOpen(open: boolean) {
    setNavigationMode(open ? "pinned" : "closed");
  }
  const [mode, setMode] = useState<"research" | "excerpts">("research");
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const inspector = useRef<HTMLDivElement>(null);
  const settingsDialog = useRef<HTMLDialogElement>(null);
  const startTime = useRef(0);
  const intro = useRef<HTMLElement>(null);
  const workspace = useRef<HTMLElement>(null);
  const navigationDialog = useRef<HTMLDialogElement>(null);
  const navigationCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  function keepNavigationOpen() {
    if (navigationCloseTimer.current !== null) {
      clearTimeout(navigationCloseTimer.current);
      navigationCloseTimer.current = null;
    }
  }

  function previewNavigation(event: PointerEvent<HTMLElement>) {
    if (
      event.pointerType !== "mouse" ||
      !window.matchMedia(
        "(hover: hover) and (pointer: fine) and (min-width: 761px)",
      ).matches
    )
      return;
    keepNavigationOpen();
    if (navigationMode === "closed") setNavigationMode("hover");
  }

  function leaveNavigation() {
    if (navigationMode !== "hover") return;
    keepNavigationOpen();
    navigationCloseTimer.current = setTimeout(() => {
      navigationCloseTimer.current = null;
      if (!navigationDialog.current?.contains(document.activeElement))
        setNavigationMode("closed");
    }, 160);
  }

  function scrollToWorkspace() {
    workspace.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "start",
    });
  }

  function editQuestion() {
    window.scrollTo({
      top: 0,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
    requestAnimationFrame(() => input.current?.focus({ preventScroll: true }));
  }

  useEffect(() => {
    const element = intro.current;
    if (!element) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      element.style.setProperty(
        "--intro-progress",
        String(introProgress(window.scrollY, window.innerHeight)),
      );
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  useEffect(() => {
    const dialog = navigationDialog.current;
    if (navigationMode === "closed" || !dialog) return;
    const previousOverflow = document.body.style.overflow;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNavigationMode("closed");
    };
    if (navigationMode === "pinned") {
      document.body.style.overflow = "hidden";
      dialog.showModal();
    } else {
      dialog.open = true;
      window.addEventListener("keydown", dismiss);
    }
    return () => {
      keepNavigationOpen();
      window.removeEventListener("keydown", dismiss);
      dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [navigationMode]);

  const refreshStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/status", {
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(6500)])
          : AbortSignal.timeout(6500),
      });
      if (!response.ok) throw new Error("Unavailable");
      setStatus(statusSchema.parse(await response.json()));
      setConnectionError(false);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError")
        return;
      setConnectionError(true);
    }
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    const initialize = async () => {
      try {
        const saved = localStorage.getItem(HISTORY_KEY);
        if (saved)
          setHistory(z.array(resultSchema).max(5).parse(JSON.parse(saved)));
      } catch {
        setNotice(
          "Saved research could not be loaded. You can start a new run.",
        );
      }
      await refreshStatus(abort.signal);
    };
    void initialize();
    return () => {
      abort.abort();
      controller.current?.abort();
    };
  }, [refreshStatus]);

  useEffect(() => {
    if (!busy) return;
    workspace.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "start",
    });
    const timer = setInterval(
      () => setElapsed((performance.now() - startTime.current) / 1000),
      100,
    );
    return () => clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    const dialog = settingsDialog.current;
    if (!settingsOpen || !dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, [settingsOpen]);

  function remember(next: ResearchResult) {
    const updated = [
      next,
      ...history.filter((item) => item.id !== next.id),
    ].slice(0, 5);
    while (JSON.stringify(updated).length > 3_000_000 && updated.length > 1)
      updated.pop();
    setHistory(updated);
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    } catch {
      setNotice(
        "This report is available, but browser storage is full. Export it to keep a copy.",
      );
    }
  }

  async function research() {
    if (controller.current || busy || question.trim().length < 12) return;
    const abort = new AbortController();
    controller.current = abort;
    startTime.current = performance.now();
    setBusy(true);
    setResult(null);
    setEvents([]);
    setSources([]);
    setQueries([]);
    setSelected(null);
    setError("");
    setNotice("");
    setElapsed(0);
    setTab("report");
    try {
      const response = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim(), mode }),
        signal: AbortSignal.any([abort.signal, AbortSignal.timeout(610000)]),
      });
      if (!response.ok || !response.body) {
        const payload: unknown = await response.json();
        const detail =
          typeof payload === "object" &&
          payload !== null &&
          "detail" in payload &&
          typeof payload.detail === "string"
            ? payload.detail
            : "The research request could not be started. Check the backend and retry.";
        throw new Error(detail);
      }
      for await (const event of readEvents(response.body)) {
        if (event.type !== "heartbeat")
          setEvents((current) => [...current, event]);
        if (event.queries) setQueries(event.queries);
        if (event.source)
          setSources((current) =>
            [
              ...current.filter((s) => s.id !== event.source?.id),
              event.source as Source,
            ].sort((a, b) => a.id.localeCompare(b.id)),
          );
        if (event.type === "error") setError(event.message);
        if (event.result) {
          setResult(event.result);
          setSources(event.result.sources);
          remember(event.result);
        }
      }
    } catch (reason) {
      if (abort.signal.aborted) {
        setNotice(
          "Research cancelled. Sources already read remain available in the Sources tab.",
        );
        setEvents((current) => [
          ...current,
          {
            type: "log",
            stage: "cancelled",
            message: "Research cancelled by you.",
            level: "warning",
            elapsed: (performance.now() - startTime.current) / 1000,
          },
        ]);
      } else
        setError(
          reason instanceof Error
            ? reason.message
            : "The request failed. Check your connection and retry.",
        );
    } finally {
      setBusy(false);
      controller.current = null;
      void refreshStatus();
    }
  }

  function reset() {
    if (busy) return;
    setQuestion("");
    setResult(null);
    setSources([]);
    setEvents([]);
    setQueries([]);
    setSelected(null);
    setError("");
    setNotice("");
    setElapsed(0);
    setTab("report");
    setSidebarOpen(false);
    editQuestion();
  }

  function openHistory(item: ResearchResult) {
    if (busy) return;
    setResult(item);
    setQuestion(item.question);
    setSources(item.sources);
    setQueries(item.queries);
    setEvents([]);
    setSelected(null);
    setTab("report");
    setError("");
    setNotice("");
    setSidebarOpen(false);
    scrollToWorkspace();
  }

  function selectCitation(citation: Citation) {
    setSelected(citation);
    if (window.matchMedia("(max-width: 1200px)").matches)
      requestAnimationFrame(() =>
        inspector.current?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "instant"
            : "smooth",
          block: "start",
        }),
      );
  }

  function exportReport() {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([markdownReport(result)], {
        type: "text/markdown;charset=utf-8",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `veriweb-${result.id.slice(0, 8)}.md`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <div className="app-shell">
      <button
        className="navigation-rail"
        aria-label="Expand navigation"
        aria-controls="workspace-navigation"
        aria-expanded={sidebarOpen}
        onPointerEnter={previewNavigation}
        onPointerLeave={leaveNavigation}
        onClick={() => setSidebarOpen(true)}
      >
        <PanelLeft size={16} />
      </button>
      <dialog
        ref={navigationDialog}
        id="workspace-navigation"
        className="navigation-dialog"
        data-mode={navigationMode}
        onPointerEnter={keepNavigationOpen}
        onPointerLeave={leaveNavigation}
        aria-label="Workspace navigation"
        onCancel={() => setSidebarOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            const bounds = event.currentTarget.getBoundingClientRect();
            if (
              event.clientX < bounds.left ||
              event.clientX > bounds.right ||
              event.clientY < bounds.top ||
              event.clientY > bounds.bottom
            )
              setSidebarOpen(false);
          }
        }}
      >
        <button
          className="navigation-close"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
          autoFocus
        >
          <X size={20} />
        </button>
        <nav className="sidebar" aria-label="Main navigation">
          <button
            onClick={reset}
            className="brand-link"
            aria-label="Veriweb home"
          >
            <Brand />
          </button>
          <div className="workspace-switch">
            <span className="workspace-avatar">V</span>
            <div>
              Personal workspace<span>Research, with receipts.</span>
            </div>
            <ChevronDown size={13} />
          </div>
          <button className="new-research" onClick={reset} disabled={busy}>
            <Plus size={17} />
            New research
            <span>
              <Command size={11} />
            </span>
          </button>
          <div className="nav-items">
            <button
              className="nav-item active"
              onClick={() => {
                setTab("report");
                setSidebarOpen(false);
                scrollToWorkspace();
              }}
            >
              <Search size={17} />
              Research workspace
              <span className="nav-active-dot" />
            </button>
            <button
              className="nav-item"
              onClick={() => {
                setTab("sources");
                setSidebarOpen(false);
                scrollToWorkspace();
              }}
            >
              <BookOpen size={17} />
              Source library
              <span className="sidebar-count">{sources.length}</span>
            </button>
          </div>
          <div className="history-heading">
            <span>
              <History size={13} />
              Recent research
            </span>
            <span>{history.length || ""}</span>
          </div>
          <div className="history-list">
            {history.length ? (
              history.map((item) => (
                <button
                  key={item.id}
                  disabled={busy}
                  onClick={() => openHistory(item)}
                  className={result?.id === item.id ? "selected" : ""}
                >
                  <FileText size={14} />
                  <span>{item.question}</span>
                </button>
              ))
            ) : (
              <p>
                Your research stays here.
                <br />
                Start a question to build your library.
              </p>
            )}
          </div>
          <div className="sidebar-bottom">
            <button
              className="sidebar-help"
              onClick={() => setSettingsOpen(true)}
            >
              <CircleHelp size={16} />
              Setup & methodology
              <ArrowUpRight size={13} />
            </button>
            <div className="profile">
              <span className="profile-avatar">V</span>
              <div>
                Local workspace<span>Private browser history</span>
              </div>
              <button
                aria-label="Open settings"
                onClick={() => setSettingsOpen(true)}
              >
                <Settings2 size={16} />
              </button>
            </div>
          </div>
        </nav>
      </dialog>

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-brand">
            <button
              className="navigation-toggle"
              aria-label="Open navigation"
              aria-controls="workspace-navigation"
              aria-expanded={sidebarOpen}
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={21} />
            </button>
            <button
              className="topbar-home"
              aria-label="Veriweb home"
              onClick={reset}
            >
              <Brand />
            </button>
          </div>
          <div className="topbar-right">
            <button
              className="amd-badge"
              aria-label="Compute and connection settings"
              onClick={() => setSettingsOpen(true)}
            >
              <span className="amd-wordmark">
                AMD
                <span className="amd-mark" />
              </span>
              <Cpu size={15} strokeWidth={1.6} aria-hidden="true" />
              <span>Compute</span>
            </button>
            <span className="topbar-divider" />
            <button
              className="help-button"
              aria-label="Setup and methodology"
              onClick={() => setSettingsOpen(true)}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        <main>
          <section
            className="research-intro"
            ref={intro}
            aria-labelledby="intro-title"
          >
            <div className="intro-content">
              <div className="intro-top">
                <h1 id="intro-title">A clearer view.</h1>
                <p>Explore a question. Trace every answer to its source.</p>
              </div>
              <form
                className={`research-form ${busy ? "is-running" : ""}`}
                onSubmit={(event) => {
                  event.preventDefault();
                  void research();
                }}
              >
                <div className="input-area">
                  <textarea
                    ref={input}
                    aria-label="Research question"
                    placeholder="What would you like to investigate?"
                    value={question}
                    maxLength={1500}
                    disabled={busy}
                    rows={2}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        (event.metaKey || event.ctrlKey) &&
                        event.key === "Enter"
                      ) {
                        event.preventDefault();
                        void research();
                      }
                    }}
                  />
                </div>
                <div className="input-toolbar">
                  <div className="input-tools">
                    <label className="mode-select">
                      <LayersIcon />
                      <select
                        aria-label="Research mode"
                        value={mode}
                        disabled={busy}
                        onChange={(event) =>
                          setMode(event.target.value as "research" | "excerpts")
                        }
                      >
                        <option value="research">Deep research</option>
                        <option value="excerpts">Evidence only</option>
                      </select>
                      <ChevronDown size={12} />
                    </label>
                    <span className="input-divider" />
                    <span className="input-hint">Up to 8 sources</span>
                  </div>
                  {busy ? (
                    <button
                      type="button"
                      className="cancel-button"
                      onClick={(event) => {
                        event.preventDefault();
                        controller.current?.abort();
                      }}
                    >
                      <Square size={12} fill="currentColor" />
                      Stop research
                    </button>
                  ) : (
                    <button
                      className="research-button"
                      disabled={question.trim().length < 12}
                      type="submit"
                    >
                      Investigate <ArrowRight size={16} />
                    </button>
                  )}
                </div>
              </form>
              {!result && !busy && !events.length && (
                <div className="suggestions">
                  {examples.map((example) => (
                    <button
                      key={example.title}
                      onClick={() => {
                        setQuestion(example.question);
                        input.current?.focus();
                      }}
                    >
                      {example.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button className="workspace-cue" onClick={scrollToWorkspace}>
              Explore the workspace <ArrowDown size={16} />
            </button>
          </section>
          {error && (
            <div className="message-banner error-banner" role="alert">
              <CircleHelp size={17} />
              <p>{error}</p>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="message-banner notice-banner" role="status">
              <CircleHelp size={16} />
              <p>{notice}</p>
              <button onClick={() => setNotice("")} aria-label="Dismiss notice">
                <X size={16} />
              </button>
            </div>
          )}
          <section
            className="workbench"
            ref={workspace}
            aria-label="Research workbench"
          >
            <div className="workspace-question">
              <button
                className="navigation-toggle"
                aria-label="Open navigation from workspace"
                aria-controls="workspace-navigation"
                aria-expanded={sidebarOpen}
                onClick={() => setSidebarOpen(true)}
              >
                <Menu size={20} />
              </button>
              <span>{question.trim() || "Your research workspace"}</span>
              <button className="edit-question" onClick={editQuestion}>
                Edit question <ArrowUpRight size={14} />
              </button>
            </div>
            <div className="workbench-tabs">
              <div
                className="tab-group"
                role="tablist"
                aria-label="Research views"
              >
                <button
                  role="tab"
                  aria-selected={tab === "report"}
                  className={tab === "report" ? "selected" : ""}
                  onClick={() => setTab("report")}
                >
                  <FileText size={15} />
                  Report
                </button>
                <button
                  role="tab"
                  aria-selected={tab === "sources"}
                  className={tab === "sources" ? "selected" : ""}
                  onClick={() => setTab("sources")}
                >
                  <BookOpen size={15} />
                  Sources<span>{sources.length}</span>
                </button>
                <button
                  role="tab"
                  aria-selected={tab === "conflicts"}
                  className={tab === "conflicts" ? "selected" : ""}
                  onClick={() => setTab("conflicts")}
                >
                  <GitCompareArrows size={15} />
                  Disagreements
                  {result && (
                    <span
                      className={
                        result.conflicts.length ? "conflict-count" : ""
                      }
                    >
                      {result.conflicts.length}
                    </span>
                  )}
                </button>
              </div>
              <button
                className="export-button"
                aria-label="Export report"
                disabled={!result}
                onClick={exportReport}
              >
                <ArrowDownToLine size={14} />
                <span>Export report</span>
              </button>
            </div>
            {result && (
              <div
                className="workspace-telemetry"
                aria-label="Measured research performance"
              >
                <span>{result.telemetry.model}</span>
                <span>{result.telemetry.ranking}</span>
                {result.telemetry.retrieval_seconds != null && (
                  <span>
                    {result.telemetry.retrieval_seconds.toFixed(1)}s retrieval
                  </span>
                )}
                {result.telemetry.tokens_per_second != null && (
                  <span>{result.telemetry.tokens_per_second} tokens/s</span>
                )}
                <button onClick={() => setSettingsOpen(true)}>
                  Compute details <ArrowUpRight size={13} />
                </button>
              </div>
            )}
            <div className="workbench-body">
              <Activity
                events={events}
                busy={busy}
                elapsed={elapsed}
                queries={queries}
              />
              <div className="report-pane" role="tabpanel" aria-label={tab}>
                <div className="document-toolbar">
                  <span>
                    {tab === "report"
                      ? "Intelligence report"
                      : tab === "sources"
                        ? "Source record"
                        : "Conflict & trust matrix"}
                  </span>
                  {busy ? (
                    <span className="working-label">
                      <LoaderCircle size={12} />
                      Researching
                    </span>
                  ) : (
                    <span className="document-label">
                      {result ? "Saved locally" : "Awaiting a question"}
                    </span>
                  )}
                </div>
                {tab === "report" ? (
                  <>
                    <Report result={result} onSelect={selectCitation} />
                    {result && (
                      <ConflictMatrix
                        result={result}
                        onSelect={selectCitation}
                      />
                    )}
                  </>
                ) : tab === "sources" ? (
                  <Sources sources={sources} onSelect={selectCitation} />
                ) : result ? (
                  <ConflictMatrix result={result} onSelect={selectCitation} />
                ) : (
                  <div className="conflict-empty">
                    <GitCompareArrows size={30} strokeWidth={1.2} />
                    <h2>
                      Different sources.
                      <br />
                      Different stories?
                    </h2>
                    <p>
                      When research finds competing claims, their exact passages
                      appear side by side here.
                    </p>
                    <span>
                      Nothing is marked as a contradiction without paired
                      evidence.
                    </span>
                  </div>
                )}
              </div>
              <div
                className="inspector-wrapper"
                ref={inspector}
                tabIndex={0}
                role="region"
                aria-label="Evidence inspector panel"
              >
                <Inspector
                  sources={sources}
                  selected={selected}
                  onSelect={selectCitation}
                  result={result}
                />
              </div>
            </div>
          </section>
          <footer className="main-footer">
            <span>
              <ShieldCheck size={13} />
              Evidence first. Uncertainty included.
            </span>
            <span>
              Veriweb for AMD AI League
              <span className="footer-dot" />
              Match 4
            </span>
          </footer>
        </main>
      </div>
      {settingsOpen && (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) setSettingsOpen(false);
          }}
        >
          <dialog
            ref={settingsDialog}
            onCancel={() => setSettingsOpen(false)}
            className="settings-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
          >
            <button
              className="dialog-close"
              aria-label="Close setup"
              onClick={() => setSettingsOpen(false)}
              autoFocus
            >
              <X size={20} />
            </button>
            <Cpu size={26} className="dialog-icon" />
            <h2 id="settings-title">Your model. Your compute.</h2>
            <p>
              Veriweb retrieves live evidence with or without a model. Connect
              an open model for query planning, synthesis, and candidate
              disagreement analysis.
            </p>
            <div className="settings-status">
              <Cpu size={16} strokeWidth={1.6} aria-hidden="true" />
              <strong>
                {connectionError
                  ? "Backend unavailable"
                  : status?.available
                    ? "Model connected"
                    : "Model not connected"}
              </strong>
              <button onClick={() => void refreshStatus()}>Check again</button>
            </div>
            <dl className="settings-facts">
              <div>
                <dt>Model</dt>
                <dd>{status?.model ?? "Not configured"}</dd>
              </div>
              <div>
                <dt>Backend</dt>
                <dd>{status?.backend ?? "Unverified"} (configuration)</dd>
              </div>
              <div>
                <dt>Retrieval</dt>
                <dd>
                  {status?.embeddings
                    ? "BM25 + sentence embeddings"
                    : "BM25; embeddings not loaded"}
                </dd>
              </div>
            </dl>
            <h3>Local setup</h3>
            <p>
              Run the hardware check, connect a compatible model server, then
              start the app. Keep model weights within your GPU memory budget.
            </p>
            <pre>python scripts/doctor.py{"\n"}python scripts/dev.py</pre>
            <p className="settings-env">
              Set <code>VERIWEB_MODEL_URL</code> to your server’s API base
              ending in <code>/v1</code>, and <code>VERIWEB_MODEL_NAME</code> to
              its model ID in <code>.env</code>. See the repository README for
              local model commands and optional AMD cloud configuration.
            </p>
            <h3>How evidence is handled</h3>
            <p>
              We read full articles, rank their passages, and validate citation
              quotes against extracted text. Model-detected disagreements are
              candidates for your review. Neither quote matching nor source
              count establishes factual truth.
            </p>
            <div className="dialog-footer">
              <ShieldCheck size={15} />
              <span>
                Runtime figures are measured per run. Configured hardware is
                never presented as verified execution.
              </span>
            </div>
          </dialog>
        </div>
      )}
    </div>
  );
}

function LayersIcon() {
  return <AudioLines size={14} />;
}
