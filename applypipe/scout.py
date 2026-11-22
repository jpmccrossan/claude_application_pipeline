"""Scout: collect listings from the configured sites, keep the relevant new ones, fetch their full
text, record scores, and hand the best to the inbox for generation.

State for the current run lives in data/scout/current/ (listings.csv plus listings/<id>.txt).
start() archives the previous run to data/scout/archive/<date>/. Listings seen in earlier runs, or
already in the tracker, are never shown again.
"""
import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import re
import shutil

from . import config, sites, tracker
from .paths import INBOX, SCOUT

CURRENT = SCOUT / "current"
ARCHIVE = SCOUT / "archive"
CSV_PATH = CURRENT / "listings.csv"
COLUMNS = ["id", "found", "source", "company", "title", "location", "posted", "deadline", "link", "board_link",
           "status", "fit", "reason", "job_folder"]
FIT_RANK = {"strong": 0, "decent": 1, "stretch": 2, "skip": 3}

ENGLISH = {"and", "the", "to", "with", "we", "you", "of", "for", "our", "your", "will", "are", "is", "in",
           "as", "be", "on", "this", "role", "team", "experience", "work", "who", "have"}
OTHER = {  # common words in other European languages job ads are written in
    "og", "til", "med", "vi", "du", "der", "af", "som", "har", "det", "på", "er", "at", "vil", "kan", "skal",
    "ikke", "eller", "din", "dine", "vores", "hos", "samt", "också", "och", "att", "för", "inte",
    "und", "der", "die", "das", "mit", "wir", "sie", "für", "ist", "nicht", "eine", "auf",
    "et", "les", "des", "une", "pour", "nous", "vous", "avec", "est", "dans", "sur",
    "y", "los", "las", "una", "para", "con", "por", "nosotros", "es",
    "en", "het", "een", "voor", "wij", "je", "jij", "niet", "zijn", "bij",
}


# ---------- state ----------

def load() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    return list(csv.DictReader(CSV_PATH.open()))


def save(rows: list[dict]) -> None:
    CURRENT.mkdir(parents=True, exist_ok=True)
    tmp = CSV_PATH.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(CSV_PATH)


@contextlib.contextmanager
def locked():
    CURRENT.mkdir(parents=True, exist_ok=True)
    with (CURRENT / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def key(company: str, title: str, link: str = "") -> str:
    """Company's first word + title without spaces or punctuation ("Power BI" == "PowerBI").
    Without a company name the link stands in, so two "Data Analyst" ads from unknown companies stay apart."""
    first = norm(company).split(" ")[0] if company.strip() else norm(link)
    return f"{first}|{norm(title).replace(' ', '')}"


def seen() -> tuple[set[str], set[str]]:
    """IDs and company|title keys already handled: archived runs and the tracker."""
    ids, keys = set(), set()
    for f in ARCHIVE.glob("*/listings.csv"):
        for r in csv.DictReader(f.open()):
            ids.add(r["id"])
            keys.add(key(r["company"], r["title"], r.get("link", "")))
    for r in tracker.load():
        keys.add(key(r["company"], r["role"]))
    return ids, keys


def language(text: str) -> str:
    words = re.findall(r"[^\W\d_]+", text.lower())
    en = sum(w in ENGLISH for w in words)
    other = sum(w in OTHER and w not in ENGLISH for w in words)
    if en + other < 8:
        return "unknown"
    return "english" if en >= other else "other"


def targets() -> dict:
    t = config.targets()
    terms = [s for s in t.get("search_terms", []) if s.strip()]
    keywords = [k.lower() for k in t.get("title_keywords", []) if k.strip()]
    if not keywords:  # fall back to the words of the search terms
        keywords = sorted({w for term in terms for w in norm(term).split() if len(w) > 2})
    return {
        "terms": terms,
        "keywords": keywords,
        "exclude": [x.lower() for x in t.get("exclude_titles", []) if x.strip()],
        "locations": [x.lower() for x in t.get("locations", []) if x.strip()],
        "location_query": t.get("location_query", ""),
        "english_only": bool(t.get("english_only", True)),
        "max_age_days": int(t.get("max_age_days", 14) or 14),
        "max_jobs": int(t.get("max_jobs_per_run", 10) or 10),
        "min_fit": t.get("min_fit", "decent"),
    }


# ---------- steps ----------

def start(log=print) -> None:
    """Archive the previous run (if it has anything) and open a new one."""
    if CURRENT.exists():
        rows = load()
        if rows:
            label = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            shutil.move(str(CURRENT), str(ARCHIVE / label))
            log(f"archived the previous run ({len(rows)} listings)")
        else:
            shutil.rmtree(CURRENT)
    (CURRENT / "listings").mkdir(parents=True, exist_ok=True)
    save([])


def why_dropped(row: dict, rows: list[dict], known: tuple[set[str], set[str]], cfg: dict) -> str:
    ids, keys = known
    title, loc = row["title"].lower(), row.get("location", "").lower()
    k = key(row["company"], row["title"], row["link"])
    if row["id"] in ids or k in keys:
        return "seen before"
    if any(r["id"] == row["id"] or key(r["company"], r["title"], r["link"]) == k for r in rows):
        return "duplicate"
    if any(word in title for word in cfg["exclude"]):
        return "excluded title"
    if cfg["keywords"] and not any(re.search(rf"\b{re.escape(w)}", title) for w in cfg["keywords"]):
        return "irrelevant title"
    if loc and cfg["locations"] and not any(place in loc for place in cfg["locations"]):
        return "outside your locations"
    posted = row.get("posted", "")
    cutoff = (dt.date.today() - dt.timedelta(days=cfg["max_age_days"])).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", posted) and posted < cutoff:
        return "too old"
    return ""


def add(listing: dict, rows: list[dict] | None = None, known=None, cfg=None) -> str:
    """Add one listing to the current run if new and relevant. Returns why it was dropped, or ''."""
    own = rows is None
    rows = load() if own else rows
    known = known or seen()
    cfg = cfg or targets()
    row = {c: str(listing.get(c, "") or "") for c in COLUMNS}
    if not row["id"]:
        row["id"] = "web-" + hashlib.sha1(row["link"].encode()).hexdigest()[:10]
    why = why_dropped(row, rows, known, cfg)
    if not why:
        rows.append(row | {"found": dt.date.today().isoformat(), "status": "new"})
        if own:
            save(rows)
    return why


def collect(log=print, repair=None) -> dict:
    """Search every enabled site. Returns {site name: {added, dropped reasons..., error}}.

    repair(site, problem) may return new settings for a website that failed or showed no job ads; the
    site is then searched again with them. Sites whose robots.txt forbids access are never repaired."""
    cfg, rows, known = targets(), load(), seen()
    report = {}
    for site in config.sites():
        if not site.get("enabled", True):
            continue
        name = site.get("name") or site.get("id")
        tally: dict = {}
        found, problem = _collect_one(site, cfg, log)
        if problem and repair and site.get("type") == "generic" and not problem.startswith("blocked:"):
            fixed = repair(site, problem)
            if fixed:
                found, problem = _collect_one(fixed, cfg, log)
        if found is None:
            log(f"{name}: failed: {problem.removeprefix('blocked: ')}")
            report[name] = {"error": problem.removeprefix("blocked: ")[:200]}
            continue
        for l in found:
            teaser = l.extra.get("teaser", "")
            if cfg["english_only"] and teaser and language(f"{l.title} {teaser}") == "other":
                tally["not English"] = tally.get("not English", 0) + 1
                continue
            why = add(l.__dict__, rows, known, cfg)
            tally[why or "added"] = tally.get(why or "added", 0) + 1
        save(rows)
        report[name] = tally
        log(f"{name}: " + (", ".join(f"{k} {v}" for k, v in sorted(tally.items())) or "nothing found"))
    return report


def _collect_one(site: dict, cfg: dict, log) -> tuple[list | None, str]:
    """(listings, problem). Listings is None when the site failed; problem is '' when all went well."""
    try:
        found = sites.collect(site, cfg["terms"], cfg["location_query"], log)
    except sites.Blocked as exc:
        return None, f"blocked: {exc}"
    except Exception as exc:  # noqa: BLE001  one broken site should not stop the run
        return None, f"{type(exc).__name__}: {exc}"[:300]
    if not found and site.get("type") == "generic":
        return found, "the page loaded but no job ads were recognised on it"
    return found, ""


def trim_to_title(text: str, title: str) -> str:
    """Drop cookie banners and menus before the ad: start at the first mention of the job title."""
    probe = title.strip()[:30].lower()
    i = text.lower().find(probe) if probe else -1
    return text[i:] if i > 0 and len(text) - i > 800 else text


def fetch(log=print, should_stop=lambda: False) -> dict:
    """Open each new listing in a browser and save its text. Respects robots.txt and spaces requests."""
    from playwright.sync_api import sync_playwright

    cfg, rows = targets(), load()
    todo = [r for r in rows if r["status"] == "new"]
    counts: dict = {}
    if todo:
        log(f"reading {len(todo)} job ads...")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=sites.BROWSER_UA, locale="en-GB")
            for i, r in enumerate(todo, 1):
                if should_stop():
                    break
                try:
                    if not sites.allowed(r["link"]):
                        raise sites.Blocked("robots.txt disallows this page")
                    sites.wait_turn(r["link"])
                    page.goto(r["link"], wait_until="domcontentloaded", timeout=40000)
                    page.wait_for_timeout(2500)
                    r["link"] = page.url
                    text = page.inner_text("body")
                    text = trim_to_title(re.sub(r"\n\s*\n+", "\n\n", text).strip(), r["title"])[:15000]
                except Exception as exc:  # noqa: BLE001
                    r["status"], r["reason"] = "skipped", f"could not open ad: {str(exc)[:80]}"
                else:
                    if len(text) < 400:
                        r["status"], r["reason"] = "skipped", "ad text not readable"
                    elif cfg["english_only"] and language(text) == "other":
                        r["status"], r["reason"] = "skipped", "not an English-language ad"
                    else:
                        (CURRENT / "listings" / f"{r['id']}.txt").write_text(text)
                        r["status"] = "fetched"
                label = r["status"] if r["status"] != "skipped" else f"skipped ({r['reason'].split(':')[0]})"
                counts[label] = counts.get(label, 0) + 1
                if i % 10 == 0:
                    log(f"  read {i}/{len(todo)}")
                    save(rows)
            browser.close()
    save(rows)
    log("read ads: " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "nothing new"))
    return counts


def unscored(chars: int = 1800) -> list[dict]:
    out = []
    for r in load():
        if r["status"] == "fetched" and not r["fit"]:
            text = (CURRENT / "listings" / f"{r['id']}.txt").read_text()
            out.append(r | {"text": re.sub(r"\s+", " ", text)[:chars]})
    return out


def score(scores: list[dict]) -> int:
    """Record [{id, fit, reason}]. Returns how many were applied."""
    with locked():
        rows = load()
        by_id = {r["id"]: r for r in rows}
        n = 0
        for s in scores:
            r = by_id.get(str(s.get("id", "")))
            fit = str(s.get("fit", "")).lower()
            if r is None or fit not in FIT_RANK:
                continue
            r["fit"], r["reason"] = fit, str(s.get("reason", ""))[:200]
            if fit == "skip":
                r["status"] = "skipped"
            n += 1
        save(rows)
        return n


def promote(log=print) -> list[str]:
    """Write the best scored listings to the inbox. Returns the inbox file names."""
    cfg, rows = targets(), load()
    limit = FIT_RANK.get(cfg["min_fit"], 1)
    for r in rows:
        if r["status"] == "fetched" and r["fit"] and FIT_RANK[r["fit"]] > limit:
            r["status"] = "below threshold"
    pool = [r for r in rows if r["status"] == "fetched" and r["fit"] and FIT_RANK[r["fit"]] <= limit]
    pool.sort(key=lambda r: (FIT_RANK[r["fit"]], r["deadline"] or "9999"))
    INBOX.mkdir(parents=True, exist_ok=True)
    promoted = []
    for r in pool:
        if len(promoted) >= cfg["max_jobs"]:
            r["status"], r["reason"] = "held", r["reason"] + " (over this run's limit)"
            continue
        text = (CURRENT / "listings" / f"{r['id']}.txt").read_text()
        header = [
            f"Link: {r['link']}",
            f"Board link: {r['board_link']}" if r["board_link"] and r["board_link"] != r["link"] else "",
            f"Company: {r['company']}" if r["company"] else "",
            f"Title: {r['title']}",
            f"Location: {r['location']}" if r["location"] else "",
            f"Deadline: {r['deadline'] or 'not stated'}",
            f"Fit (scout): {r['fit']}: {r['reason']}",
            f"Scout-ID: {r['id']}",
            "Scouted: yes",
        ]
        name = f"scout-{r['id']}.txt"
        (INBOX / name).write_text("\n".join(h for h in header if h) + "\n\n" + text)
        r["status"] = "promoted"
        promoted.append(name)
    save(rows)
    log(f"chose {len(promoted)} to generate; held back {sum(r['status'] == 'held' for r in rows)}")
    return promoted


def link_jobs(results: dict[str, str]) -> None:
    """results maps Scout-ID -> job folder name ('' if generation failed)."""
    with locked():
        rows = load()
        for r in rows:
            if r["id"] in results:
                r["job_folder"] = results[r["id"]]
                r["status"] = "generated" if results[r["id"]] else "failed"
        save(rows)


def summary() -> dict:
    rows = load()
    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"total": len(rows), "counts": counts, "rows": rows}
