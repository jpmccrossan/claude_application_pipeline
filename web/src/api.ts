// Thin client for the local FastAPI backend.

export type LogLine = { t: string; kind: string; text: string };
export type RunInfo = {
  id: string;
  kind: string;
  title: string;
  status: "running" | "done" | "failed" | "stopped" | "interrupted";
  started: string;
  finished: string;
  error: string;
  result: Record<string, unknown>;
  log: LogLine[];
  log_total: number;
  meta: Record<string, string>;
};

export type Status = {
  disclaimer_accepted: boolean;
  onboarded: boolean;
  has_profile: boolean;
  engine: "claude-code" | "api" | "";
  engine_setting: string;
  claude_cli: string;
  api_key: string;
  chromium: boolean;
  running: RunInfo[];
  inbox: number;
  data_dir: string;
};

export type Application = {
  folder: string;
  day: string;
  company: string;
  role: string;
  fit: string;
  deadline: string;
  location: string;
  status: string;
  status_date: string;
  follow_up_date: string;
  notes: string;
  rendered: boolean;
};

export type TrackerRow = Record<string, string>;

export type Site = {
  id?: string;
  name: string;
  type: string;
  enabled: boolean;
  [key: string]: unknown;
};

export type SiteType = { label: string; help: string; fields: Record<string, string> };

export class ApiError extends Error {}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(url, init);
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = data?.error ?? data?.detail ?? `Request failed (${res.status})`;
    throw new ApiError(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
  del: <T>(url: string) => request<T>("DELETE", url),
  upload: <T>(url: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>("POST", url, form);
  },
};

export const fileUrl = (folder: string, name: string) =>
  `/api/applications/${encodeURIComponent(folder)}/file/${encodeURIComponent(name)}`;
