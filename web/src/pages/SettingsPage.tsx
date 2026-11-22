import { useEffect, useState } from "react";
import { api, Status } from "../api";
import { Field, Notice, Section, useAsync } from "../components/ui";

type Settings = { engine: string; model: string; max_parallel: number; api_key: string };

/** Choose and test the Claude engine. Used here and in setup. */
export function EngineSettings({ status, onChange }: { status: Status; onChange: () => void }) {
  const { data, reload } = useAsync(() => api.get<Settings>("/api/settings"));
  const [engine, setEngine] = useState("auto");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [test, setTest] = useState<{ ok: boolean; error: string; engine?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) { setEngine(data.engine); setModel(data.model); } }, [data]);

  const save = async (patch: Partial<Settings>) => { await api.put("/api/settings", patch); await reload(); onChange(); };
  const runTest = async () => {
    setBusy(true);
    setTest(null);
    try { setTest(await api.post("/api/engine/test")); } catch (e) { setTest({ ok: false, error: (e as Error).message }); }
    setBusy(false);
  };
  const pick = (e: string) => { setEngine(e); save({ engine: e }); setTest(null); };

  return (
    <div className="stack">
      <div className="grid2">
        <div className={`choice ${engine !== "api" ? "on" : ""}`} onClick={() => pick("claude-code")}>
          <h3>Claude Code {status.claude_cli ? "(found)" : "(not installed)"}</h3>
          <div className="small muted">Uses your Claude Code login: a Claude subscription or your own API key. Recommended if you already use Claude Code.</div>
          {!status.claude_cli && <div className="small" style={{ marginTop: 6 }}>Install: <code>npm install -g @anthropic-ai/claude-code</code>, run <code>claude</code> once to log in, then restart this app.</div>}
        </div>
        <div className={`choice ${engine === "api" ? "on" : ""}`} onClick={() => pick("api")}>
          <h3>Claude API key {status.api_key ? `(${status.api_key})` : ""} <span className="badge badge-warn">experimental</span></h3>
          <div className="small muted">Pay-as-you-go from console.anthropic.com, billed per use by Anthropic. Nothing else to install.</div>
        </div>
      </div>
      {engine === "api" && (
        <div className="row gap">
          <input type="password" placeholder={status.api_key ? `Saved key ${status.api_key}. Paste a new one to replace it.` : "sk-ant-..."} value={key} onChange={(e) => setKey(e.target.value)} />
          <button className="btn" disabled={!key.trim()} onClick={async () => { await save({ api_key: key.trim() } as Partial<Settings>); setKey(""); }}>Save key</button>
        </div>)}
      <Field label="Model (optional)" hint={engine === "api" ? "Blank uses claude-opus-5-5." : "Blank uses your Claude Code default. Examples: opus, sonnet."}>
        <div className="row gap">
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="default" />
          <button className="btn btn-ghost" onClick={() => save({ model })}>Save</button>
        </div>
      </Field>
      <div className="row gap">
        <button className="btn" disabled={busy || !status.engine} onClick={runTest}>{busy ? "Testing..." : "Test connection"}</button>
        {!status.engine && <span className="muted small">Set up one of the options above first.</span>}
      </div>
      {test && (test.ok ? <Notice kind="ok">Connected via {test.engine === "api" ? "the Claude API" : "Claude Code"}.</Notice>
        : <Notice kind="error">{test.error || "No reply."}</Notice>)}
    </div>
  );
}

export default function SettingsPage({ status, onChange }: { status: Status; onChange: () => void }) {
  const { data, reload } = useAsync(() => api.get<Settings>("/api/settings"));
  const [parallel, setParallel] = useState(3);
  useEffect(() => { if (data) setParallel(data.max_parallel); }, [data]);
  return (
    <>
      <div className="page-head"><div><div className="kicker">Set up</div><h1>Settings</h1></div></div>
      <Section title="Claude connection"><EngineSettings status={status} onChange={onChange} /></Section>
      <Section title="Speed">
        <Field label="Applications generated at once" hint="Higher is faster but uses your Claude limits more quickly.">
          <div className="row gap">
            <input type="number" min={1} max={8} value={parallel} onChange={(e) => setParallel(Number(e.target.value))} style={{ width: 100 }} />
            <button className="btn btn-ghost" onClick={async () => { await api.put("/api/settings", { max_parallel: parallel }); reload(); }}>Save</button>
          </div>
        </Field>
      </Section>
      <Section title="Your data">
        <p>Everything personal (profile, CV, settings, applications, tracker) is stored on this computer in:</p>
        <p className="mono small">{status.data_dir}</p>
        <p className="muted small">This folder is excluded from git. Back it up if you care about your history. Job ads and your facts are sent to Claude when generating applications.</p>
        {!status.chromium && <Notice kind="error">The PDF browser (Chromium) is missing. Run <code>./start.sh</code> again, or <code>.venv/bin/playwright install chromium</code>.</Notice>}
      </Section>
      <Section title="Responsible use">
        <p className="small">You accepted the disclaimer during setup. Read it any time in <code>DISCLAIMER.md</code>. In short: check each site's terms before scraping it, keep request volumes low, and review every application before you send it.</p>
      </Section>
    </>
  );
}
