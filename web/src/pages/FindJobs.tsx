import { useState } from "react";
import { api, RunInfo, Status } from "../api";
import { Badge, Notice, RunLog, Section, fitTone, useAsync } from "../components/ui";
import { go } from "../App";

type Row = Record<string, string>;

export default function FindJobs({ status, onChange }: { status: Status; onChange: () => void }) {
  const listings = useAsync(() => api.get<{ total: number; counts: Record<string, number>; rows: Row[] }>("/api/scout"));
  const runs = useAsync(() => api.get<RunInfo[]>("/api/runs"));
  const live = status.running.find((r) => r.kind === "scout");
  const last = runs.data?.find((r) => r.kind === "scout");
  const [runId, setRunId] = useState<string | null>(live?.id ?? last?.id ?? null);
  const [err, setErr] = useState("");
  const [show, setShow] = useState("best");

  const start = async () => {
    setErr("");
    try {
      const r = await api.post<{ run: string }>("/api/runs/scout");
      setRunId(r.run);
      onChange();
    } catch (e) { setErr((e as Error).message); }
  };
  const rows = (listings.data?.rows ?? []).filter((r) =>
    show === "all" || (show === "best" ? ["generated", "promoted", "held", "failed"].includes(r.status) || r.fit === "stretch" : r.status === show));
  const busy = status.running.some((r) => r.kind === "scout" || r.kind === "generate");
  const shownRun = runId ?? live?.id ?? last?.id ?? null;

  return (
    <>
      <div className="page-head">
        <div><div className="kicker">Scout</div><h1>Find jobs</h1></div>
        <button className="btn btn-big" disabled={busy || !status.engine} onClick={start}>{busy ? "Running..." : "Find jobs now"}</button>
      </div>
      <div className="hero">
        <p style={{ maxWidth: 680 }}>
          Searches your <a href="#/sites">job sites</a> (and the web, if you allow it in <a href="#/preferences">preferences</a>),
          drops anything irrelevant, too senior, too old or already seen, reads each remaining ad, scores it against your facts,
          and writes a tailored CV and cover letter for the best ones. A full run can take 20 to 60 minutes; you can leave this page.
        </p>
        <p className="muted small" style={{ margin: 0 }}>
          The scout checks robots.txt and spaces out its requests. Only add sites whose terms allow automated access. See DISCLAIMER.md.
        </p>
      </div>
      {err && <Notice kind="error">{err}</Notice>}
      {shownRun && <Section title="Latest run"><RunLog runId={shownRun} onDone={() => { listings.reload(); runs.reload(); onChange(); }} /></Section>}

      <Section title={`This run's listings (${listings.data?.total ?? 0})`}
        actions={<select value={show} onChange={(e) => setShow(e.target.value)} style={{ width: 180 }}>
          <option value="best">Best and stretch</option><option value="all">Everything</option>
          <option value="skipped">Skipped</option><option value="below threshold">Below threshold</option>
        </select>}>
        {listings.data && Object.keys(listings.data.counts).length > 0 && (
          <div className="row gap wrap" style={{ marginBottom: 12 }}>
            {Object.entries(listings.data.counts).map(([k, v]) => <Badge key={k}>{k}: {v}</Badge>)}
          </div>)}
        {!rows.length && <div className="empty">No listings to show yet.</div>}
        {rows.length > 0 && (
          <table className="table">
            <thead><tr><th>Job</th><th>Fit</th><th>Why</th><th>Status</th><th></th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}>
                <td><b>{r.company || "?"}</b><div className="muted small">{r.title}</div></td>
                <td>{r.fit && <Badge tone={fitTone(r.fit)}>{r.fit}</Badge>}</td>
                <td className="small">{r.reason}</td>
                <td><Badge>{r.status}</Badge></td>
                <td className="row gap">
                  <a className="small" href={r.link} target="_blank" rel="noreferrer">ad</a>
                  {r.job_folder && <button className="linkbtn small" onClick={() => go(`applications/${r.job_folder}`)}>application</button>}
                </td>
              </tr>))}</tbody>
          </table>)}
        <p className="muted small" style={{ marginTop: 10 }}>
          Want one that was held back or scored as a stretch? Open its ad, copy the page and paste it on the Home page.
        </p>
      </Section>
    </>
  );
}
