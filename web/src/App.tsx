import { useEffect, useState } from "react";
import { api, Status } from "./api";
import Setup from "./pages/Setup";
import Home from "./pages/Home";
import Applications from "./pages/Applications";
import ApplicationDetail from "./pages/ApplicationDetail";
import FindJobs from "./pages/FindJobs";
import ChatPage from "./pages/ChatPage";
import ProfilePage from "./pages/ProfilePage";
import Preferences from "./pages/Preferences";
import SitesPage from "./pages/SitesPage";
import SettingsPage from "./pages/SettingsPage";

/** Tiny hash router: #/applications/<folder> -> ["applications", "<folder>"] */
function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (path: string) => { window.location.hash = `#/${path}`; };

const NAV: [string, string][] = [
  ["", "Home"],
  ["applications", "Applications"],
  ["find", "Find jobs"],
  ["chat", "Chat with Claude"],
];
const NAV_SETUP: [string, string][] = [
  ["profile", "Profile & facts"],
  ["preferences", "Job preferences"],
  ["sites", "Job sites"],
  ["settings", "Settings"],
];

export default function App() {
  const route = useRoute();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  const refresh = () => api.get<Status>("/api/status").then((s) => { setStatus(s); setError(""); }).catch((e) => setError(e.message));
  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 8000);
    return () => window.clearInterval(t);
  }, []);

  if (error && !status) {
    return <div className="setup"><div className="setup-card"><div className="setup-body">
      <h1>Cannot reach the app server</h1><p className="muted">{error}</p>
      <p>Start it with <code>./start.sh</code> in the project folder, then reload this page.</p>
    </div></div></div>;
  }
  if (!status) return <div className="setup"><span className="spinner" /></div>;
  if (!status.disclaimer_accepted || !status.onboarded) {
    return <Setup status={status} onDone={refresh} />;
  }

  const page = route[0] ?? "";
  const body = (() => {
    switch (page) {
      case "applications":
        return route[1] ? <ApplicationDetail folder={route[1]} /> : <Applications />;
      case "find": return <FindJobs status={status} onChange={refresh} />;
      case "chat": return <ChatPage />;
      case "profile": return <ProfilePage />;
      case "preferences": return <Preferences />;
      case "sites": return <SitesPage />;
      case "settings": return <SettingsPage status={status} onChange={refresh} />;
      default: return <Home status={status} onChange={refresh} />;
    }
  })();

  const link = ([path, label]: [string, string]) => (
    <a key={path} href={`#/${path}`} className={page === path ? "active" : ""}>
      {label}
      {path === "" && status.inbox > 0 && <span className="count">{status.inbox}</span>}
      {path === "find" && status.running.some((r) => r.kind === "scout") && <span className="spinner" />}
    </a>
  );

  return (
    <div className="shell">
      <aside className="side">
        <div className="side-top">
          <span className="dot" style={{ background: "#2036d9" }} />
          <span className="dot" style={{ background: "#e9ecfa" }} />
          <span className="dot" style={{ background: "#9a99a4" }} />
        </div>
        <div className="brand">
          <div className="brand-name">Application <span>Pipeline</span></div>
          <div className="brand-sub">tailored CVs and letters, by Claude</div>
        </div>
        <nav className="nav">
          {NAV.map(link)}
          <div className="nav-label">Set up</div>
          {NAV_SETUP.map(link)}
        </nav>
        <div className="side-foot">
          <div className="engine-pill">
            <span className="dot" style={{ background: status.engine ? "#8be0ad" : "#ff8f86" }} />
            {status.engine === "claude-code" ? "Claude Code" : status.engine === "api" ? "Claude API" : "No Claude engine"}
          </div>
          {status.running.length > 0 && <div style={{ marginTop: 6 }}><span className="spinner" />{status.running.length} running</div>}
        </div>
      </aside>
      <main className="main">{body}</main>
    </div>
  );
}
