"""Background runs (scout, generate, onboarding, chat turns) with a log the UI can poll.

Each run is a thread. Its state and log are written to data/runs/<id>.json as it goes, so a page
refresh (or a server restart) still shows what happened. One server process only: the app is a
single-user local tool.
"""
import datetime as dt
import json
import threading
import traceback
import uuid

from .paths import RUNS

_runs: dict[str, "Run"] = {}
_lock = threading.Lock()


class Run:
    def __init__(self, kind: str, title: str, meta: dict | None = None):
        self.id = dt.datetime.now().strftime("%y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        self.kind, self.title, self.meta = kind, title, meta or {}
        self.status = "running"
        self.started = dt.datetime.now().isoformat(timespec="seconds")
        self.finished = ""
        self.log_lines: list[dict] = []
        self.result: dict = {}
        self.error = ""
        self._stop = threading.Event()
        self._save_lock = threading.Lock()

    def log(self, text, kind: str = "info") -> None:
        if isinstance(text, dict):
            kind, text = text.get("kind", kind), text.get("text", "")
        line = {"t": dt.datetime.now().strftime("%H:%M:%S"), "kind": kind, "text": str(text)[:2000]}
        self.log_lines.append(line)
        self.save()

    def should_stop(self) -> bool:
        return self._stop.is_set()

    def stop(self) -> None:
        self._stop.set()
        self.log("stopping...", "warn")

    def to_dict(self, since: int = 0) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "meta": self.meta, "status": self.status,
                "started": self.started, "finished": self.finished, "error": self.error, "result": self.result,
                "log": self.log_lines[since:], "log_total": len(self.log_lines)}

    def save(self) -> None:
        with self._save_lock:
            RUNS.mkdir(parents=True, exist_ok=True)
            tmp = RUNS / f".{self.id}.tmp"
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False))
            tmp.replace(RUNS / f"{self.id}.json")


def start(kind: str, title: str, target, *args, meta: dict | None = None) -> Run:
    """Run target(run, *args) in a thread. target returns a result dict."""
    run = Run(kind, title, meta)
    with _lock:
        _runs[run.id] = run

    def body():
        from .agent.engines import Stopped

        try:
            run.result = target(run, *args) or {}
            run.status = "stopped" if run.should_stop() else "done"
        except Stopped:
            run.status = "stopped"
        except Exception as exc:  # noqa: BLE001  shown in the UI
            run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
            run.log(traceback.format_exc()[-1500:], "error")
        run.finished = dt.datetime.now().isoformat(timespec="seconds")
        run.log(f"finished: {run.status}", "done" if run.status == "done" else "warn")

    run.save()
    threading.Thread(target=body, daemon=True, name=f"run-{run.id}").start()
    return run


def get(run_id: str) -> dict | None:
    if run_id in _runs:
        return _runs[run_id].to_dict()
    path = RUNS / f"{run_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def stop(run_id: str) -> bool:
    run = _runs.get(run_id)
    if run and run.status == "running":
        run.stop()
        return True
    return False


def active(kind: str | None = None) -> list[Run]:
    return [r for r in _runs.values() if r.status == "running" and (kind is None or r.kind == kind)]


def recent(limit: int = 30) -> list[dict]:
    out = []
    for path in sorted(RUNS.glob("*.json"), reverse=True)[:limit]:
        try:
            d = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        live = _runs.get(d["id"])
        if live:
            d = live.to_dict()
        elif d.get("status") == "running":
            d["status"] = "interrupted"  # the server stopped while it was running
        d.pop("log", None)
        out.append(d)
    return out
