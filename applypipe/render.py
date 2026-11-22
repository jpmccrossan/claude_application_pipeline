"""Render one application: content.json + profile + templates -> self-contained HTML -> one-page PDFs.

Usage:
    python -m applypipe.render data/output/<YYMMDD>/<job folder> [--dry] [--bundle]
    python -m applypipe.render --example        render the example person, as a self-test

Reads   <job>/source/content.json and data/profile/profile.json
Writes  <job>/HTML/cv.html, <job>/HTML/letter.html   (fonts and images inlined, open anywhere)
        <job>/<Name>_CV.pdf, <job>/<Name>_Cover_Letter.pdf
        <job>/<Name>_Application.pdf  (letter + CV, only with --bundle or "bundle": true)
        <job>/APPLY.md  (link, deadline, how to apply, checklist)
Runs the rule checks first and stops on errors. Fails if either document overflows its A4 page.
"""
import argparse
import base64
import colorsys
import datetime as dt
import html
import re
import shutil
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined
from markupsafe import Markup

from . import check, profile as profiles
from .jobfiles import read_content
from .paths import EXAMPLES, TEMPLATES

DEFAULT_ACCENT = "#2036d9"
# Blue family used by the design; re-hued together when another accent is chosen.
BLUE_FAMILY = ["#2036d9", "#1626a3", "#2b47f0", "#1c2fc4", "#d8dffa", "#e9ecfa", "#f2f1fb", "#dde2f7",
               "#d0daf8", "#e9ebfb", "#e2e7fb", "#f1f1fb", "#e6e9fb"]


def md(text: str) -> Markup:
    """Escape, then turn **bold** into <strong>."""
    escaped = html.escape(text or "", quote=False)
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped))


def build_skills(profile: dict, order: dict | None) -> list[dict]:
    """skills_order maps group name -> chips. Chips may be reordered, never added or removed."""
    groups = []
    for group in profile.get("skills", []):
        chips = list(group["chips"])
        wanted = (order or {}).get(group["name"])
        if wanted and sorted(wanted) == sorted(chips):
            chips = list(wanted)
        elif wanted:
            print(f"note: skills_order['{group['name']}'] ignored, it must reorder exactly: {chips}")
        groups.append({"name": group["name"], "style": group.get("style", "plain"), "chips": chips})
    return groups


def context(profile: dict, content: dict, example: bool = False) -> dict:
    """Everything the two templates need, with profile defaults for anything not tailored."""
    name = profile.get("name", "").split()
    summary = list(profile.get("summary", []))
    for i in range(len(summary[:2])):
        summary[i] = content.get(f"summary_{i + 1}") or summary[i]
    experience = []
    tailored = content.get("experience") or {}
    for job in profile.get("experience", []):
        bullets = tailored.get(job["id"]) or job.get("bullets", [])
        experience.append(job | {"bullets": [b for b in bullets if str(b).strip()]})
    beyond = []
    texts = content.get("beyond") or []
    for i, b in enumerate(profile.get("beyond", [])):
        beyond.append({"heading": b.get("heading", ""), "text": texts[i] if i < len(texts) and texts[i] else b.get("text", "")})
    photo = profiles.photo(example)
    show_photo = photo and profile.get("photo", True) and content.get("photo", True) is not False
    letter = profile.get("letter", {})
    paragraphs = [content[k] for k in ("p1", "p2", "p3", "p4", "p5", "p6") if str(content.get(k, "")).strip()]
    icons_dir = TEMPLATES / "assets" / "icons"
    return {
        "p": profile | {"education": profile.get("education", []), "extras": profile.get("extras", []),
                        "contact": profile.get("contact", []), "banner": profile.get("banner", ""),
                        "highlight": profile.get("highlight", ""), "languages": profile.get("languages", ""),
                        "references": profile.get("references", "")},
        "name_first": " ".join(name[:-1]) if len(name) > 1 else "",
        "name_last": name[-1] if name else "",
        "tagline": content.get("tagline") or profile.get("headline", ""),
        "summary": summary,
        "experience": experience,
        "beyond": beyond,
        "skills": build_skills(profile, content.get("skills_order")),
        "icons": [i for i in profile.get("stack_icons", []) if (icons_dir / f"{i}.svg").exists()],
        "photo_src": data_uri(photo) if show_photo else "",
        "letter_date": content.get("letter_date") or dt.date.today().strftime("%B %Y"),
        "topbar": content.get("topbar") or f"Cover letter · {content.get('role_banner', '')}",
        "recipient_names": content.get("recipient_names", ""),
        "company_line": content.get("company_line", ""),
        "role_banner": content.get("role_banner", ""),
        "salutation": content.get("salutation") or letter.get("default_salutation", "Dear Hiring Manager,"),
        "paragraphs": paragraphs,
        "signoff": letter.get("signoff", "Kind regards,"),
        "short_col1_head": content.get("short_col1_head", ""),
        "short_col1": content.get("short_col1", ""),
        "short_col2_head": content.get("short_col2_head", ""),
        "short_col2": content.get("short_col2", ""),
        "availability_heading": letter.get("availability_heading", "Availability"),
        "availability": letter.get("availability", ""),
        "accent": content.get("accent_hex") or profile.get("accent") or DEFAULT_ACCENT,
    }


def recolour(markup: str, accent: str) -> str:
    """Shift the whole blue family to the accent's hue, keeping each tint's lightness."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent or "") or accent.lower() == DEFAULT_ACCENT:
        return markup

    def hls(hex_):
        r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hls(r, g, b)

    _, base_l, base_s = hls(DEFAULT_ACCENT)
    new_h, new_l, new_s = hls(accent)
    for hex_ in BLUE_FAMILY:
        _, l, s = hls(hex_)
        if l < 0.7:  # saturated tones follow the accent's lightness too
            l = min(max(l + new_l - base_l, 0), 1)
        s = min(s * (new_s / base_s if base_s else 1), 1)
        r, g, b = colorsys.hls_to_rgb(new_h, l, s)
        markup = re.sub(hex_, "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255)), markup, flags=re.I)
    return markup


def data_uri(path: Path) -> str:
    mime = {".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}[path.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def inline_assets(markup: str) -> str:
    """Make the HTML self-contained: fonts and icons become data URIs."""
    fonts_css = (TEMPLATES / "fonts" / "fonts.css").read_text()
    fonts_css = re.sub(
        r"url\((font_\d+\.woff2)\)",
        lambda m: f"url(data:font/woff2;base64,{base64.b64encode((TEMPLATES / 'fonts' / m.group(1)).read_bytes()).decode()})",
        fonts_css,
    )
    markup = markup.replace('<link href="fonts/fonts.css" rel="stylesheet">', f"<style>{fonts_css}</style>")
    return re.sub(r'src="(assets/[^"]+)"', lambda m: f'src="{data_uri(TEMPLATES / m.group(1))}"', markup)


def render_html(job: Path, ctx: dict) -> dict[str, Path]:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True, undefined=Undefined)
    env.filters["md"] = md
    out_dir = job / "HTML"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name in ("cv", "letter"):
        markup = recolour(env.get_template(f"{name}.html").render(**ctx), ctx["accent"])
        paths[name] = out_dir / f"{name}.html"
        paths[name].write_text(inline_assets(markup))
    return paths


# Overflow is invisible in the PDF (the page box clips), so measure it in the browser instead.
FIT_JS = """() => {
  const page = document.body.firstElementChild;
  const pageBox = page.getBoundingClientRect();
  const footer = [...page.querySelectorAll('div')].filter(d => d.style.margin.startsWith('auto')).pop();
  let lowest = 0;
  // Every descendant, because flex items can shrink and let their text spill past their own box.
  for (const el of (footer ? footer.parentElement : page).querySelectorAll('*')) {
    if ((footer && footer.contains(el)) || el.closest('[aria-hidden]')) continue;
    lowest = Math.max(lowest, el.getBoundingClientRect().bottom);
  }
  const footerBox = footer ? footer.getBoundingClientRect() : {top: pageBox.bottom, bottom: pageBox.bottom};
  // Negative slack = pixels of text that need cutting (gap closed, footer pushed past the page edge).
  return {
    slack: Math.round(footerBox.top - lowest - Math.max(0, footerBox.bottom - pageBox.bottom)),
    overflowY: page.scrollHeight - page.clientHeight,
  };
}"""


def render_pdfs(job: Path, html_paths: dict[str, Path], names: dict[str, str]) -> tuple[list[str], dict]:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader

    errors, results = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for name, path in html_paths.items():
            page.goto(path.resolve().as_uri())
            page.evaluate("document.fonts.ready")
            fit = page.evaluate(FIT_JS)
            pdf = job / names[name]
            page.pdf(path=str(pdf), format="A4", print_background=True, prefer_css_page_size=True)
            pages = len(PdfReader(pdf).pages)
            ok = pages == 1 and fit["slack"] >= 0 and fit["overflowY"] <= 1
            results[name] = {"ok": ok, "pages": pages, "free_px": fit["slack"]}
            print(f"{name}: {'ok' if ok else 'FAIL'}  pages={pages}  free space above footer={fit['slack']}px")
            if not ok:
                errors.append(f"{name} does not fit on one page: shorten its text by roughly {max(-fit['slack'], 0) + 10}px of lines")
        browser.close()
    return errors, results


def render_job(job: Path, dry: bool = False, bundle: bool = False, example: bool = False) -> dict:
    """Check, render and write APPLY.md. Returns {ok, errors, warnings, results}."""
    job = Path(job)
    profile = profiles.load(example)
    errors, warnings = check.check(job, example=example)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "results": {}}
    content = read_content(job)
    warnings += profiles.length_warnings(profile, content)
    html_paths = render_html(job, context(profile, content, example))
    if dry:
        return {"ok": True, "errors": [], "warnings": warnings, "results": {}}
    names = profiles.doc_names(profile)
    errors, results = render_pdfs(job, html_paths, names)
    if not errors:
        if bundle or content.get("bundle"):
            write_bundle(job, names)
        write_apply_sheet(job, content, names)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "results": results}


def write_apply_sheet(job: Path, content: dict, names: dict) -> None:
    """APPLY.md: everything needed to send this application by hand."""
    job_txt = job / "source" / "job.txt"
    header = job_txt.read_text()[:3000] if job_txt.exists() else ""
    link = content.get("url") or next(iter(re.findall(r"^Link: (\S+)", header, re.M)), "")
    files = [names["letter"], names["cv"]] + ([names["bundle"]] if (job / names["bundle"]).exists() else [])
    lines = [
        f"# {content.get('role', '')} at {content.get('company', '')}",
        "",
        f"- Link: {link or 'not recorded (see source/job.txt)'}",
        f"- Deadline: {content.get('deadline') or 'not stated'}",
        f"- Location: {content.get('location') or 'not stated'}",
        (f"- Address to: {content['recipient_names']} ({content.get('addressee_confidence') or 'confidence not recorded'})"
         if content.get("recipient_names") else "- Address to: no named person found (letter uses the default salutation)"),
        f"- Contact: {content.get('contact_email') or 'none given'}",
        f"- Fit: {content.get('fit') or 'not scored'}",
        f"- How to apply: {content.get('apply_how') or 'see the link'}",
        "",
        "## Before sending",
        *[f"- {item}" for item in (content.get("todo") or ["Read both PDFs once."])],
        "",
        "## Files",
        *[f"- {name}" for name in files],
        "- HTML/ (the same documents as web pages)",
    ]
    (job / "APPLY.md").write_text("\n".join(lines) + "\n")


def write_bundle(job: Path, names: dict) -> None:
    """Cover letter then CV in one PDF, for applications that ask for a single file."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for name in ("letter", "cv"):
        writer.append(str(job / names[name]))
    writer.write(str(job / names["bundle"]))
    print(f"bundle: {names['bundle']}")


def example_job() -> Path:
    """A throwaway job folder holding the example content, for self-tests and previews."""
    work = Path(tempfile.mkdtemp(prefix="applypipe-example-"))
    (work / "source").mkdir()
    shutil.copy(EXAMPLES / "content.json", work / "source" / "content.json")
    return work


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", type=Path, nargs="?")
    ap.add_argument("--dry", action="store_true", help="write HTML only, skip PDFs")
    ap.add_argument("--bundle", action="store_true", help="also write letter + CV as one PDF")
    ap.add_argument("--example", action="store_true", help="render the example person (self-test)")
    args = ap.parse_args()
    if not args.job and not args.example:
        ap.error("give a job folder or --example")
    job = example_job() if args.example else args.job
    result = render_job(job, dry=args.dry, bundle=args.bundle, example=args.example)
    for w in result["warnings"]:
        print(f"warning: {w}")
    if args.example:
        print(f"output in {job}")
    if not result["ok"]:
        sys.exit("\n".join(f"error: {e}" for e in result["errors"]))


if __name__ == "__main__":
    main()
