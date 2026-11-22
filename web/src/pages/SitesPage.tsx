import { useEffect, useState } from "react";
import { api, RunInfo, Site, SiteType } from "../api";
import { Badge, Field, LinesInput, Notice, RunLog, SaveBar, Section, useAsync } from "../components/ui";

type TestResult = { ok: boolean; error: string; count: number; sample: { company: string; title: string; location: string; link: string }[] };
const LIST_FIELDS = new Set(["boards", "companies"]);

type FixResult = { ok: boolean; site: Site; test: TestResult | null; message: string };

function SiteCard({ site, type: known, autoTest, onChange, onRemove }: {
  site: Site; type?: SiteType; autoTest?: boolean; onChange: (s: Site) => void; onRemove: () => void;
}) {
  const type = known ?? { label: `${site.type} (no longer supported)`, help: "This source type was removed. Delete it.", fields: {} };
  const [test, setTest] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [fixRun, setFixRun] = useState<string | null>(null);
  const [fixNote, setFixNote] = useState<{ ok: boolean; text: string } | null>(null);
  const run = async () => {
    setTesting(true);
    setTest(null);
    setFixNote(null);
    try { setTest(await api.post<TestResult>("/api/sites/test", site)); }
    catch (e) { setTest({ ok: false, error: (e as Error).message, count: 0, sample: [] }); }
    setTesting(false);
  };
  useEffect(() => { if (autoTest) run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const askClaude = async () => {
    setFixNote(null);
    try {
      const r = await api.post<{ run: string }>("/api/runs/site", { site, problem: test?.error || "Test found no job ads" });
      setFixRun(r.run);
    } catch (e) { setFixNote({ ok: false, text: (e as Error).message }); }
  };
  const fixDone = (r: RunInfo) => {
    const out = r.result as unknown as FixResult | undefined;
    if (out?.ok) {
      onChange(out.site);
      setTest(out.test);
      setFixNote({ ok: true, text: "Claude found settings that work. Press Save to keep them." });
    } else {
      setFixNote({ ok: false, text: out?.message || r.error || `The run ${r.status}.` });
    }
    setFixRun(null);
  };
  const blocked = !!test?.error.includes("robots.txt");
  const canFix = site.type === "generic" && !!(site.url || site.search_url) && !blocked;
  return (
    <div className={`site-card ${site.enabled ? "" : "off"}`}>
      <div className="row gap" style={{ marginBottom: 10 }}>
        <label className="check"><input type="checkbox" checked={site.enabled} onChange={(e) => onChange({ ...site, enabled: e.target.checked })} /></label>
        <input value={site.name} onChange={(e) => onChange({ ...site, name: e.target.value })} style={{ fontWeight: 700, maxWidth: 340 }} />
        <Badge>{type.label}</Badge>
        <span className="grow" />
        <button className="btn btn-small btn-ghost" disabled={testing || !!fixRun} onClick={run}>{testing ? "Testing..." : "Test"}</button>
        {canFix && <button className="btn btn-small btn-ghost" disabled={testing || !!fixRun} onClick={askClaude}
          title="Claude reads the page and works out where the job ads are. The result is tested before you can keep it.">Ask Claude to fix it</button>}
        <button className="btn btn-small btn-danger" onClick={onRemove}>Remove</button>
      </div>
      <p className="muted small">{type.help}</p>
      <div className="stack">
        {Object.entries(type.fields).map(([key, label]) => (
          <Field key={key} label={label}>
            {LIST_FIELDS.has(key)
              ? <LinesInput value={(site[key] as string[]) ?? []} onChange={(v) => onChange({ ...site, [key]: v })} rows={3} />
              : <input value={String(site[key] ?? "")} onChange={(e) => onChange({ ...site, [key]: e.target.value })} />}
          </Field>))}
      </div>
      {fixRun && <div style={{ marginTop: 12 }}><RunLog runId={fixRun} onDone={fixDone} compact /></div>}
      {fixNote && <div style={{ marginTop: 12 }}><Notice kind={fixNote.ok ? "ok" : "warn"}>{fixNote.text}</Notice></div>}
      {test && (
        <div style={{ marginTop: 12 }}>
          {test.ok ? <Notice kind="ok">Found {test.count} listings (before your filters). First few:</Notice>
            : <Notice kind="error">{blocked ? `${test.error}. This site does not allow automated access, so it cannot be used. Paste its job ads on Home instead.`
              : `${test.error}${canFix ? ". Press Ask Claude to fix it to let Claude work out the settings." : ""}`}</Notice>}
          {test.sample.length > 0 && (
            <table className="table"><tbody>{test.sample.slice(0, 8).map((s, i) => (
              <tr key={i}><td><b>{s.company || "?"}</b> · {s.title}</td><td className="small muted">{s.location}</td>
                <td><a className="small" href={s.link} target="_blank" rel="noreferrer">open</a></td></tr>))}</tbody></table>)}
        </div>)}
    </div>
  );
}

/** Editable list of job sites, used here and in setup. */
export function SitesEditor({ sites, types, onChange }: { sites: Site[]; types: Record<string, SiteType>; onChange: (s: Site[]) => void }) {
  const [newType, setNewType] = useState("greenhouse");
  const [address, setAddress] = useState("");
  const [adding, setAdding] = useState(false);
  const [addErr, setAddErr] = useState("");
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const addType = () => onChange([...sites, { name: types[newType].label, type: newType, enabled: true }]);
  const addAddress = async () => {
    setAdding(true);
    setAddErr("");
    try {
      const site = await api.post<Site>("/api/sites/resolve", { url: address.trim() });
      setFresh((f) => new Set(f).add(site.id as string));
      onChange([...sites, site]);
      setAddress("");
    } catch (e) { setAddErr((e as Error).message); }
    setAdding(false);
  };
  return (
    <div className="stack">
      {!sites.length && <div className="empty">No sites yet. Add one below.</div>}
      {sites.map((s, i) => (
        <SiteCard key={s.id ?? i} site={s} type={types[s.type]} autoTest={!!s.id && fresh.has(s.id)}
          onChange={(n) => onChange(sites.map((x, j) => (j === i ? n : x)))}
          onRemove={() => onChange(sites.filter((_, j) => j !== i))} />))}
      <div className="card stack">
        <div className="row gap wrap">
          <b>Add a job site:</b>
          <input value={address} onChange={(e) => setAddress(e.target.value)} style={{ flex: 1, minWidth: 260 }}
            placeholder="Paste its address, e.g. a search results page"
            onKeyDown={(e) => { if (e.key === "Enter" && address.trim()) addAddress(); }} />
          <button className="btn btn-small" disabled={!address.trim() || adding} onClick={addAddress}>{adding ? "Checking..." : "Add"}</button>
        </div>
        <span className="muted small">Any job site, anywhere. It is tested straight away; if no jobs are found, Claude can work out the settings.
          Company careers pages on Greenhouse, Lever and Ashby, and job feeds, are recognised from their address.</span>
        {addErr && <Notice kind="error">{addErr}</Notice>}
        <details>
          <summary className="small muted">Add by type instead</summary>
          <div className="row gap wrap" style={{ marginTop: 8 }}>
            <select value={newType} onChange={(e) => setNewType(e.target.value)} style={{ width: 280 }}>
              {Object.entries(types).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}
            </select>
            <button className="btn btn-small btn-ghost" onClick={addType}>Add</button>
            <span className="muted small">{types[newType]?.help}</span>
          </div>
        </details>
      </div>
    </div>
  );
}

export default function SitesPage() {
  const { data } = useAsync(() => api.get<{ sites: Site[]; types: Record<string, SiteType> }>("/api/sites"));
  const [sites, setSites] = useState<Site[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { if (data) setSites(data.sites); }, [data]);
  if (!sites || !data) return <span className="spinner" />;
  const save = async () => {
    setSaving(true);
    setErr("");
    try { setSites((await api.put<{ sites: Site[] }>("/api/sites", sites)).sites); setDirty(false); }
    catch (e) { setErr((e as Error).message); }
    setSaving(false);
  };
  return (
    <>
      <div className="page-head"><div><div className="kicker">Set up</div><h1>Job sites</h1></div></div>
      <Notice>
        Paste the address of any job site. If its robots.txt allows automated access, the scout reads it; if no jobs are
        found, <b>Ask Claude to fix it</b> works out the right settings. robots.txt is not the whole story: also check the
        site's terms, and only add sites that allow automated access (see DISCLAIMER.md).
      </Notice>
      {err && <Notice kind="error">{err}</Notice>}
      <Section title="Where the scout looks">
        <SitesEditor sites={sites} types={data.types} onChange={(s) => { setSites(s); setDirty(true); }} />
      </Section>
      <SaveBar dirty={dirty} saving={saving} onSave={save} />
    </>
  );
}
