#!/usr/bin/env bash
# One command to set up (first time) and start the Application Pipeline.
#   ./start.sh                 set up if needed, start the app, open your browser
#   ./start.sh --port 9000     use another port
#   ./start.sh --no-browser    do not open a browser
# Works on macOS, Linux and Windows (WSL).
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$*" >&2; exit 1; }

# 1. Python 3.10+
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || die "Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/ and run ./start.sh again."

# 2. Virtual environment and packages (reinstalled only when requirements.txt changes)
if [ ! -x .venv/bin/python ]; then
  say "Creating a Python environment in .venv (first run only)"
  "$PY" -m venv .venv || die "Could not create .venv. On Debian/Ubuntu: sudo apt install python3-venv"
fi
REQ_HASH="$(cksum requirements.txt | cut -d' ' -f1)"
if [ "$(cat .venv/.requirements-hash 2>/dev/null || true)" != "$REQ_HASH" ]; then
  say "Installing Python packages"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  echo "$REQ_HASH" > .venv/.requirements-hash
fi

# 3. Chromium for PDF rendering and reading job ads
if ! .venv/bin/python - <<'EOF' 2>/dev/null
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    raise SystemExit(0 if Path(p.chromium.executable_path).exists() else 1)
EOF
then
  say "Downloading Chromium for PDF rendering (about 150 MB, first run only)"
  .venv/bin/python -m playwright install chromium || die "Chromium download failed. Try: .venv/bin/python -m playwright install --with-deps chromium"
fi

# 4. The web UI (prebuilt in web/dist; rebuilt only if missing and Node is available)
if [ ! -f web/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    say "Building the web UI"
    (cd web && npm install --no-audit --no-fund --silent && npm run build --silent)
  else
    die "web/dist is missing and Node.js is not installed. Install Node 18+ (https://nodejs.org) or download a release that includes web/dist."
  fi
fi

# 5. Claude
if command -v claude >/dev/null 2>&1; then
  say "Claude Code found: $(command -v claude)"
else
  warn "Claude Code is not installed. You can add a Claude API key in the app instead,"
  warn "or install Claude Code: npm install -g @anthropic-ai/claude-code  (then run: claude, to log in)"
fi

say "Starting the app (Ctrl+C to stop)"
exec .venv/bin/python -m server "$@"
