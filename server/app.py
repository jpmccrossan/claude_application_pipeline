"""Local web app: JSON API for the React UI, plus the built UI itself.

Run with ./start.sh (or: python -m server). Binds to 127.0.0.1 only: this is a single-user tool with
no login, and it can run Claude on your files, so never expose it to a network.
"""
import json
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from applypipe import config, cvtext, jobfiles, paths, pipeline, profile as profiles, runs, scout, sites, tracker
from applypipe.agent import engines

paths.ensure_dirs()
app = FastAPI(title="Claude Application Pipeline", docs_url="/api/docs", openapi_url="/api/openapi.json")
DIST = paths.ROOT / "web" / "dist"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


@app.middleware("http")
async def local_only(request, call_next):
    """Refuse requests from other websites. Any page you visit could otherwise send requests to this
    server (it has no login), for example to start runs or upload files. Browsers always send the
    Host header, and send Origin on cross-site requests, so both must name this machine."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    origin = request.headers.get("origin") or ""
    origin_host = re.sub(r"^https?://", "", origin).rsplit(":", 1)[0] if origin else ""
    if host not in LOCAL_HOSTS or (origin and origin_host not in LOCAL_HOSTS):
        return JSONResponse({"error": "This app only accepts requests from this computer."}, status_code=403)
    return await call_next(request)


def bad(message: str, code: int = 400):
    raise HTTPException(status_code=code, detail=message)


# ---------------------------------------------------------------- status and settings

_chromium_ok: bool | None = None


def chromium_ok() -> bool:
    global _chromium_ok
    if _chromium_ok is None:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                _chromium_ok = Path(p.chromium.executable_path).exists()
        except Exception:  # noqa: BLE001
            _chromium_ok = False
    return _chromium_ok


@app.get("/api/status")
def status():
    s = config.settings()
    return {
        "disclaimer_accepted": s["disclaimer_accepted"],
        "onboarded": s["onboarded"] and profiles.has_profile(),
        "has_profile": profiles.has_profile(),
        "engine": engines.choose_engine(),
        "engine_setting": s["engine"],
        "claude_cli": engines.claude_cli(),
        "api_key": config.api_key_hint(),
        "chromium": chromium_ok(),
        "running": [r.to_dict() | {"log": []} for r in runs.active()],
        "inbox": len(jobfiles.waiting()),
        "data_dir": str(paths.DATA),
    }


class SettingsIn(BaseModel):
    engine: str | None = None
    model: str | None = None
    max_parallel: int | None = None
    disclaimer_accepted: bool | None = None
    onboarded: bool | None = None
    api_key: str | None = None


@app.get("/api/settings")
def get_settings():
    return config.settings() | {"api_key": config.api_key_hint()}


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    values = {k: v for k, v in body.model_dump().items() if v is not None and k != "api_key"}
    if "engine" in values and values["engine"] not in ("auto", "claude-code", "api"):
        bad("engine must be auto, claude-code or api")
    if "max_parallel" in values:
        values["max_parallel"] = max(1, min(8, values["max_parallel"]))
    if body.api_key is not None:
        config.save_api_key(body.api_key)
    return config.save_settings(values) | {"api_key": config.api_key_hint()}


@app.get("/api/disclaimer")
def disclaimer():
    return {"text": (paths.ROOT / "DISCLAIMER.md").read_text()}


@app.post("/api/engine/test")
def engine_test():
    try:
        engine = engines.get_engine()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    result = engine.run("Reply with exactly: OK", task="none", workdir=paths.CHATS, timeout_s=180)
    return {"ok": result.ok and "OK" in result.text, "engine": engine.name, "reply": result.text[:200], "error": result.error}


# ---------------------------------------------------------------- profile

@app.get("/api/profile")
def get_profile():
    return {
        "profile": profiles.load(),
        "facts": profiles.facts(),
        "style_notes": profiles.style_notes(),
        "is_example": not profiles.has_profile(),
        "has_photo": profiles.photo() is not None,
        "cv_file": next((p.name for p in paths.PROFILE_DIR.glob("cv.*") if p.suffix != ".txt"), ""),
        "icons": profiles.available_icons(),
    }


class ProfileIn(BaseModel):
    profile: dict | None = None
    facts: str | None = None
    style_notes: str | None = None


@app.put("/api/profile")
def put_profile(body: ProfileIn):
    paths.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if body.profile is not None:
        problems = profiles.validate(body.profile)
        if problems:
            bad("; ".join(problems))
        profiles.PROFILE.write_text(json.dumps(body.profile, indent=2, ensure_ascii=False))
    if body.facts is not None:
        profiles.FACTS.write_text(body.facts)
    if body.style_notes is not None:
        profiles.STYLE_NOTES.write_text(body.style_notes)
    return get_profile()


@app.post("/api/profile/cv")
async def upload_cv(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt", ".md"):
        bad("Upload your CV as PDF, Word (.docx) or plain text.")
    paths.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for old in paths.PROFILE_DIR.glob("cv.*"):
        old.unlink()
    dest = paths.PROFILE_DIR / f"cv{suffix}"
    dest.write_bytes(await file.read())
    try:
        text = cvtext.extract(dest)
    except Exception as exc:  # noqa: BLE001
        bad(str(exc))
    (paths.PROFILE_DIR / "cv.txt").write_text(text)
    return {"ok": True, "chars": len(text), "preview": text[:600]}


@app.post("/api/profile/photo")
async def upload_photo(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower().replace(".jpeg", ".jpg")
    if suffix not in (".jpg", ".png"):
        bad("Upload a JPG or PNG photo.")
    for name in profiles.PHOTO_NAMES:
        (paths.PROFILE_DIR / name).unlink(missing_ok=True)
    (paths.PROFILE_DIR / f"photo{suffix}").write_bytes(await file.read())
    return {"ok": True}


@app.delete("/api/profile/photo")
def delete_photo():
    for name in profiles.PHOTO_NAMES:
        (paths.PROFILE_DIR / name).unlink(missing_ok=True)
    return {"ok": True}


class OnboardIn(BaseModel):
    details: dict = {}


@app.post("/api/onboard")
def onboard(body: OnboardIn):
    cv = paths.PROFILE_DIR / "cv.txt"
    if not cv.exists():
        bad("Upload your CV first.")
    _need_engine()
    run = runs.start("onboard", "Build profile from CV", pipeline.onboard, cv.read_text(), body.details)
    return {"run": run.id}


@app.post("/api/profile/preview")
def profile_preview():
    return pipeline.preview_profile()


# ---------------------------------------------------------------- preferences and sites

@app.get("/api/targets")
def get_targets():
    return config.targets()


@app.put("/api/targets")
def put_targets(body: dict):
    config.save_targets(body)
    return config.targets()


@app.get("/api/sites")
def get_sites():
    return {"sites": config.sites(), "types": sites.TYPES}


@app.put("/api/sites")
def put_sites(body: list[dict]):
    for i, s in enumerate(body):
        if s.get("type") not in sites.TYPES:
            bad(f"{s.get('name') or f'site {i + 1}'}: this kind of source is no longer supported. Remove it, then save.")
        s.setdefault("id", f"{s['type']}-{uuid.uuid4().hex[:6]}")
        if s["type"] == "generic" and s.get("link_pattern"):
            try:
                re.compile(s["link_pattern"])
            except re.error as exc:
                bad(f"{s.get('name', 'site')}: link pattern is not a valid regular expression ({exc})")
    config.save_sites(body)
    return get_sites()


@app.post("/api/sites/test")
def test_site(site: dict):
    t = scout.targets()
    return sites.test(site, t["terms"], t["location_query"])


class ResolveIn(BaseModel):
    url: str


@app.post("/api/sites/resolve")
def resolve_site(body: ResolveIn):
    """Turn a pasted address into a site the scout can use (not saved until the page saves)."""
    try:
        site = sites.resolve(body.url, scout.targets()["terms"])
    except (sites.Blocked, ValueError) as exc:
        bad(str(exc))
    site["id"] = f"{site['type']}-{uuid.uuid4().hex[:6]}"
    return site


class FixSiteIn(BaseModel):
    site: dict
    problem: str = ""


@app.post("/api/runs/site")
def run_fix_site(body: FixSiteIn):
    _need_engine()
    if body.site.get("type") != "generic" or not sites.page_address(body.site):
        bad("Claude can only set up website sources that have an address.")
    title = f"Set up {body.site.get('name') or 'job site'}"
    return {"run": runs.start("site", title, pipeline.fix_site, body.site, body.problem[:500]).id}


# ---------------------------------------------------------------- inbox and runs

class PasteIn(BaseModel):
    text: str
    name: str = ""


@app.get("/api/inbox")
def get_inbox():
    return [{"name": f.name, "chars": len(f.read_text()), "preview": f.read_text()[:300]} for f in jobfiles.waiting()]


@app.post("/api/inbox")
def post_inbox(body: PasteIn):
    if len(body.text.strip()) < 200:
        bad("That looks too short to be a job ad. Paste the whole ad (and the link at the top, if you have it).")
    path = jobfiles.add_to_inbox(body.text, body.name)
    return {"name": path.name}


@app.delete("/api/inbox/{name}")
def delete_inbox(name: str):
    path = paths.INBOX / Path(name).name
    path.unlink(missing_ok=True)
    return {"ok": True}


def _need_engine():
    if not engines.choose_engine():
        bad("No Claude engine available. Install and log in to Claude Code, or add an API key in Settings.")


@app.post("/api/runs/generate")
def run_generate(body: dict | None = None):
    _need_engine()
    if runs.active("generate") or runs.active("scout"):
        bad("A run is already in progress.")
    files = (body or {}).get("files")
    return {"run": runs.start("generate", "Generate applications", pipeline.generate_inbox, files).id}


@app.post("/api/runs/scout")
def run_scout():
    _need_engine()
    if runs.active("scout") or runs.active("generate"):
        bad("A run is already in progress.")
    return {"run": runs.start("scout", "Find jobs", pipeline.run_scout).id}


@app.get("/api/runs")
def list_runs():
    return runs.recent()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, since: int = 0):
    data = runs.get(run_id)
    if data is None:
        bad("no such run", 404)
    data["log"] = data.get("log", [])[since:]
    return data


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str):
    return {"ok": runs.stop(run_id)}


@app.get("/api/scout")
def scout_listings():
    return scout.summary()


# ---------------------------------------------------------------- applications

@app.get("/api/applications")
def applications():
    rows = {r["folder"]: r for r in tracker.load()}
    out = []
    for job in reversed(jobfiles.job_folders()):
        if job.parent.name == "preview":
            continue
        row = rows.get(job.name, {})
        try:
            content = jobfiles.read_content(job)
        except (json.JSONDecodeError, OSError):
            content = {}
        names = profiles.doc_names(profiles.load())
        out.append({
            "folder": job.name, "day": job.parent.name,
            "company": content.get("company", row.get("company", "")), "role": content.get("role", row.get("role", "")),
            "fit": content.get("fit", ""), "deadline": content.get("deadline", ""), "location": content.get("location", ""),
            "status": row.get("status", "not logged"), "status_date": row.get("status_date", ""),
            "follow_up_date": row.get("follow_up_date", ""), "notes": row.get("notes", ""),
            "rendered": (job / names["cv"]).exists() and (job / names["letter"]).exists(),
        })
    return {"applications": out, "statuses": tracker.STATUSES, "followups": tracker.followups()}


def _job(folder: str) -> Path:
    job = jobfiles.find_job(Path(folder).name)
    if not job:
        bad("no such application", 404)
    return job


@app.get("/api/applications/{folder}")
def application(folder: str):
    job = _job(folder)
    names = profiles.doc_names(profiles.load())
    src = job / "source"
    return {
        "folder": job.name,
        "content": jobfiles.read_content(job),
        "brief": (src / "brief.md").read_text() if (src / "brief.md").exists() else "",
        "apply": (job / "APPLY.md").read_text() if (job / "APPLY.md").exists() else "",
        "job_text": (src / "job.txt").read_text()[:20000] if (src / "job.txt").exists() else "",
        "files": {k: v for k, v in names.items() if (job / v).exists()},
        "tracker": next((r for r in tracker.load() if r["folder"] == job.name), None),
    }


@app.put("/api/applications/{folder}/content")
def save_content(folder: str, content: dict):
    job = _job(folder)
    (job / "source" / "content.json").write_text(json.dumps(content, indent=1, ensure_ascii=False))
    with pipeline._render_lock:
        from applypipe import render
        return render.render_job(job)


@app.post("/api/applications/{folder}/render")
def rerender(folder: str):
    job = _job(folder)
    with pipeline._render_lock:
        from applypipe import render
        return render.render_job(job)


class StatusIn(BaseModel):
    status: str
    note: str = ""


@app.put("/api/applications/{folder}/status")
def set_status(folder: str, body: StatusIn):
    job = _job(folder)
    if not any(r["folder"] == job.name for r in tracker.load()):
        tracker.log(job, status=body.status, notes=body.note)
        return {"ok": True}
    tracker.set_status(job.name, body.status.lower().strip(), body.note)
    return {"ok": True}


@app.delete("/api/applications/{folder}")
def delete_application(folder: str):
    job = _job(folder)
    shutil.rmtree(job)
    rows = [r for r in tracker.load() if r["folder"] != job.name]
    with tracker.locked():
        tracker.save(rows)
    return {"ok": True}


@app.get("/api/applications/{folder}/file/{name}")
def application_file(folder: str, name: str):
    job = _job(folder)
    name = Path(name).name
    candidates = {p.name: p for p in job.glob("*.pdf")} | {f"{p.name}": p for p in (job / "HTML").glob("*.html")}
    path = candidates.get(name)
    if not path:
        bad("no such file", 404)
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media, headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.get("/api/profile/preview/cv")
def profile_preview_file():
    names = profiles.doc_names(profiles.load())
    path = paths.PROFILE_DIR / "preview" / names["cv"]
    if not path.exists():
        bad("no preview yet", 404)
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


# ---------------------------------------------------------------- chat

class ChatIn(BaseModel):
    message: str
    chat_id: str = ""
    job: str = ""


@app.post("/api/chat")
def chat(body: ChatIn):
    _need_engine()
    if not body.message.strip():
        bad("Type a message first.")
    chat_id = re.sub(r"[^a-z0-9]", "", body.chat_id.lower()) or uuid.uuid4().hex[:12]
    if any(r.meta.get("chat") == chat_id for r in runs.active("chat")):
        bad("Claude is still answering the last message.")
    run = runs.start("chat", "Chat", pipeline.chat_turn, chat_id, body.message.strip(), body.job,
                     meta={"chat": chat_id, "job": body.job})
    return {"run": run.id, "chat_id": chat_id}


@app.get("/api/chat/{chat_id}")
def get_chat(chat_id: str):
    path = paths.CHATS / f"{re.sub(r'[^a-z0-9]', '', chat_id)}.json"
    if not path.exists():
        return {"id": chat_id, "messages": []}
    data = json.loads(path.read_text())
    data.pop("session", None)
    return data


# ---------------------------------------------------------------- the UI

@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.mount("/fonts", StaticFiles(directory=paths.TEMPLATES / "fonts"), name="fonts")
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    index = DIST / "index.html"
    if path.startswith("api/"):
        bad("not found", 404)
    if not index.exists():
        return JSONResponse({"error": "The UI is not built. Run ./start.sh, or: cd web && npm install && npm run build"}, 500)
    return FileResponse(index)
