import { ReactNode, useEffect, useRef, useState } from "react";
import { api, LogLine, RunInfo } from "../api";

export function Section({ title, kicker, children, actions }: {
  title: string; kicker?: string; children: ReactNode; actions?: ReactNode;
}) {
  return (
    <section className="section">
      <header className="section-head">
        <div>
          {kicker && <div className="kicker">{kicker}</div>}
          <h2>{title}</h2>
        </div>
        {actions && <div className="row gap">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warn" | "error" | "ok"; children: ReactNode }) {
  return <div className={`notice notice-${kind}`}>{children}</div>;
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

/** Text area that edits a list of strings, one per line. */
export function LinesInput({ value, onChange, rows = 4, placeholder }: {
  value: string[] | undefined; onChange: (v: string[]) => void; rows?: number; placeholder?: string;
}) {
  const [text, setText] = useState((value ?? []).join("\n"));
  useEffect(() => setText((value ?? []).join("\n")), [JSON.stringify(value)]); // eslint-disable-line
  return (
    <textarea rows={rows} value={text} placeholder={placeholder}
      onChange={(e) => { setText(e.target.value); onChange(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean)); }} />
  );
}

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone ?? "plain"}`}>{children}</span>;
}

export function fitTone(fit: string) {
  return { strong: "fill", decent: "outline", stretch: "warn", skip: "muted" }[fit] ?? "plain";
}

export function statusTone(status: string) {
  return ({ ready: "outline", applied: "fill", "followed up": "fill", interview: "ok", offer: "ok",
    rejected: "muted", withdrawn: "muted", running: "fill", done: "ok", failed: "error", stopped: "muted",
    interrupted: "warn" } as Record<string, string>)[status] ?? "plain";
}

/** Polls a run and shows its log until it finishes. */
export function useRun(runId: string | null, onDone?: (run: RunInfo) => void) {
  const [run, setRun] = useState<RunInfo | null>(null);
  const [lines, setLines] = useState<LogLine[]>([]);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  useEffect(() => {
    if (!runId) return;
    let since = 0;
    let stopped = false;
    let timer: number;
    setLines([]);
    setRun(null);
    const tick = async () => {
      try {
        const r = await api.get<RunInfo>(`/api/runs/${runId}?since=${since}`);
        if (stopped) return;
        since += r.log.length;
        if (r.log.length) setLines((old) => [...old, ...r.log]);
        setRun(r);
        if (r.status === "running") timer = window.setTimeout(tick, 1200);
        else doneRef.current?.(r);
      } catch {
        if (!stopped) timer = window.setTimeout(tick, 3000);
      }
    };
    tick();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [runId]);
  return { run, lines };
}

export function RunLog({ runId, onDone, compact }: { runId: string | null; onDone?: (run: RunInfo) => void; compact?: boolean }) {
  const { run, lines } = useRun(runId, onDone);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }); }, [lines.length]);
  if (!runId) return null;
  return (
    <div className={`runlog ${compact ? "runlog-compact" : ""}`}>
      <div className="runlog-head">
        <span className="mono">{run?.title ?? "Starting..."}</span>
        <span className="row gap">
          {run && <Badge tone={statusTone(run.status)}>{run.status}</Badge>}
          {run?.status === "running" && (
            <button className="btn btn-small btn-ghost-dark" onClick={() => api.post(`/api/runs/${runId}/stop`)}>Stop</button>
          )}
        </span>
      </div>
      <div className="runlog-body" ref={box}>
        {lines.map((l, i) => (
          <div key={i} className={`logline log-${l.kind}`}><span className="log-t">{l.t}</span>{l.text}</div>
        ))}
        {run?.status === "running" && <div className="logline log-info"><span className="spinner" /> working</div>}
        {run?.error && <div className="logline log-error">{run.error}</div>}
      </div>
    </div>
  );
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const reload = async () => {
    setLoading(true);
    try { setData(await fn()); setError(""); } catch (e) { setError((e as Error).message); }
    setLoading(false);
  };
  useEffect(() => { reload(); }, deps); // eslint-disable-line
  return { data, setData, error, loading, reload };
}

export function SaveBar({ dirty, saving, onSave, message }: { dirty: boolean; saving: boolean; onSave: () => void; message?: string }) {
  return (
    <div className={`savebar ${dirty ? "savebar-dirty" : ""}`}>
      <span>{message || (dirty ? "Unsaved changes" : "All changes saved")}</span>
      <button className="btn" disabled={!dirty || saving} onClick={onSave}>{saving ? "Saving..." : "Save"}</button>
    </div>
  );
}
