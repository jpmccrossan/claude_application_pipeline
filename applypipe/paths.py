"""Where everything lives.

Code, prompts and templates sit in the repository. Everything personal (profile, CV, settings,
generated applications, the tracker) lives under data/, which is git-ignored. Set APPLYPIPE_DATA to
keep it somewhere else.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("APPLYPIPE_DATA") or ROOT / "data").resolve()

PROFILE_DIR = DATA / "profile"
CONFIG_DIR = DATA / "config"
INBOX = DATA / "inbox"
OUTPUT = DATA / "output"
RESEARCH = DATA / "research"
SCOUT = DATA / "scout"
TRACKER_DIR = DATA / "tracker"
RUNS = DATA / "runs"
CHATS = DATA / "chats"

PROMPTS = ROOT / "prompts"
TEMPLATES = ROOT / "templates"
EXAMPLES = ROOT / "examples"

PYTHON = sys.executable


def ensure_dirs() -> None:
    for d in (PROFILE_DIR, CONFIG_DIR, INBOX, OUTPUT, RESEARCH, SCOUT, TRACKER_DIR, RUNS, CHATS):
        d.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    """Path relative to the repo root when possible (shorter in logs and prompts)."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)
