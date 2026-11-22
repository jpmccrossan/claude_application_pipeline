# Claude Application Pipeline

Local web app (FastAPI + React/TS) that turns a CV plus job ads into tailored one-page CVs and cover
letters, using Claude through either the Claude Code CLI (`claude -p`) or the Claude API. Public, PolyForm Noncommercial 1.0.0 (no commercial use).
README.md is the user guide; DISCLAIMER.md covers responsible scraping.

If you were started by the app itself to do one task, follow that task's prompt and ignore this file.

## Layout
- `applypipe/`: Python core. `pipeline.py` orchestrates (generate, scout, onboard, chat); `agent/engines.py`
  holds the two engines; `agent/tasks.py` builds prompts and parses tagged replies (including site setup); `render.py` + `check.py`
  render and validate; `scout.py` + `sites.py` collect listings; `profile.py`, `tracker.py`, `config.py`,
  `paths.py`, `jobfiles.py`, `runs.py` (background runs with logs the UI polls).
- `server/app.py`: JSON API under `/api`, serves `web/dist`. `python -m server` or `./start.sh`.
- `web/`: React + TS (Vite). `web/dist` is committed; rebuild with `cd web && npm run build` after UI changes.
- `prompts/`: what Claude is told. `templates/`: Jinja CV and letter, fonts, icons.
- `examples/`: fictional person (Sam Rivera) and default config, used until the user sets up their own.
- `data/` (git-ignored, or `$APPLYPIPE_DATA`): all personal data. Never commit it; never put personal data anywhere else.

## Rules
- Claude agents get the least privilege that works: research uses web tools only; scoring, onboarding and
  site setup get no tools. They return tagged text that Python validates and writes. Site setup must never fetch
  pages itself: Python reads the page (robots.txt, delay, user agent) and tests the settings before saving.
  Only chat edits files, inside `data/`, never `data/config/`. Keep it that way; no shell access for agents.
- Every claim in an application must trace to the user's `facts.md`. Do not weaken `check.py` to make output pass.
- One page or fail: the render's one-page check (FIT_JS) finds the footer by its inline `margin:auto` style.
- Scraping stays polite: robots.txt check, delay per host, honest user agent. Do not add sites whose terms
  forbid automated access as built-in adapters.
- Single process, bound to 127.0.0.1. No auth, so never bind to 0.0.0.0.
- No em dashes in prose the app writes. Keep the code plain; no new frameworks or databases.

## Checks before calling something done
- `.venv/bin/python -m applypipe.render --example` renders both documents `ok`.
- `cd web && npm run build` passes (it type-checks).
- For pipeline changes, run one real generation against a throwaway data folder:
  `APPLYPIPE_DATA=/tmp/ap-test ./start.sh --no-browser`.
