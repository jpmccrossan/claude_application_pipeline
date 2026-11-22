import { useState } from "react";
import { api, Application } from "../api";
import { Badge, Section, fitTone, statusTone, useAsync } from "../components/ui";
import { go } from "../App";

export default function Applications() {
  const { data, reload } = useAsync(() => api.get<{ applications: Application[]; statuses: string[] }>("/api/applications"));
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const list = (data?.applications ?? []).filter((a) =>
    (filter === "all" || a.status === filter) && `${a.company} ${a.role}`.toLowerCase().includes(q.toLowerCase()));

  const setStatus = async (folder: string, status: string) => {
    await api.put(`/api/applications/${encodeURIComponent(folder)}/status`, { status });
    reload();
  };
  const counts = (data?.applications ?? []).reduce<Record<string, number>>((m, a) => ({ ...m, [a.status]: (m[a.status] ?? 0) + 1 }), {});

  return (
    <>
      <div className="page-head">
        <div><div className="kicker">Tracker</div><h1>Applications</h1></div>
        <div className="row gap"><input placeholder="Search company or role" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 240 }} /></div>
      </div>
      <div className="row gap wrap" style={{ marginBottom: 14 }}>
        {["all", ...(data?.statuses ?? [])].map((s) => (
          <button key={s} className={`btn btn-small ${filter === s ? "" : "btn-ghost"}`} onClick={() => setFilter(s)}>
            {s} {s === "all" ? data?.applications.length ?? 0 : counts[s] ?? 0}
          </button>))}
      </div>
      <Section title={`${list.length} application${list.length === 1 ? "" : "s"}`}>
        {!list.length && <div className="empty">Nothing here yet.</div>}
        {list.length > 0 && (
          <table className="table">
            <thead><tr><th>Company and role</th><th>Fit</th><th>Location</th><th>Deadline</th><th>Status</th><th>Made</th></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.folder} className="clickable" onClick={() => go(`applications/${a.folder}`)}>
                  <td><b>{a.company}</b><div className="muted small">{a.role}</div></td>
                  <td>{a.fit && <Badge tone={fitTone(a.fit)}>{a.fit}</Badge>}</td>
                  <td className="small">{a.location}</td>
                  <td className="small">{a.deadline || <span className="muted">none</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select value={a.status} onChange={(e) => setStatus(a.folder, e.target.value)} className={`badge-${statusTone(a.status)}`}>
                      {[...new Set([...(data?.statuses ?? []), a.status])].map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="muted small mono">{a.day}</td>
                </tr>))}
            </tbody>
          </table>)}
        <p className="muted small" style={{ marginTop: 12 }}>
          New applications start as <b>ready</b>. Once you have sent one, set it to <b>applied</b>: that starts a 10-day follow-up reminder.
        </p>
      </Section>
    </>
  );
}
