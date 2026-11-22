import { useEffect, useState } from "react";
import { api } from "../api";
import { Field, LinesInput, SaveBar, Section, useAsync } from "../components/ui";

export type Targets = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/** The job-preferences form, used here and in setup. */
export function TargetsForm({ value, onChange }: { value: Targets; onChange: (t: Targets) => void }) {
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  return (
    <div className="stack">
      <div className="grid2">
        <Field label="What roles do you want?" hint="One search per line. These are typed into each job site's search.">
          <LinesInput value={value.search_terms} onChange={(v) => set("search_terms", v)} rows={5}
            placeholder={"python developer\ndata engineer"} />
        </Field>
        <Field label="Where?" hint="Places to keep, one per line (matched against the listing's location). Include 'remote' if you want remote roles. Leave empty for anywhere.">
          <LinesInput value={value.locations} onChange={(v) => set("locations", v)} rows={5} placeholder={"london\nremote"} />
        </Field>
      </div>
      <div className="grid2">
        <Field label="Title must contain one of" hint="Keeps only titles with one of these words. Empty: the words of your searches are used.">
          <LinesInput value={value.title_keywords} onChange={(v) => set("title_keywords", v)} rows={4} />
        </Field>
        <Field label="Skip titles containing" hint="For example senior, lead, manager, intern.">
          <LinesInput value={value.exclude_titles} onChange={(v) => set("exclude_titles", v)} rows={4} />
        </Field>
      </div>
      <div className="grid3">
        <Field label="Your level" hint="In your own words; used when scoring.">
          <input value={value.seniority ?? ""} onChange={(e) => set("seniority", e.target.value)} placeholder="mid-level, about 4 years" />
        </Field>
        <Field label="Max years an ad may require">
          <input type="number" min={0} value={value.max_years_required ?? ""} onChange={(e) => set("max_years_required", Number(e.target.value))} />
        </Field>
        <Field label="Languages you work in">
          <input value={value.languages ?? ""} onChange={(e) => set("languages", e.target.value)} placeholder="English, Spanish" />
        </Field>
      </div>
      <div className="grid3">
        <Field label="City for site searches" hint="Filled into {location} in site URLs.">
          <input value={value.location_query ?? ""} onChange={(e) => set("location_query", e.target.value)} />
        </Field>
        <Field label="Ignore ads older than (days)">
          <input type="number" min={1} value={value.max_age_days ?? 14} onChange={(e) => set("max_age_days", Number(e.target.value))} />
        </Field>
        <Field label="Applications per run (max)">
          <input type="number" min={1} max={50} value={value.max_jobs_per_run ?? 10} onChange={(e) => set("max_jobs_per_run", Number(e.target.value))} />
        </Field>
      </div>
      <div className="grid2">
        <Field label="Generate applications for" hint="Each listing is scored strong, decent, stretch or skip.">
          <select value={value.min_fit ?? "decent"} onChange={(e) => set("min_fit", e.target.value)}>
            <option value="strong">Strong fits only</option>
            <option value="decent">Strong and decent fits</option>
            <option value="stretch">Strong, decent and stretch</option>
          </select>
        </Field>
        <div className="stack" style={{ paddingTop: 20 }}>
          <label className="check"><input type="checkbox" checked={value.english_only ?? true} onChange={(e) => set("english_only", e.target.checked)} />
            Only English-language ads</label>
          <label className="check"><input type="checkbox" checked={value.web_search ?? true} onChange={(e) => set("web_search", e.target.checked)} />
            Also let Claude search the web for listings (uses more of your Claude usage)</label>
        </div>
      </div>
      <Field label="Companies to check directly (web search)" hint="Optional, one per line. Claude looks at their careers pages.">
        <LinesInput value={value.companies_to_check} onChange={(v) => set("companies_to_check", v)} rows={3} />
      </Field>
      <div className="grid2">
        <Field label="Avoid" hint="Industries, companies or kinds of role to skip.">
          <textarea rows={2} value={value.avoid ?? ""} onChange={(e) => set("avoid", e.target.value)} />
        </Field>
        <Field label="Anything else" hint="Free text used when scoring, e.g. 'prefer product companies'.">
          <textarea rows={2} value={value.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>
    </div>
  );
}

export default function Preferences() {
  const { data } = useAsync(() => api.get<Targets>("/api/targets"));
  const [value, setValue] = useState<Targets | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (data) setValue(data); }, [data]);
  if (!value) return <span className="spinner" />;
  const save = async () => { setSaving(true); setValue(await api.put<Targets>("/api/targets", value)); setSaving(false); setDirty(false); };
  return (
    <>
      <div className="page-head"><div><div className="kicker">Set up</div><h1>Job preferences</h1></div></div>
      <Section title="What the scout looks for">
        <TargetsForm value={value} onChange={(v) => { setValue(v); setDirty(true); }} />
      </Section>
      <SaveBar dirty={dirty} saving={saving} onSave={save} />
    </>
  );
}
