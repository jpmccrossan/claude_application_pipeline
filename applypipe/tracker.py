"""The tracking CSV: one row per application.

Statuses are free text; common ones: ready (generated, not yet sent), applied, followed up,
interview, rejected, offer, withdrawn. Setting "applied" or "followed up" sets the follow-up date
10 days on.
"""
import contextlib
import csv
import datetime as dt
import fcntl

from .jobfiles import read_content
from .paths import TRACKER_DIR

CSV_PATH = TRACKER_DIR / "applications.csv"
COLUMNS = [
    "date", "company", "role", "location", "fit", "deadline", "url", "hiring_manager",
    "addressee_confidence", "contact_email", "status", "status_date", "follow_up_date", "notes", "folder",
]
FOLLOW_UP_DAYS = 10
OPEN = {"applied", "followed up"}
STATUSES = ["ready", "applied", "followed up", "interview", "offer", "rejected", "withdrawn"]


@contextlib.contextmanager
def locked():
    """Serialise read-modify-write of the CSV: applications are logged in parallel."""
    TRACKER_DIR.mkdir(parents=True, exist_ok=True)
    with (TRACKER_DIR / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    rows = list(csv.DictReader(CSV_PATH.open()))
    for row in rows:
        for col in COLUMNS:
            row.setdefault(col, "")
    return rows


def save(rows: list[dict]) -> None:
    TRACKER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CSV_PATH.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(CSV_PATH)


def plus_days(iso: str, days: int) -> str:
    return (dt.date.fromisoformat(iso) + dt.timedelta(days=days)).isoformat()


def log(job, status: str = "ready", notes: str = "") -> bool:
    """Add a rendered job to the tracker. False if it is already there."""
    with locked():
        rows = load()
        folder = job.name
        if any(r["folder"] == folder for r in rows):
            return False
        content = read_content(job)
        today = dt.date.today().isoformat()
        rows.append({
            **{col: str(content.get(col, "")) for col in COLUMNS},
            "date": today, "status": status, "status_date": today,
            "follow_up_date": plus_days(today, FOLLOW_UP_DAYS) if status in OPEN else "",
            "notes": notes, "folder": folder,
        })
        save(rows)
        return True


def set_status(folder: str, status: str, note: str = "") -> dict:
    with locked():
        rows = load()
        row = next((r for r in rows if r["folder"] == folder), None)
        if row is None:
            raise KeyError(folder)
        today = dt.date.today().isoformat()
        row["status"], row["status_date"] = status, today
        if status in OPEN:
            row["follow_up_date"] = plus_days(today, FOLLOW_UP_DAYS)
        if note:
            row["notes"] = f"{row['notes']}; {today}: {note}".lstrip("; ")
        save(rows)
        return row


def rename_folder(old: str, new: str) -> None:
    with locked():
        rows = load()
        for r in rows:
            if r["folder"] == old:
                r["folder"] = new
        save(rows)


def followups() -> dict:
    rows, today = load(), dt.date.today().isoformat()
    ready = [r for r in rows if r["status"] == "ready" and (not r["deadline"] or r["deadline"] >= today)]
    due = [r for r in rows if r["status"] in OPEN and r["follow_up_date"] and r["follow_up_date"] <= today]
    return {
        "ready": sorted(ready, key=lambda r: r["deadline"] or "9999"),
        "due": sorted(due, key=lambda r: r["follow_up_date"]),
    }
