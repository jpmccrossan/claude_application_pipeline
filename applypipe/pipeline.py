"""The work itself: generate applications, scout for jobs, onboard a new user, chat edits.

Every function takes a Run (for logging and stop requests). Claude does the research and writing and
returns text; this module validates it, writes the files, renders, checks the one-page rule, and
sends any problems back to Claude for a fix (same conversation, up to three rounds).
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import shutil
import threading
from pathlib import Path

from . import config, jobfiles, profile as profiles, render, scout, sites, tracker
from .agent import engines, tasks
from .paths import CHATS, DATA, PROFILE_DIR

FIX_ROUNDS = 3
_render_lock = threading.Lock()  # one Chromium render at a time keeps memory predictable


def _events(run, prefix: str):
    def on_event(ev: dict):
        if ev.get("kind") == "tool":
            run.log(f"{prefix}{ev['text']}", "tool")
    return on_event


def _render(job: Path) -> dict:
    with _render_lock:
        return render.render_job(job)


# ---------------------------------------------------------------- one application

def generate_one(run, inbox_file: Path, status: str | None = None) -> dict:
    """Inbox file -> rendered, logged application. Returns {ok, folder, ...}.
    If the run is stopped part-way, the ad goes back to the inbox and the half-made folder is removed."""
    holder: dict = {}
    try:
        return _generate_one(run, inbox_file, status, holder)
    except engines.Stopped:
        job = holder.get("job")
        if job and job.exists() and "_pending" in job.name:
            src = job / "source" / "job.txt"
            if src.exists() and not inbox_file.exists():
                shutil.move(str(src), str(inbox_file))
            shutil.rmtree(job, ignore_errors=True)
            run.log(f"[{inbox_file.name}] stopped; the ad is back in the inbox", "warn")
        raise


def _generate_one(run, inbox_file: Path, status: str | None, holder: dict) -> dict:
    engine = engines.get_engine()
    name = inbox_file.name
    text = inbox_file.read_text()
    scout_id = (re.search(r"^Scout-ID: (\S+)", text[:3000], re.M) or [None, ""])[1]
    job = jobfiles.new_workdir(inbox_file)
    holder["job"] = job
    label = f"[{name}] "
    run.log(f"{label}researching and writing...")
    result = engine.run(tasks.brief_prompt(text), task="web", workdir=job / "source",
                        on_event=_events(run, label), should_stop=run.should_stop)
    if not result.ok:
        return _fail(run, job, label, f"Claude failed: {result.error}", scout_id)
    session = result.session
    reply = result.text
    for attempt in range(FIX_ROUNDS + 1):
        try:
            parsed = tasks.parse_brief(reply)
        except (ValueError, json.JSONDecodeError) as exc:
            if attempt == FIX_ROUNDS:
                return _fail(run, job, label, f"could not read Claude's reply: {exc}", scout_id)
            result = engine.run("Your reply could not be read: " + str(exc) +
                                ". Reply again with the <content_json> section containing valid JSON.",
                                task="web", workdir=job / "source", session=session, should_stop=run.should_stop)
            reply, session = result.text, result.session or session
            continue
        if "skip" in parsed:
            shutil.move(str(job / "source" / "job.txt"), str(inbox_file))  # leave it in the inbox
            shutil.rmtree(job, ignore_errors=True)
            run.log(f"{label}skipped: {parsed['skip']}", "warn")
            return {"ok": False, "skipped": parsed["skip"], "file": name, "scout_id": scout_id}
        if attempt == 0:
            (job / "source" / "brief.md").write_text(parsed["brief"])
            tasks.save_research(parsed["research"])
        (job / "source" / "content.json").write_text(json.dumps(parsed["content"], indent=1, ensure_ascii=False))
        check = _render(job)
        if check["ok"]:
            break
        run.log(f"{label}fixing: {'; '.join(check['errors'])[:300]}", "warn")
        if attempt == FIX_ROUNDS:
            final = jobfiles.finalise(job)
            return _fail(run, final, label, "still failing after fixes: " + "; ".join(check["errors"]), scout_id, keep=True)
        result = engine.run(tasks.fix_prompt(check["errors"], check["warnings"][:6]), task="web",
                            workdir=job / "source", session=session, should_stop=run.should_stop)
        if not result.ok:
            return _fail(run, job, label, f"Claude failed while fixing: {result.error}", scout_id, keep=True)
        reply, session = result.text, result.session or session
    final = jobfiles.finalise(job)
    (final / "source" / "session.txt").write_text(f"{engine.name}:{session}\n")
    tracker.log(final, status=status or "ready")
    content = jobfiles.read_content(final)
    run.log(f"{label}done: {content.get('company')}, {content.get('role')} ({content.get('fit', '?')} fit)", "done")
    return {"ok": True, "folder": final.name, "company": content.get("company"), "role": content.get("role"),
            "fit": content.get("fit"), "file": name, "scout_id": scout_id, "results": check["results"]}


def _fail(run, job: Path, label: str, message: str, scout_id: str, keep: bool = False) -> dict:
    run.log(f"{label}{message}", "error")
    if not keep:
        # Put the ad back in the inbox so nothing is lost.
        src = job / "source" / "job.txt"
        if src.exists():
            jobfiles.add_to_inbox(src.read_text(), "retry_" + job.name)
        shutil.rmtree(job, ignore_errors=True)
    return {"ok": False, "error": message, "folder": job.name if keep else "", "scout_id": scout_id}


def generate_inbox(run, files: list[str] | None = None) -> dict:
    waiting = jobfiles.waiting()
    if files:
        waiting = [f for f in waiting if f.name in files]
    if not waiting:
        run.log("the inbox is empty: paste a job ad first", "warn")
        return {"generated": []}
    parallel = max(1, int(config.settings().get("max_parallel", 3)))
    run.log(f"generating {len(waiting)} application(s), {parallel} at a time")
    out = []
    with cf.ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [pool.submit(generate_one, run, f) for f in waiting]
        for fut in cf.as_completed(futures):
            try:
                out.append(fut.result())
            except engines.Stopped:
                pass
            except Exception as exc:  # noqa: BLE001
                run.log(f"error: {exc}", "error")
                out.append({"ok": False, "error": str(exc)})
    done = sum(r.get("ok", False) for r in out)
    run.log(f"{done} of {len(waiting)} generated", "done")
    return {"generated": out}


# ---------------------------------------------------------------- scout

def run_scout(run) -> dict:
    engine = engines.get_engine()
    cfg = scout.targets()
    if not cfg["terms"]:
        raise ValueError("Add at least one search term in Preferences first.")
    run.log("starting a new scout run")
    scout.start(run.log)

    run.log("searching your job sites...")
    scout.collect(run.log, repair=_scout_repair(run, engine))
    if config.targets().get("web_search", True) and not run.should_stop():
        run.log("asking Claude to search the web as well...")
        res = engine.run(tasks.web_search_prompt(), task="web", workdir=DATA / "scout",
                         on_event=_events(run, "[web] "), should_stop=run.should_stop)
        if res.ok:
            added = 0
            rows, known = scout.load(), scout.seen()
            for l in tasks.parse_listings(res.text):
                if l.get("url"):
                    why = scout.add({"company": l.get("company", ""), "title": l.get("title", ""), "link": l["url"],
                                     "location": l.get("location", ""), "deadline": l.get("deadline", ""),
                                     "source": "web search"}, rows, known, cfg)
                    added += not why
            scout.save(rows)
            run.log(f"web search: added {added}")
        else:
            run.log(f"web search failed: {res.error}", "warn")
    if run.should_stop():
        return {}

    scout.fetch(run.log, run.should_stop)
    todo = scout.unscored()
    if todo and not run.should_stop():
        batches = [todo[i:i + 15] for i in range(0, len(todo), 15)]
        run.log(f"scoring {len(todo)} listings in {len(batches)} batch(es)...")

        def score_batch(batch):
            res = engine.run(tasks.scoring_prompt(batch), task="none", workdir=DATA / "scout", should_stop=run.should_stop)
            if not res.ok:
                run.log(f"scoring failed: {res.error}", "warn")
                return 0
            try:
                return scout.score(tasks.parse_scores(res.text))
            except (ValueError, json.JSONDecodeError) as exc:
                run.log(f"could not read scores: {exc}", "warn")
                return 0

        parallel = max(1, int(config.settings().get("max_parallel", 3)))
        with cf.ThreadPoolExecutor(max_workers=parallel) as pool:
            scored = sum(pool.map(score_batch, batches))
        run.log(f"scored {scored}")
    if run.should_stop():
        return {}

    promoted = scout.promote(run.log)
    gen = generate_inbox(run, promoted) if promoted else {"generated": []}
    scout.link_jobs({g["scout_id"]: g.get("folder", "") for g in gen["generated"] if g.get("scout_id")})
    s = scout.summary()
    run.log("scout finished: " + ", ".join(f"{k} {v}" for k, v in sorted(s["counts"].items())), "done")
    return {"counts": s["counts"], "generated": gen["generated"]}


# ---------------------------------------------------------------- job site setup

SITE_ROUNDS = 2
REPAIR_EVERY_DAYS = 7  # a careers page with no openings today should not cost a Claude call every run


def too_broad_pattern(pattern: str, page: dict) -> str:
    """Why a link pattern is too loose to be trusted (it matches the navigation too), or ''."""
    hrefs = [h for h, _ in page["links"] if h.startswith("http")]
    hits = sum(bool(re.search(pattern, h)) for h in hrefs)
    if len(hrefs) >= 10 and hits >= 0.8 * len(hrefs):
        return f"the link pattern matches {hits} of the {len(hrefs)} links on the page, so it includes navigation"
    return ""


def repair_site(engine, site: dict, problem: str, log, should_stop=lambda: False) -> dict:
    """Claude works out a website's search address and link pattern from the page; Python checks and tests
    them. Returns {"ok", "site", "test", "message"}. Raises sites.Blocked if robots.txt forbids the page."""
    cfg = scout.targets()
    terms, location = cfg["terms"], cfg["location_query"]
    original = site.get("url") or site.get("search_url") or ""
    first = terms[0] if terms else ""
    start = sites.fill(sites.page_address(site), first, location)
    log(f"reading {start} ...")
    page = sites.read_page(start)
    log(f"page has {len(page['links'])} links; asking Claude to work out the settings...")
    res = engine.run(tasks.site_prompt(site, page, problem, terms, location), task="none",
                     workdir=DATA / "scout", should_stop=should_stop)
    for attempt in range(SITE_ROUNDS + 1):
        if not res.ok:
            raise RuntimeError(f"Claude failed: {res.error}")
        try:
            got = tasks.parse_site(res.text, original)
        except (ValueError, json.JSONDecodeError) as exc:
            feedback = f"Your reply could not be used: {exc}."
        else:
            if "cannot" in got:
                return {"ok": False, "site": site, "test": None, "message": got["cannot"]}
            candidate = {k: v for k, v in site.items() if k != "claude_tried"} | got
            log(f"testing search address {got['search_url']} with link pattern {got['link_pattern']}")
            test = sites.test(candidate, terms, location)
            too_broad = too_broad_pattern(got["link_pattern"], page)
            if test["ok"] and (test["count"] < 2 or too_broad):
                test = test | {"ok": False, "error": too_broad or "it matched only one link, so it is probably not the job list"}
            if test["ok"]:
                return {"ok": True, "site": candidate, "test": test, "message": f"found {test['count']} listings"}
            if "robots.txt" in test["error"]:
                return {"ok": False, "site": site, "test": test, "message": test["error"]}
            feedback = f"I tested those settings: {test['error']}."
            if got["search_url"] != page["url"]:
                try:
                    feedback += " This is the page your search address opens:" + tasks.page_section(
                        sites.read_page(sites.fill(got["search_url"], first, location)))
                except Exception as exc:  # noqa: BLE001  tell Claude rather than fail the run
                    feedback += f" Your search address could not be opened ({type(exc).__name__}: {str(exc)[:200]})."
        if attempt == SITE_ROUNDS:
            break
        log(feedback.split(" This is the page")[0][:300], "warn")
        res = engine.run(feedback + "\n\nReply again in the same format.", task="none", workdir=DATA / "scout",
                         session=res.session, should_stop=should_stop)
    return {"ok": False, "site": site, "test": None, "message": "Claude could not find settings that work for this site."}


def fix_site(run, site: dict, problem: str) -> dict:
    """Background run behind the Sites page's Ask Claude button. The page decides whether to keep the result."""
    try:
        out = repair_site(engines.get_engine(), site, problem or "Test found no job ads", run.log, run.should_stop)
    except sites.Blocked as exc:
        out = {"ok": False, "site": site, "test": None, "message": f"{exc}. This site does not allow automated access."}
    run.log(out["message"], "done" if out["ok"] else "warn")
    return out


def _scout_repair(run, engine):
    """During a scout run, a website that stopped working gets one attempt at new settings, saved if they work."""
    def repair(site: dict, problem: str):
        name = site.get("name") or site.get("id")
        if not sites.page_address(site):
            return None
        tried = site.get("claude_tried", "")
        if tried and tried > (dt.date.today() - dt.timedelta(days=REPAIR_EVERY_DAYS)).isoformat():
            run.log(f"{name}: {problem}. Claude already tried to fix it on {tried}; press Ask Claude to fix it "
                    "on the Sites page to try again.", "warn")
            return None
        run.log(f"{name}: {problem}; asking Claude to fix this site's settings...", "warn")
        try:
            out = repair_site(engine, site, problem, run.log, run.should_stop)
        except engines.Stopped:
            raise
        except Exception as exc:  # noqa: BLE001  a failed repair should not stop the run
            run.log(f"{name}: could not fix it ({type(exc).__name__}: {str(exc)[:200]})", "warn")
            return None
        if not out["ok"]:
            run.log(f"{name}: {out['message']}", "warn")
            remember = site | {"claude_tried": dt.date.today().isoformat()}
            config.save_sites([remember if s.get("id") == site.get("id") else s for s in config.sites()])
            return None
        saved = [out["site"] if s.get("id") == site.get("id") else s for s in config.sites()]
        config.save_sites(saved)
        run.log(f"{name}: new settings work ({out['message']}) and were saved")
        return out["site"]
    return repair


# ---------------------------------------------------------------- onboarding

def onboard(run, cv_text: str, details: dict) -> dict:
    engine = engines.get_engine()
    run.log("reading your CV and building your profile...")
    res = engine.run(tasks.onboard_prompt(cv_text, details, profiles.photo() is not None), task="none",
                     workdir=PROFILE_DIR, should_stop=run.should_stop)
    for attempt in range(FIX_ROUNDS + 1):
        if not res.ok:
            raise RuntimeError(f"Claude failed: {res.error}")
        try:
            profile, facts = tasks.parse_onboard(res.text)
            problems = profiles.validate(profile)
        except (ValueError, json.JSONDecodeError) as exc:
            problems = [str(exc)]
        if not problems:
            break
        if attempt == FIX_ROUNDS:
            raise RuntimeError("the profile still has problems: " + "; ".join(problems))
        run.log("fixing: " + "; ".join(problems), "warn")
        res = engine.run("Problems: " + "; ".join(problems) + ". Reply again with both sections, fixed.",
                         task="none", workdir=PROFILE_DIR, session=res.session, should_stop=run.should_stop)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profiles.PROFILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    profiles.FACTS.write_text(facts.strip() + "\n")
    run.log("profile written; checking it fits on one page...")
    preview = preview_profile()
    run.log(f"CV preview: {'fits on one page' if preview['ok'] else 'too long: ' + '; '.join(preview['errors'])}",
            "done" if preview["ok"] else "warn")
    return {"preview": preview}


def preview_profile() -> dict:
    """Render the profile's default CV wording to check it fits one page. Writes data/profile/preview/."""
    folder = PROFILE_DIR / "preview"
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "source").mkdir(parents=True)
    profile = profiles.load()
    content = {"company": "Preview", "role": "Preview", "role_banner": "PREVIEW", "company_line": "Your profile",
               "p1": "This is a preview of your CV with its default wording. Each application rewrites these words for the job.",
               "short_col1_head": "PREVIEW", "short_col1": "Your profile's default wording.",
               "short_col2_head": "PREVIEW", "short_col2": "Tailored per job."}
    (folder / "source" / "content.json").write_text(json.dumps(content))
    with _render_lock:
        result = render.render_job(folder)
    names = profiles.doc_names(profile)
    result["cv"] = str((folder / names["cv"]).relative_to(DATA)) if (folder / names["cv"]).exists() else ""
    return result


# ---------------------------------------------------------------- chat

def chat_turn(run, chat_id: str, message: str, job_folder: str = "") -> dict:
    engine = engines.get_engine()
    path = CHATS / f"{chat_id}.json"
    chat = json.loads(path.read_text()) if path.exists() else {"id": chat_id, "job": job_folder, "messages": [],
                                                               "session": "", "engine": engine.name}
    if chat.get("engine") != engine.name:
        chat["session"] = ""  # sessions do not carry across engines
        chat["engine"] = engine.name
    job = jobfiles.find_job(chat.get("job") or job_folder) if (chat.get("job") or job_folder) else None
    chat["messages"].append({"role": "user", "text": message})
    _save_chat(path, chat)
    before = _mtime(job)
    prompt = tasks.chat_first_message(message, job) if not chat["session"] else message
    res = engine.run(prompt, task="files", workdir=DATA, session=chat["session"], system=tasks.chat_system(),
                     on_event=_events(run, ""), should_stop=run.should_stop)
    chat["session"] = res.session or chat["session"]
    reply = res.text if res.ok else f"Something went wrong: {res.error}"
    rendered = None
    if job and res.ok and _mtime(job) != before:
        rendered = _render(job)
        if not rendered["ok"]:
            note = "; ".join(rendered["errors"])
            run.log(f"render problem, asking Claude to fix: {note}", "warn")
            fix = engine.run(tasks.fix_prompt(rendered["errors"], []) .replace(
                "Reply with only the full corrected <content_json>...</content_json>.",
                "Edit content.json to fix it, then say what you changed in one sentence."),
                task="files", workdir=DATA, session=chat["session"], system=tasks.chat_system(),
                on_event=_events(run, ""), should_stop=run.should_stop)
            reply += "\n\n" + (fix.text if fix.ok else f"(fix failed: {fix.error})")
            rendered = _render(job)
        reply += "\n\n" + ("PDFs updated." if rendered["ok"] else "The PDFs could not be updated: " + "; ".join(rendered["errors"]))
    chat["messages"].append({"role": "assistant", "text": reply})
    _save_chat(path, chat)
    return {"reply": reply, "rendered": rendered}


def _mtime(job: Path | None) -> float:
    if not job:
        return 0
    f = job / "source" / "content.json"
    return f.stat().st_mtime if f.exists() else 0


def _save_chat(path: Path, chat: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chat, indent=1, ensure_ascii=False))
