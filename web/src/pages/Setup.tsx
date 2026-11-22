import { ReactNode, useEffect, useRef, useState } from "react";
import { api, Site, SiteType, Status } from "../api";
import { Field, Notice, RunLog, useAsync } from "../components/ui";
import { EngineSettings } from "./SettingsPage";
import { Targets, TargetsForm } from "./Preferences";
import { SitesEditor } from "./SitesPage";
import { CvPreview } from "./ProfilePage";

const STEPS = ["Welcome", "Connect Claude", "Your CV", "Check your profile", "Job preferences", "Job sites", "Done"];

/** Minimal Markdown for the disclaimer: headings, bullets, paragraphs, **bold**. */
function Md({ text }: { text: string }) {
  const bold = (s: string) => s.split(/\*\*(.+?)\*\*/g).map((p, i) => (i % 2 ? <b key={i}>{p}</b> : p));
  const out: ReactNode[] = [];
  let para: string[] = [];
  let items: string[] = [];
  const flush = () => {
    if (para.length) out.push(<p key={out.length}>{bold(para.join(" "))}</p>);
    if (items.length) out.push(<ul key={out.length}>{items.map((l, j) => <li key={j}>{bold(l)}</li>)}</ul>);
    para = [];
    items = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) { flush(); continue; }
    if (line.startsWith("# ")) { flush(); out.push(<h2 key={out.length}>{line.slice(2)}</h2>); continue; }
    if (line.startsWith("## ")) { flush(); out.push(<h3 key={out.length}>{line.slice(3)}</h3>); continue; }
    if (line.startsWith("- ")) { if (para.length) flush(); items.push(line.slice(2)); continue; }
    if (items.length) items[items.length - 1] += " " + line; else para.push(line);
  }
  flush();
  return <>{out}</>;
}

export default function Setup({ status, onDone }: { status: Status; onDone: () => void }) {
  const [step, setStep] = useState(status.disclaimer_accepted ? (status.engine ? (status.has_profile ? 3 : 2) : 1) : 0);
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  let body: ReactNode;
  switch (step) {
    case 0: body = <Welcome onAccept={async () => { await api.put("/api/settings", { disclaimer_accepted: true }); onDone(); next(); }} />; break;
    case 1: body = <StepEngine status={status} onChange={onDone} onNext={next} onBack={back} />; break;
    case 2: body = <StepCv onNext={next} onBack={back} />; break;
    case 3: body = <StepReview onNext={next} onBack={back} onRebuild={() => setStep(2)} />; break;
    case 4: body = <StepTargets onNext={next} onBack={back} />; break;
    case 5: body = <StepSites onNext={next} onBack={back} />; break;
    default: body = <StepDone onBack={back} onFinish={async () => { await api.put("/api/settings", { onboarded: true }); onDone(); }} />;
  }
  return (
    <div className="setup">
      <div className="setup-card">
        <div className="setup-bar">
          <span className="dot" style={{ background: "#2036d9" }} /><span className="dot" style={{ background: "#e9ecfa" }} /><span className="dot" style={{ background: "#9a99a4" }} />
          <span className="mono small" style={{ marginLeft: 6 }}>Application Pipeline · setup</span>
        </div>
        <div className="setup-steps">
          {STEPS.map((s, i) => <div key={s} className={i === step ? "on" : i < step ? "done" : ""}>{i + 1}. {s}</div>)}
        </div>
        <div className="setup-body">{body}</div>
      </div>
    </div>
  );
}

function Foot({ onBack, children }: { onBack?: () => void; children: ReactNode }) {
  return <div className="setup-foot">{onBack ? <button className="btn btn-ghost" onClick={onBack}>Back</button> : <span />}<div className="row gap">{children}</div></div>;
}

function Welcome({ onAccept }: { onAccept: () => void }) {
  const { data } = useAsync(() => api.get<{ text: string }>("/api/disclaimer"));
  const [ok, setOk] = useState(false);
  return (
    <>
      <div className="kicker">Welcome</div>
      <h1>Tailored job applications, written by Claude, checked against your real experience.</h1>
      <p style={{ marginTop: 14 }}>Upload your CV once. Then paste job ads (or let the app find them on the job sites you choose) and get a
        one-page CV and cover letter for each, researched and written around what that company needs, using only facts from your own CV.</p>
      <p className="muted">Setup takes about five minutes. First, please read this:</p>
      <div className="disclaimer">{data ? <Md text={data.text} /> : <span className="spinner" />}</div>
      <label className="check" style={{ marginTop: 14 }}>
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        I have read the disclaimer. I will check each job site's terms before adding it, use the app responsibly, and review every application before I send it.
      </label>
      <Foot><button className="btn btn-big" disabled={!ok} onClick={onAccept}>Accept and continue</button></Foot>
    </>
  );
}

function StepEngine({ status, onChange, onNext, onBack }: { status: Status; onChange: () => void; onNext: () => void; onBack: () => void }) {
  return (
    <>
      <div className="kicker">Step 2</div>
      <h1>Connect Claude</h1>
      <p className="muted" style={{ marginTop: 8 }}>The app needs Claude to research companies and write. Pick one:</p>
      <EngineSettings status={status} onChange={onChange} />
      <Foot onBack={onBack}><button className="btn btn-big" disabled={!status.engine} onClick={onNext}>Continue</button></Foot>
    </>
  );
}

function StepCv({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [cv, setCv] = useState<{ chars: number; preview: string } | null>(null);
  const [photo, setPhoto] = useState(false);
  const [err, setErr] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [d, setD] = useState({ name: "", email: "", phone: "", location: "", links: "", status_line: "", availability: "", spelling: "British English" });
  const cvRef = useRef<HTMLInputElement>(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const set = (k: string, v: string) => setD({ ...d, [k]: v });

  const uploadCv = async (f: File) => {
    setErr("");
    try { setCv(await api.upload("/api/profile/cv", f)); } catch (e) { setErr((e as Error).message); }
  };
  const uploadPhoto = async (f: File) => {
    try { await api.upload("/api/profile/photo", f); setPhoto(true); } catch (e) { setErr((e as Error).message); }
  };
  const build = async () => {
    setErr("");
    setFailed(false);
    try { setRunId((await api.post<{ run: string }>("/api/onboard", { details: d })).run); } catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      <div className="kicker">Step 3</div>
      <h1>Your CV</h1>
      <p className="muted" style={{ marginTop: 8 }}>Claude reads your CV and builds two things: your facts (everything true about you, the only source applications may use) and your CV layout.</p>
      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="drop" onClick={() => cvRef.current?.click()}>
          <h3>{cv ? "CV uploaded" : "Upload your CV"}</h3>
          <div className="muted small">{cv ? `${cv.chars.toLocaleString()} characters read. Click to replace.` : "PDF, Word (.docx) or text"}</div>
          <input ref={cvRef} type="file" hidden accept=".pdf,.docx,.txt,.md" onChange={(e) => e.target.files?.[0] && uploadCv(e.target.files[0])} />
        </div>
        <div className="drop" onClick={() => photoRef.current?.click()}>
          <h3>{photo ? "Photo added" : "Photo (optional)"}</h3>
          <div className="muted small">Shown on the CV. Leave it out where photos are not expected (UK, US).</div>
          <input ref={photoRef} type="file" hidden accept=".jpg,.jpeg,.png" onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])} />
        </div>
      </div>
      <h3 style={{ margin: "22px 0 10px" }}>Check your details <span className="muted small">(optional: anything blank is taken from your CV)</span></h3>
      <div className="grid2">
        <Field label="Full name"><input value={d.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Email"><input value={d.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Phone"><input value={d.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="City, country"><input value={d.location} onChange={(e) => set("location", e.target.value)} /></Field>
        <Field label="Links" hint="Website, GitHub, portfolio"><input value={d.links} onChange={(e) => set("links", e.target.value)} /></Field>
        <Field label="Spelling"><select value={d.spelling} onChange={(e) => set("spelling", e.target.value)}><option>British English</option><option>American English</option></select></Field>
        <Field label="Status line" hint='e.g. "Open to work · 2026" or "Available from March · 2026"'><input value={d.status_line} onChange={(e) => set("status_line", e.target.value)} /></Field>
        <Field label="Availability" hint="Notice period, right to work, relocation"><input value={d.availability} onChange={(e) => set("availability", e.target.value)} /></Field>
      </div>
      {err && <div style={{ marginTop: 14 }}><Notice kind="error">{err}</Notice></div>}
      {runId && <div style={{ marginTop: 16 }}><RunLog runId={runId} onDone={(r) => (r.status === "done" ? onNext() : setFailed(true))} /></div>}
      {failed && <Notice kind="error">Building the profile did not finish. Check the log above, then try again.</Notice>}
      <Foot onBack={onBack}>
        <button className="btn btn-big" disabled={!cv || (!!runId && !failed)} onClick={build}>{runId && !failed ? "Building..." : "Build my profile"}</button>
      </Foot>
    </>
  );
}

function StepReview({ onNext, onBack, onRebuild }: { onNext: () => void; onBack: () => void; onRebuild: () => void }) {
  const { data } = useAsync(() => api.get<{ facts: string; profile: Record<string, unknown> }>("/api/profile"));
  const [facts, setFacts] = useState("");
  const [bust, setBust] = useState(0);
  const [fit, setFit] = useState<{ ok: boolean; errors: string[] } | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (data) setFacts(data.facts); }, [data]);
  useEffect(() => { api.post<{ ok: boolean; errors: string[] }>("/api/profile/preview").then((r) => { setFit(r); setBust(Date.now()); }); }, []);
  const todos = facts.split("\n").filter((l) => l.includes("TODO")).length;
  const save = async () => { setSaving(true); await api.put("/api/profile", { facts }); setSaving(false); onNext(); };
  return (
    <>
      <div className="kicker">Step 4</div>
      <h1>Check your profile</h1>
      <p className="muted" style={{ marginTop: 8 }}>Read your facts carefully: applications can only say what is written here. Fix anything wrong now.
        {todos > 0 && <> There {todos === 1 ? "is" : "are"} <b>{todos} TODO question{todos === 1 ? "" : "s"}</b>: answering them (numbers, outcomes) makes letters much stronger, and you can do it later in Profile.</>}</p>
      {fit && !fit.ok && <Notice kind="warn">The default CV is a little long: {fit.errors.join("; ")}. Each application shortens it, but you can trim it later with Chat ("shorten my default bullets").</Notice>}
      <div className="grid2" style={{ marginTop: 12, alignItems: "start" }}>
        <Field label="facts.md"><textarea className="code" rows={28} value={facts} onChange={(e) => setFacts(e.target.value)} /></Field>
        <div><div className="field-label" style={{ marginBottom: 5 }}>CV preview (default wording)</div>{bust ? <CvPreview bust={bust} /> : <span className="spinner" />}</div>
      </div>
      <Foot onBack={onBack}>
        <button className="btn btn-ghost" onClick={onRebuild}>Rebuild from CV</button>
        <button className="btn btn-big" disabled={saving} onClick={save}>Looks right, continue</button>
      </Foot>
    </>
  );
}

function StepTargets({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { data } = useAsync(() => api.get<Targets>("/api/targets"));
  const [value, setValue] = useState<Targets | null>(null);
  useEffect(() => { if (data) setValue(data); }, [data]);
  if (!value) return <span className="spinner" />;
  return (
    <>
      <div className="kicker">Step 5</div>
      <h1>What are you looking for?</h1>
      <p className="muted" style={{ marginTop: 8 }}>Used by "Find jobs". You can change all of this later. The values below are examples: replace them with yours.</p>
      <div style={{ marginTop: 14 }}><TargetsForm value={value} onChange={setValue} /></div>
      <Foot onBack={onBack}><button className="btn btn-big" onClick={async () => { await api.put("/api/targets", value); onNext(); }}>Save and continue</button></Foot>
    </>
  );
}

function StepSites({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { data } = useAsync(() => api.get<{ sites: Site[]; types: Record<string, SiteType> }>("/api/sites"));
  const [sites, setSites] = useState<Site[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { if (data) setSites(data.sites); }, [data]);
  if (!sites || !data) return <span className="spinner" />;
  const save = async () => {
    try { await api.put("/api/sites", sites); onNext(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <>
      <div className="kicker">Step 6</div>
      <h1>Where should it look?</h1>
      <p className="muted" style={{ marginTop: 8 }}>Turn on the sources you want and press Test to check them. Company boards (Greenhouse, Lever, Ashby) use public job APIs: add the companies you like.
        You can skip this and only paste job ads yourself.</p>
      {err && <Notice kind="error">{err}</Notice>}
      <div style={{ marginTop: 14 }}><SitesEditor sites={sites} types={data.types} onChange={setSites} /></div>
      <Foot onBack={onBack}><button className="btn btn-big" onClick={save}>Save and continue</button></Foot>
    </>
  );
}

function StepDone({ onBack, onFinish }: { onBack: () => void; onFinish: () => void }) {
  return (
    <>
      <div className="kicker">Ready</div>
      <h1>You're set up.</h1>
      <div className="stack" style={{ marginTop: 16 }}>
        <div className="card"><h3>Paste a job ad</h3><p className="muted small" style={{ margin: 0 }}>On Home, paste any ad and press Generate. You get a CV and cover letter in a few minutes.</p></div>
        <div className="card"><h3>Or let it find jobs</h3><p className="muted small" style={{ margin: 0 }}>Find jobs searches your sites, scores every ad against your facts, and writes applications for the best.</p></div>
        <div className="card"><h3>Edit by chatting</h3><p className="muted small" style={{ margin: 0 }}>Open any application and tell Claude what to change. The PDFs update.</p></div>
        <Notice>Applications start as <b>ready</b>. Review each one, send it yourself, then mark it <b>applied</b> to get a follow-up reminder.</Notice>
      </div>
      <Foot onBack={onBack}><button className="btn btn-big" onClick={onFinish}>Open the app</button></Foot>
    </>
  );
}
