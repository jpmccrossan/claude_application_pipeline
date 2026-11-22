"""Job sources: where /scout looks for listings. Configured in data/config/sites.json (or the Sites page).

Each site is {"id", "name", "type", "enabled", ...type settings}. Types:
    greenhouse   public job-board API, one or more company boards   {"boards": ["example-co", "slug: Display Name"]}
    lever        public job-board API                                {"companies": ["example-co"]}
    ashby        public job-board API                                {"companies": ["example-co"]}
    rss          any RSS or Atom feed of jobs                        {"url": "https://...rss?q={query}"}
    generic      any job website, read in a browser                  {"url": "https://jobs.example.com/search?q=python"}
                 optional: "search_url" with {query} / {location}, "link_pattern" (regex), "wait_ms"

Paste any address and resolve() picks the type: Greenhouse, Lever and Ashby board addresses use their
public APIs, a feed address is read as RSS, anything else is opened in a browser. In the browser, job
links are recognised automatically (guess_job_links); if that fails, Claude can work out the search
address and link pattern from the page (pipeline.repair_site), and the result is tested before use.

Every source is polite by default: robots.txt is checked before any page is fetched, requests to
the same site are spaced out, and the user agent says what it is. See DISCLAIMER.md.
"""
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

UA = "claude-application-pipeline/1.0 (personal job search tool)"
# Pages that need a real browser: a normal browser string, plus the tool's name so sites can tell what it is.
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 " + UA
DELAY_S = 1.5

TYPES = {
    "greenhouse": {
        "label": "Greenhouse company boards",
        "help": "Company careers pages hosted on Greenhouse (URL like boards.greenhouse.io/<slug>). Public API, no scraping.",
        "fields": {"boards": "Company board slugs, one per line. Optional display name: slug: Name"},
    },
    "lever": {
        "label": "Lever company boards",
        "help": "Careers pages hosted on Lever (URL like jobs.lever.co/<slug>). Public API, no scraping.",
        "fields": {"companies": "Company slugs, one per line. Optional display name: slug: Name"},
    },
    "ashby": {
        "label": "Ashby company boards",
        "help": "Careers pages hosted on Ashby (URL like jobs.ashbyhq.com/<slug>). Public API, no scraping.",
        "fields": {"companies": "Company slugs, one per line. Optional display name: slug: Name"},
    },
    "rss": {
        "label": "RSS / Atom feed",
        "help": "Any job feed. Use {query} and {location} in the URL to search each of your search terms.",
        "fields": {"url": "Feed URL"},
    },
    "generic": {
        "label": "Any job website",
        "help": "Paste the address of a page that lists jobs, such as a search results page. Job links are found "
                "automatically. If Test finds nothing, press Ask Claude to fix it. Leave the other boxes blank "
                "unless you know what they do.",
        "fields": {"url": "Website address",
                   "search_url": "Search address (optional; {query} and {location} are filled in from your preferences)",
                   "link_pattern": "Job link pattern (optional regular expression; blank finds job links automatically)"},
    },
}


@dataclass
class Listing:
    id: str
    source: str
    company: str
    title: str
    link: str
    location: str = ""
    deadline: str = ""
    posted: str = ""
    board_link: str = ""
    extra: dict = field(default_factory=dict)


# ---------- politeness ----------

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


def allowed(url: str) -> bool:
    """robots.txt says we may fetch this URL (unreadable robots.txt counts as allowed)."""
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(f"{base}/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                rp.parse(resp.read().decode("utf-8", "replace").splitlines())
            _robots[base] = rp
        except Exception:  # noqa: BLE001  no robots.txt: nothing is disallowed
            _robots[base] = None
    rp = _robots[base]
    return rp is None or rp.can_fetch(UA, url)


def wait_turn(url: str) -> None:
    """Space out requests to the same host."""
    host = urllib.parse.urlsplit(url).netloc
    gap = time.monotonic() - _last_hit.get(host, 0)
    if gap < DELAY_S:
        time.sleep(DELAY_S - gap)
    _last_hit[host] = time.monotonic()


class Blocked(Exception):
    pass


def get(url: str, accept: str = "*/*") -> str:
    if not allowed(url):
        raise Blocked(f"robots.txt does not allow {url}")
    wait_turn(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en,*;q=0.5"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def strip_html(fragment: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def entries(value) -> list[tuple[str, str]]:
    """'slug' or 'slug: Display Name' lines -> [(slug, name)]."""
    items = value if isinstance(value, list) else str(value or "").splitlines()
    out = []
    for item in items:
        item = str(item).strip()
        if not item:
            continue
        slug, _, name = item.partition(":")
        out.append((slug.strip(), name.strip() or slug.strip().replace("-", " ").title()))
    return out


def stable_id(prefix: str, url: str) -> str:
    """Same URL, same id, across runs and restarts."""
    return f"{prefix}-{hashlib.sha1(url.encode()).hexdigest()[:12]}"


def fill(template: str, query: str, location: str) -> str:
    return template.replace("{query}", urllib.parse.quote_plus(query)).replace("{location}", urllib.parse.quote_plus(location))


# ---------- adapters: each yields Listings ----------

def from_greenhouse(site: dict, terms: list[str], location: str, log):
    for slug, name in entries(site.get("boards")):
        data = json.loads(get(f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(slug)}/jobs", "application/json"))
        for j in data.get("jobs", []):
            yield Listing(id=f"gh-{slug}-{j['id']}", source=site["id"], company=j.get("company_name") or name,
                          title=j.get("title", ""), link=j.get("absolute_url", ""),
                          location=(j.get("location") or {}).get("name", ""),
                          posted=(j.get("first_published") or j.get("updated_at") or "")[:10],
                          deadline=(j.get("application_deadline") or "")[:10])


def from_lever(site: dict, terms: list[str], location: str, log):
    for slug, name in entries(site.get("companies")):
        data = json.loads(get(f"https://api.lever.co/v0/postings/{urllib.parse.quote(slug)}?mode=json", "application/json"))
        for j in data:
            cats = j.get("categories") or {}
            posted = time.strftime("%Y-%m-%d", time.gmtime(j["createdAt"] / 1000)) if j.get("createdAt") else ""
            yield Listing(id=f"lv-{slug}-{j['id']}", source=site["id"], company=name, title=j.get("text", ""),
                          link=j.get("hostedUrl", ""), location=cats.get("location", ""), posted=posted)


def from_ashby(site: dict, terms: list[str], location: str, log):
    for slug, name in entries(site.get("companies")):
        data = json.loads(get(f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(slug)}", "application/json"))
        for j in data.get("jobs", []):
            loc = j.get("location", "") + (" (remote)" if j.get("isRemote") else "")
            yield Listing(id=f"ab-{slug}-{j['id']}", source=site["id"], company=name, title=j.get("title", ""),
                          link=j.get("jobUrl", ""), location=loc, posted=(j.get("publishedAt") or "")[:10])


def from_rss(site: dict, terms: list[str], location: str, log):
    url_t = site.get("url", "")
    queries = terms if "{query}" in url_t else [""]
    for term in queries:
        root = ET.fromstring(get(fill(url_t, term, location), "application/rss+xml, application/atom+xml, */*"))
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//a:entry", ns)
        for it in items:
            title = (it.findtext("title") or it.findtext("a:title", namespaces=ns) or "").strip()
            link = (it.findtext("link") or "").strip()
            if not link:
                el = it.find("a:link", ns)
                link = el.get("href", "") if el is not None else ""
            company = ""
            m = re.match(r"(.+?)\s+at\s+(.+)$", title)  # "Role at Company"
            n = re.match(r"([^:]{2,60}):\s+(.+)$", title)  # "Company: Role"
            if m:
                title, company = m.group(1).strip(), m.group(2).strip()
            elif n:
                company, title = n.group(1).strip(), n.group(2).strip()
            yield Listing(id=stable_id("rss", link), source=site["id"], company=company, title=title,
                          link=link, posted=(it.findtext("pubDate") or "")[:16])


JOB_WORDS = re.compile(  # "job" in the address of a job ad, in several languages
    r"job|career|vacanc|position|opening|posting|opportunit|recruit|hiring|stilling|stelle|emploi|empleo|"
    r"vacature|lavoro|vaga|oferta|offre|annonce|rekry|tyopaik|praca|baito|shigoto", re.I)


def host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def same_site(a: str, b: str) -> bool:
    ha, hb = host(a), host(b)
    return bool(ha) and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha))


def _shape(url: str) -> str:
    """Links to ads on one site share a shape: same folder, different last part."""
    parts = urllib.parse.urlsplit(url)
    segs = [x for x in parts.path.split("/") if x]
    if len(segs) >= 2:
        return parts.netloc + "/" + "/".join(re.sub(r"\d+", "N", x) for x in segs[:-1]) + "/*"
    keys = sorted(k for k, _ in urllib.parse.parse_qsl(parts.query))
    return parts.netloc + parts.path + "?" + "&".join(keys)


def _looks_like_item(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    last = [x for x in parts.path.split("/") if x][-1:] or [""]
    return bool(re.search(r"\d", last[0]) or last[0].count("-") >= 2 or parts.query)


def guess_job_links(page_url: str, links: list) -> list:
    """The largest group of same-site links that look like job ads, or [] if none do."""
    here = page_url.split("#")[0].rstrip("/")
    groups: dict[str, dict[str, str]] = {}
    for href, text in links:
        href = href.split("#")[0]
        first = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
        if (not href.startswith("http") or href.rstrip("/") == here or not same_site(href, page_url)
                or len(first) < 6 or not _looks_like_item(href)):
            continue
        parts = urllib.parse.urlsplit(href)
        if not JOB_WORDS.search(parts.path + "?" + parts.query):
            continue
        groups.setdefault(_shape(href), {}).setdefault(href, text)
    best = max(groups.values(), key=len, default={})
    return list(best.items()) if len(best) >= 2 else []


def open_page(page, url: str, wait_ms: int = 2500) -> list:
    """Load url in a Playwright page (robots.txt and spacing respected). Returns [[href, text], ...]."""
    if not allowed(url):
        raise Blocked(f"robots.txt does not allow {url}")
    wait_turn(url)
    page.goto(url, wait_until="domcontentloaded", timeout=40000)
    page.wait_for_timeout(wait_ms)
    return page.eval_on_selector_all(
        "a[href]", """els => els.map(e => [e.href, ((e.innerText || '').trim() || e.getAttribute('aria-label')
            || (e.parentElement && e.parentElement.innerText) || '').trim()])""")


def read_page(url: str, wait_ms: int = 2500) -> dict:
    """What a page offers, for Claude to work out a site's settings: final address, title, links, search forms."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=BROWSER_UA)
        try:
            links = open_page(page, url, wait_ms)
            forms = page.eval_on_selector_all(
                "form", """fs => fs.map(f => ({action: f.action, method: f.method,
                    inputs: [...f.querySelectorAll('input,select')].filter(i => i.type !== 'hidden' || i.name)
                        .map(i => ({name: i.name, type: i.type, placeholder: i.placeholder || '', value: i.type === 'hidden' ? i.value : ''}))}))""")
            return {"url": page.url, "title": page.title(), "links": links, "forms": forms}
        finally:
            browser.close()


def page_address(site: dict) -> str:
    return (site.get("search_url") or site.get("url") or "").strip()


def from_generic(site: dict, terms: list[str], location: str, log):
    from playwright.sync_api import sync_playwright

    url_t = page_address(site)
    if not url_t.startswith(("http://", "https://")):
        raise ValueError("add the website address (starting with https://)")
    pattern = re.compile(site["link_pattern"]) if site.get("link_pattern") else None
    queries = terms if "{query}" in url_t else [""]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=BROWSER_UA)
        try:
            for term in queries:
                url = fill(url_t, term, location)
                links = open_page(page, url, int(site.get("wait_ms") or 2500))
                if pattern:
                    found = {}
                    for href, text in links:
                        href = href.split("#")[0]
                        if pattern.search(href) and text and href not in found:
                            found[href] = text
                    links = list(found.items())
                else:
                    links = guess_job_links(page.url, links)
                for href, text in links:
                    lines = [l.strip() for l in text.splitlines() if l.strip()]
                    yield Listing(id=stable_id("web", href), source=site["id"],
                                  company=lines[1] if len(lines) > 2 else "", title=lines[0][:150], link=href,
                                  location=lines[2] if len(lines) > 2 else "")
        finally:
            browser.close()


ATS_HOSTS = {"boards.greenhouse.io": "greenhouse", "job-boards.greenhouse.io": "greenhouse",
             "jobs.lever.co": "lever", "jobs.ashbyhq.com": "ashby"}


def resolve(url: str, terms: list[str]) -> dict:
    """A site config for any pasted address. Raises Blocked if robots.txt forbids it."""
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    if not parts.netloc or " " in parts.netloc:
        raise ValueError("that does not look like a website address")
    name = host(url)
    kind = ATS_HOSTS.get(parts.netloc.lower())
    slug = next((x for x in parts.path.split("/") if x), "")
    if kind and slug:
        key = "boards" if kind == "greenhouse" else "companies"
        return {"name": f"{slug} ({TYPES[kind]['label']})", "type": kind, "enabled": True, key: [slug]}
    if not allowed(url):
        raise Blocked(f"{name} does not allow automated access (robots.txt)")
    if re.search(r"rss|atom|feed|\.xml$", parts.path + "?" + parts.query, re.I):
        try:
            head = get(url, "application/rss+xml, application/atom+xml, */*")[:2000].lower()
            if "<rss" in head or "<feed" in head:
                return {"name": f"{name} feed", "type": "rss", "enabled": True, "url": url}
        except Blocked:
            raise
        except Exception:  # noqa: BLE001  not a feed after all: read it as a page
            pass
    site = {"name": name, "type": "generic", "enabled": True, "url": url}
    # A search results address that contains one of the search terms becomes a template for all of them.
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    lowered = {t.strip().lower() for t in terms}
    for i, (k, v) in enumerate(query):
        if v.strip().lower() in lowered:
            query[i] = (k, "{query}")
            q = urllib.parse.urlencode(query, safe="{}")
            site["search_url"] = urllib.parse.urlunsplit(parts._replace(query=q))
            break
    return site


ADAPTERS = {
    "greenhouse": from_greenhouse, "lever": from_lever, "ashby": from_ashby, "rss": from_rss,
    "generic": from_generic,
}


def collect(site: dict, terms: list[str], location: str = "", log=print, limit: int = 0) -> list[Listing]:
    """All listings from one site. Raises on a broken site so the caller can report it."""
    adapter = ADAPTERS.get(site.get("type", ""))
    site = site if site.get("id") else site | {"id": "new"}  # not saved yet (Test before Save)
    if adapter is None:
        raise ValueError(f"unknown site type '{site.get('type')}'")
    out = []
    for listing in adapter(site, terms, location, log):
        if listing.title and listing.link:
            out.append(listing)
            if limit and len(out) >= limit:
                break
    return out


def test(site: dict, terms: list[str], location: str = "") -> dict:
    """Try a site with the first search term and show what it returns."""
    try:
        found = collect(site, terms[:1] or ["developer"], location, limit=200)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400], "count": 0, "sample": []}
    sample = [{"company": l.company, "title": l.title, "location": l.location, "link": l.link} for l in found[:15]]
    return {"ok": bool(found), "error": "" if found else "no listings found; check the settings",
            "count": len(found), "sample": sample}
