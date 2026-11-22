"""Settings, job preferences (targets), job sites and secrets: JSON files under data/config/.

Missing files fall back to the examples in examples/config/, so a fresh checkout works.
"""
import json
import os
from pathlib import Path

from .paths import CONFIG_DIR, EXAMPLES

DEFAULT_SETTINGS = {
    "engine": "auto",            # "auto", "claude-code" or "api"
    "model": "",                 # blank: Claude Code's default, or claude-opus-5-5 for the API engine
    "max_parallel": 3,           # applications generated at once
    "disclaimer_accepted": False,
    "onboarded": False,
}


def _read(name: str) -> dict | list | None:
    path = CONFIG_DIR / name
    if path.exists():
        return json.loads(path.read_text())
    example = EXAMPLES / "config" / name
    if example.exists():
        return json.loads(example.read_text())
    return None


def _write(name: str, value) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_DIR / f".{name}.tmp"
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    tmp.replace(CONFIG_DIR / name)


def settings() -> dict:
    return DEFAULT_SETTINGS | (_read("settings.json") or {})


def save_settings(values: dict) -> dict:
    merged = settings() | {k: v for k, v in values.items() if k in DEFAULT_SETTINGS}
    _write("settings.json", merged)
    return merged


def targets() -> dict:
    return _read("targets.json") or {}


def save_targets(values: dict) -> None:
    _write("targets.json", values)


def sites() -> list[dict]:
    return _read("sites.json") or []


def save_sites(values: list[dict]) -> None:
    _write("sites.json", values)


# ---------- secrets (API key), never sent back to the browser ----------

SECRETS = CONFIG_DIR / "secrets.json"


def api_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if SECRETS.exists():
        return json.loads(SECRETS.read_text()).get("anthropic_api_key", "")
    return ""


def save_api_key(key: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(json.dumps({"anthropic_api_key": key.strip()}))
    os.chmod(SECRETS, 0o600)


def api_key_hint() -> str:
    key = api_key()
    return f"...{key[-4:]}" if key else ""


def is_example(name: str) -> bool:
    return not (CONFIG_DIR / name).exists()


def path(name: str) -> Path:
    return CONFIG_DIR / name
