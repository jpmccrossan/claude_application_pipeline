import { useState } from "react";
import { api, Application, Status, TrackerRow } from "../api";
import { Badge, Notice, RunLog, Section, fitTone, useAsync } from "../components/ui";
import { go } from "../App";

type Inbox = { name: string; chars: number; preview: string }[];

export default function Home({ status, onChange }: { status: Status; onChange: () => void }) {
  const inbox = useAsync(() => api.get<Inbox>("/api/inbox"));
  const apps = useAsync(() => api.get<{ applications: Application[]; followups: { ready: TrackerRow[]; due: TrackerRow[] } }>("/api/applications"));
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [runId, setRunId] = useState<string | null>(status.running.find((r) => r.kind === "generate")?.id ?? null);

  const add = async () => {
    setErr("");
    try {
      await api.post("/api/inbox", { text });
      setText("");
      inbox.reload();
      onChange();
    } catch (e) { setErr((e as Error).message); }
  };
  const generate = async () => {
    setErr("");
    try {
      const r = await api.post<{ run: string }>("/api/runs/generate");
      setRunId(r.run);
      onChange();
    } catch (e) { setErr((e as Error).message); }
  };
  const remove = async (name: string) => { await api.del(`/api/inbox/${encodeURIComponent(name)}`); inbox.reload(); onChange(); };

  const list = apps.data?.applications ?? [];
  const busy = status.running.some((r) => r.kind === "generate" || r.kind === "scout");

  return (
    <>
      <div className="page-head">
        <div><div className="kicker">Home</div><h1>New applications</h1></div>
        <button className="btn btn-ghost" onClick={() => go("find")}>Find jobs for me</button>
      </div>

      {!status.engine && <Notice kind="error">No Claude engine is available. Open <a href="#/settings">Settings</a> to connect Claude Code or add an API key.</Notice>}

      <div className="grid2">
        <Section kicker="Step 1" title="Paste a job ad">
          <div className="stack">
            <textarea rows={10} value={text} onChange={(e) => setText(e.target.value)}
              placeholder={"Paste the whole job ad here. Copying the full page (Ctrl+A, Ctrl+C) is fine: the menus and other junk are ignored.\n\nTip: put the job's link on the first line so it ends up in your tracker."} />
            {err && <Notice kind="error">{err}</Notice>}
            <div className="row gap"><button className="btn" disabled={text.trim().length < 50} onClick={add}>Add to inbox</button>
              <span className="muted small">Add as many as you like, then generate them together.</span></div>
          </div>
        </Section>

        <Section kicker="Step 2" title={`Inbox (${inbox.data?.length ?? 0})`}
          actions={<button className="btn" disabled={!inbox.data?.length || busy || !status.engine} onClick={generate}>
            Generate {inbox.data?.length || ""} application{inbox.data?.length === 1 ? "" : "s"}</button>}>
          {!inbox.data?.length && <div className="empty">Nothing waiting. Paste a job ad, or let <a href="#/find">Find jobs</a> fill this for you.</div>}
          <div className="stack">
            {inbox.data?.map((f) => (
              <div key={f.name} className="card row gap">
                <div className="grow"><div className="mono small">{f.name}</div><div className="muted small">{f.preview.slice(0, 140)}...</div></div>
                <button className="btn btn-small btn-danger" onClick={() => remove(f.name)}>Remove</button>
              </div>
            ))}
          </div>
          <p className="muted small" style={{ marginTop: 12 }}>
            Each ad gets its own research and writing pass. Expect a few minutes per application; several run at once.
          </p>
        </Section>
      </div>

      {runId && <Section title="Progress"><RunLog runId={runId} onDone={() => { inbox.reload(); apps.reload(); onChange(); }} /></Section>}

      {(apps.data?.followups.due.length ?? 0) > 0 && (
        <Section kicker="Follow up" title="Waiting more than 10 days">
          <table className="table"><tbody>
            {apps.data!.followups.due.map((r) => (
              <tr key={r.folder} className="clickable" onClick={() => go(`applications/${r.folder}`)}>
                <td><b>{r.company}</b> · {r.role}</td><td className="muted">applied {r.date}</td>
                <td>{r.contact_email || r.hiring_manager || "no contact recorded"}</td>
              </tr>))}
          </tbody></table>
          <p className="muted small" style={{ marginTop: 10 }}>Open one and ask Claude in the chat to draft a short follow-up email.</p>
        </Section>
      )}

      <Section kicker="Latest" title="Recent applications" actions={<a href="#/applications">See all</a>}>
        {!list.length && <div className="empty">No applications yet.</div>}
        <table className="table"><tbody>
          {list.slice(0, 6).map((a) => (
            <tr key={a.folder} className="clickable" onClick={() => go(`applications/${a.folder}`)}>
              <td><b>{a.company}</b><div className="muted small">{a.role}</div></td>
              <td>{a.fit && <Badge tone={fitTone(a.fit)}>{a.fit}</Badge>}</td>
              <td><Badge>{a.status}</Badge></td>
              <td className="muted small">{a.deadline ? `deadline ${a.deadline}` : ""}</td>
            </tr>))}
        </tbody></table>
      </Section>
    </>
  );
}
