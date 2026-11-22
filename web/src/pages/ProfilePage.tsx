import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Notice, RunLog, SaveBar, Section, useAsync } from "../components/ui";

export type ProfileData = {
  profile: Record<string, unknown>;
  facts: string;
  style_notes: string;
  is_example: boolean;
  has_photo: boolean;
  cv_file: string;
  icons: string[];
};

export function CvPreview({ bust }: { bust: number }) {
  return <iframe className="pdf" style={{ height: "70vh" }} title="CV preview" src={`/api/profile/preview/cv?v=${bust}#view=FitH`} />;
}

export default function ProfilePage() {
  const { data, reload } = useAsync(() => api.get<ProfileData>("/api/profile"));
  const [facts, setFacts] = useState("");
  const [notes, setNotes] = useState("");
  const [json, setJson] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [tab, setTab] = useState("facts");
  const [bust, setBust] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const cvInput = useRef<HTMLInputElement>(null);
  const photoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!data) return;
    setFacts(data.facts);
    setNotes(data.style_notes);
    setJson(JSON.stringify(data.profile, null, 2));
    setDirty(false);
  }, [data]);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const profile = JSON.parse(json);
      await api.put("/api/profile", { profile, facts, style_notes: notes });
      setDirty(false);
      setMsg({ kind: "ok", text: "Saved." });
      reload();
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof SyntaxError ? `profile.json is not valid JSON: ${e.message}` : (e as Error).message });
    }
    setSaving(false);
  };
  const preview = async () => {
    setMsg({ kind: "ok", text: "Rendering preview..." });
    const r = await api.post<{ ok: boolean; errors: string[] }>("/api/profile/preview");
    setBust(Date.now());
    setTab("preview");
    setMsg(r.ok ? { kind: "ok", text: "Your default CV fits on one page." } : { kind: "error", text: r.errors.join("; ") });
  };
  const uploadCv = async (f: File) => {
    try {
      await api.upload("/api/profile/cv", f);
      if (confirm("CV uploaded. Rebuild your profile and facts from it now? This replaces your current profile and facts.")) {
        const r = await api.post<{ run: string }>("/api/onboard", { details: {} });
        setRunId(r.run);
      }
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  };
  const uploadPhoto = async (f: File) => {
    try { await api.upload("/api/profile/photo", f); setMsg({ kind: "ok", text: "Photo saved. Set \"photo\": true in profile.json to show it." }); reload(); }
    catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  };

  if (!data) return <span className="spinner" />;
  return (
    <>
      <div className="page-head">
        <div><div className="kicker">Set up</div><h1>Profile & facts</h1></div>
        <div className="row gap">
          <button className="btn btn-ghost" onClick={() => cvInput.current?.click()}>Upload a new CV</button>
          <button className="btn btn-ghost" onClick={() => photoInput.current?.click()}>{data.has_photo ? "Replace photo" : "Add photo"}</button>
          {data.has_photo && <button className="btn btn-ghost" onClick={async () => { await api.del("/api/profile/photo"); reload(); }}>Remove photo</button>}
          <button className="btn" onClick={preview}>Preview CV</button>
          <input ref={cvInput} type="file" hidden accept=".pdf,.docx,.txt,.md" onChange={(e) => e.target.files?.[0] && uploadCv(e.target.files[0])} />
          <input ref={photoInput} type="file" hidden accept=".jpg,.jpeg,.png" onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])} />
        </div>
      </div>
      {data.is_example && <Notice kind="warn">You are seeing the example person. Upload your CV to build your own profile.</Notice>}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {runId && <Section title="Rebuilding your profile"><RunLog runId={runId} onDone={() => { reload(); setBust(Date.now()); }} /></Section>}

      <div className="tabs">
        {[["facts", "Facts (source of truth)"], ["style", "Writing style"], ["profile", "CV layout (profile.json)"], ["preview", "CV preview"]].map(([k, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>))}
      </div>
      {tab === "facts" && (
        <Section title="facts.md">
          <p className="muted small">Everything true about you. Nothing can be claimed in an application unless it is written here.
            Lines containing <b>TODO</b> are open questions and are ignored until you replace them with a fact: answering them (numbers, outcomes) makes the letters much stronger.</p>
          <textarea className="code" rows={30} value={facts} onChange={(e) => { setFacts(e.target.value); setDirty(true); }} />
        </Section>)}
      {tab === "style" && (
        <Section title="Your writing preferences">
          <p className="muted small">Optional. Notes applied to every letter, in plain words. For example: "British spelling", "Keep it modest and direct", "Never mention my career break", "Sign off with Best wishes".</p>
          <textarea rows={12} value={notes} onChange={(e) => { setNotes(e.target.value); setDirty(true); }} />
        </Section>)}
      {tab === "profile" && (
        <Section title="profile.json">
          <p className="muted small">The fixed parts of your CV (name, contact line, employers, dates, education, skill chips, beyond-work columns, letter sign-off) and the default wording each application tailors.
            Easier: ask for changes in <a href="#/chat">Chat</a>. Icons available for <code>stack_icons</code>: {data.icons.join(", ")}.</p>
          <textarea className="code" rows={34} value={json} onChange={(e) => { setJson(e.target.value); setDirty(true); }} />
        </Section>)}
      {tab === "preview" && <Section title="Your CV with its default wording">{bust ? <CvPreview bust={bust} /> : <button className="btn" onClick={preview}>Render preview</button>}</Section>}
      <SaveBar dirty={dirty} saving={saving} onSave={save} />
    </>
  );
}
