import { useState } from "react";
import { api, fileUrl } from "../api";
import { Badge, Notice, fitTone, useAsync } from "../components/ui";
import Chat from "../components/Chat";
import { go } from "../App";

type Detail = {
  folder: string;
  content: Record<string, unknown>;
  brief: string;
  apply: string;
  job_text: string;
  files: Record<string, string>;
  tracker: Record<string, string> | null;
};

const STATUSES = ["ready", "applied", "followed up", "interview", "offer", "rejected", "withdrawn"];

export default function ApplicationDetail({ folder }: { folder: string }) {
  const { data, error, reload } = useAsync(() => api.get<Detail>(`/api/applications/${encodeURIComponent(folder)}`), [folder]);
  const [tab, setTab] = useState("letter");
  const [bust, setBust] = useState(Date.now());
  const [msg, setMsg] = useState("");

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!data) return <span className="spinner" />;
  const c = data.content as Record<string, string>;
  const status = data.tracker?.status ?? "not logged";

  const setStatus = async (s: string) => {
    await api.put(`/api/applications/${encodeURIComponent(folder)}/status`, { status: s });
    reload();
  };
  const rerender = async () => {
    setMsg("Rendering...");
    const r = await api.post<{ ok: boolean; errors: string[] }>(`/api/applications/${encodeURIComponent(folder)}/render`);
    setMsg(r.ok ? "PDFs updated." : r.errors.join("; "));
    setBust(Date.now());
  };
  const remove = async () => {
    if (!confirm(`Delete the application for ${c.company}? This removes its folder and tracker row.`)) return;
    await api.del(`/api/applications/${encodeURIComponent(folder)}`);
    go("applications");
  };
  const pdf = (key: string) => data.files[key] ? (
    <iframe className="pdf" title={key} src={`${fileUrl(folder, data.files[key])}?v=${bust}#view=FitH`} />
  ) : <Notice kind="warn">Not rendered yet. Ask for a change in the chat, or press Re-render.</Notice>;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker"><a href="#/applications">Applications</a> / {data.folder}</div>
          <h1>{c.company}</h1>
          <div className="row gap" style={{ marginTop: 6 }}>
            <span className="muted">{c.role}</span>
            {c.fit && <Badge tone={fitTone(c.fit)}>{c.fit} fit</Badge>}
            {c.location && <span className="muted small">{c.location}</span>}
          </div>
        </div>
        <div className="row gap">
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 150 }}>
            {[...new Set([...STATUSES, status])].map((s) => <option key={s}>{s}</option>)}
          </select>
          {c.url && <a className="btn btn-ghost" href={c.url} target="_blank" rel="noreferrer">Open job ad</a>}
        </div>
      </div>

      <div className="detail">
        <div>
          {Array.isArray(data.content.todo) && (data.content.todo as string[]).length > 0 && (
            <Notice kind="warn"><b>Before sending:</b> {(data.content.todo as string[]).join(" · ")}</Notice>)}
          <div className="tabs">
            {[["letter", "Cover letter"], ["cv", "CV"], ["apply", "How to apply"], ["brief", "Research"], ["job", "Job ad"]].map(([k, l]) => (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>))}
          </div>
          {tab === "letter" && pdf("letter")}
          {tab === "cv" && pdf("cv")}
          {tab === "apply" && <div className="prose">{data.apply || "Not written yet."}</div>}
          {tab === "brief" && <div className="prose">{data.brief || "No research notes."}</div>}
          {tab === "job" && <div className="prose">{data.job_text}</div>}
          <div className="row gap wrap" style={{ marginTop: 12 }}>
            {Object.entries(data.files).map(([k, name]) => (
              <a key={k} className="btn btn-small btn-ghost" href={fileUrl(folder, name)} download>{name}</a>))}
            <button className="btn btn-small btn-ghost" onClick={rerender}>Re-render</button>
            <button className="btn btn-small btn-danger" onClick={remove}>Delete</button>
            <span className="muted small">{msg}</span>
          </div>
        </div>
        <Chat job={folder} title="Edit with Claude" onEdited={() => { setBust(Date.now()); reload(); }}
          hints={["Make paragraph 2 shorter", "Make the tone a little warmer", "Lead with my most relevant project",
            "Draft a short follow-up email for this application"]} />
      </div>
    </>
  );
}
