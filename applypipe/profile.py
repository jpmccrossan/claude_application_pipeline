"""The person: profile.json (structured, drives the CV layout) and facts.md (the source of truth).

profile.json holds fixed identity text (name, contact, employers, dates, education, skills) and the
default wording of every field that can be tailored per job. facts.md is everything true about the
person, in plain words; nothing may be claimed in an application that is not in it.
"""
import json
import re
from pathlib import Path

from .paths import EXAMPLES, PROFILE_DIR, TEMPLATES

PROFILE = PROFILE_DIR / "profile.json"
FACTS = PROFILE_DIR / "facts.md"
STYLE_NOTES = PROFILE_DIR / "style_notes.md"
PHOTO_NAMES = ("photo.jpg", "photo.jpeg", "photo.png")

# Letter fields: character budgets that fit the one-page letter layout.
LETTER_BUDGETS = {
    "p1": (240, 400), "p2": (420, 700), "p3": (380, 650), "p4": (300, 560),
    "p5": (200, 420), "p6": (110, 250),
    "short_col1_head": (8, 30), "short_col2_head": (8, 30),
    "short_col1": (90, 230), "short_col2": (90, 230), "role_banner": (6, 60),
}


def has_profile() -> bool:
    return PROFILE.exists()


def load(example: bool = False) -> dict:
    path = EXAMPLES / "profile" / "profile.json" if example or not PROFILE.exists() else PROFILE
    return json.loads(path.read_text())


def facts(example: bool = False) -> str:
    path = EXAMPLES / "profile" / "facts.md" if example or not FACTS.exists() else FACTS
    return path.read_text()


def style_notes() -> str:
    return STYLE_NOTES.read_text() if STYLE_NOTES.exists() else ""


def photo(example: bool = False) -> Path | None:
    folder = EXAMPLES / "profile" if example else PROFILE_DIR
    return next((folder / n for n in PHOTO_NAMES if (folder / n).exists()), None)


def file_stem(profile: dict) -> str:
    """'Sam Rivera' -> 'Sam_Rivera', used in PDF names."""
    return re.sub(r"[^A-Za-z0-9-]+", "_", profile.get("name", "Applicant")).strip("_") or "Applicant"


def doc_names(profile: dict) -> dict[str, str]:
    stem = file_stem(profile)
    return {"cv": f"{stem}_CV.pdf", "letter": f"{stem}_Cover_Letter.pdf", "bundle": f"{stem}_Application.pdf"}


def validate(profile: dict) -> list[str]:
    """Problems that would break rendering. Empty list means the profile is usable."""
    errors = []
    if not str(profile.get("name", "")).strip():
        errors.append("name is missing")
    for i, job in enumerate(profile.get("experience", [])):
        if not job.get("id") or not re.fullmatch(r"[a-z0-9_]+", job["id"]):
            errors.append(f"experience[{i}].id must be lowercase letters, digits or _")
        if not isinstance(job.get("bullets", []), list):
            errors.append(f"experience[{i}].bullets must be a list")
    ids = [j.get("id") for j in profile.get("experience", [])]
    if len(ids) != len(set(ids)):
        errors.append("experience ids must be unique")
    for i, group in enumerate(profile.get("skills", [])):
        if not group.get("name") or not isinstance(group.get("chips"), list):
            errors.append(f"skills[{i}] needs a name and a list of chips")
    if len(profile.get("summary", [])) < 1:
        errors.append("summary needs at least one paragraph")
    return errors


def available_icons() -> list[str]:
    return sorted(p.stem for p in (TEMPLATES / "assets" / "icons").glob("*.svg"))


def _budget(text: str, low: float = 0.75, high: float = 1.2) -> dict:
    n = len(text.replace("**", ""))
    return {"default": text, "min": round(n * low), "max": round(n * high)}


def schema(profile: dict) -> dict:
    """Every field a job can tailor, with its default and character budget."""
    summary = profile.get("summary", [])
    out = {"tagline": _budget(profile.get("headline", ""), 0.6, 1.25)}
    for i, text in enumerate(summary[:2], start=1):
        out[f"summary_{i}"] = _budget(text)
    out["experience"] = {
        job["id"]: {
            "role": f"{job.get('title', '')}, {job.get('org', '')}",
            "bullets": [_budget(b) for b in job.get("bullets", [])],
            "note": f"give at most {len(job.get('bullets', []))} bullets; they may be reworded, reordered or dropped",
        }
        for job in profile.get("experience", [])
    }
    out["beyond"] = [
        {"heading": b.get("heading", ""), **_budget(b.get("text", ""))} for b in profile.get("beyond", [])
    ]
    for key, (lo, hi) in LETTER_BUDGETS.items():
        out[key] = {"min": lo, "max": hi}
    out["p4"]["optional"] = True
    out["skills_order"] = {
        "note": "object: group name -> that group's chips, reordered only (never add or remove)",
        "groups": {g["name"]: g["chips"] for g in profile.get("skills", [])},
    }
    return out


def length_warnings(profile: dict, content: dict) -> list[str]:
    """Fields outside their budget. Warnings only; the one-page check is what fails a render."""
    warnings = []
    spec = schema(profile)

    def check(name: str, text, lo: int, hi: int):
        if not isinstance(text, str):
            return
        n = len(text.replace("**", ""))
        if n and not lo <= n <= hi:
            warnings.append(f"{name}: {n} chars, target {lo}-{hi}")

    for key, s in spec.items():
        if isinstance(s, dict) and "min" in s and key in content:
            check(key, content[key], s["min"], s["max"])
    for job_id, bullets in (content.get("experience") or {}).items():
        budgets = spec["experience"].get(job_id, {}).get("bullets", [])
        if budgets:
            hi = max(b["max"] for b in budgets)
            lo = min(b["min"] for b in budgets)
            for i, text in enumerate(bullets):
                check(f"experience.{job_id}[{i}]", text, lo, hi)
    for i, text in enumerate(content.get("beyond") or []):
        if i < len(spec["beyond"]):
            check(f"beyond[{i}]", text, spec["beyond"][i]["min"], spec["beyond"][i]["max"])
    return warnings
