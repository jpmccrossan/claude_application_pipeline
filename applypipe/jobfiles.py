"""Job folders: create them from inbox files, and read content.json the same way everywhere."""
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

from .paths import INBOX, OUTPUT

GROUPS = ("meta", "shared", "letter", "cv")


def read_content(job: Path) -> dict:
    """content.json as one flat object. Models sometimes group keys under "meta", "letter" or "cv":
    those groups are flattened (and the file rewritten flat) so every reader sees the same keys."""
    path = Path(job) / "source" / "content.json"
    content = json.loads(path.read_text())
    if any(isinstance(content.get(g), dict) for g in GROUPS):
        flat = {k: v for k, v in content.items() if k not in GROUPS or not isinstance(v, dict)}
        for g in GROUPS:
            if isinstance(content.get(g), dict):
                for k, v in content[g].items():
                    flat.setdefault(k, v)
        path.write_text(json.dumps(flat, indent=1, ensure_ascii=False))
        content = flat
    return content


def slug(text: str) -> str:
    """Filesystem-safe: & becomes "and", anything not a letter or digit becomes one underscore."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text.replace("&", " and ")).strip("_")[:60]


def waiting() -> list[Path]:
    """Non-empty .txt files in the inbox, oldest first. Exact duplicates are skipped."""
    INBOX.mkdir(parents=True, exist_ok=True)
    files = sorted((f for f in INBOX.glob("*.txt") if f.read_text().strip()), key=lambda f: f.stat().st_mtime)
    seen, unique = set(), []
    for f in files:
        digest = hashlib.sha1(" ".join(f.read_text().split()).encode()).hexdigest()
        if digest not in seen:
            seen.add(digest)
            unique.append(f)
    return unique


def add_to_inbox(text: str, name: str = "") -> Path:
    INBOX.mkdir(parents=True, exist_ok=True)
    stem = slug(name) or dt.datetime.now().strftime("pasted_%y%m%d_%H%M%S")
    path = INBOX / f"{stem}.txt"
    n = 2
    while path.exists():
        path = INBOX / f"{stem}_{n}.txt"
        n += 1
    path.write_text(text.strip() + "\n")
    return path


def new_workdir(source: Path) -> Path:
    """A job folder before the company and role are known: data/output/YYMMDD/YYMMDD_HHMMSS_pending/.
    The inbox file moves to source/job.txt. finalise() renames it once content.json exists."""
    now = dt.datetime.now()
    job = OUTPUT / f"{now:%y%m%d}" / f"{now:%y%m%d_%H%M%S}_{slug(source.stem)}_pending"
    n = 2
    while job.exists():
        job = job.with_name(f"{job.name}{n}")
        n += 1
    (job / "source").mkdir(parents=True)
    shutil.move(str(source), job / "source" / "job.txt")
    return job


def finalise(job: Path) -> Path:
    """Rename a pending folder to YYMMDD_HHMM_Company_Role from its content.json."""
    content = read_content(job)
    stamp = job.name[:11]  # YYMMDD_HHMM
    target = job.parent / f"{stamp}_{slug(content.get('company', 'Company'))}_{slug(content.get('role', 'Role'))}"
    if target == job:
        return job
    n = 2
    while target.exists():
        target = target.with_name(f"{target.name}_{n}")
        n += 1
    job.rename(target)
    return target


def job_folders() -> list[Path]:
    return sorted((p.parent.parent for p in OUTPUT.glob("*/*/source/content.json")), key=lambda p: p.name)


def find_job(name: str) -> Path | None:
    """A job folder by its folder name."""
    for p in OUTPUT.glob(f"*/{name}"):
        if p.is_dir():
            return p
    return None
