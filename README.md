# Claude Application Pipeline

Tailored job applications, written by Claude and checked against your real experience.

Upload your CV once. Then paste job ads, or let the app find them on the job sites you choose. For each
job you get a **one-page CV and a one-page cover letter** (PDF and HTML), researched and written around
what that company needs, using **only facts from your own CV**. Everything runs on your computer
through a simple local web app.

> **Please read [DISCLAIMER.md](DISCLAIMER.md) before using the job-site features.** Check each site's
> terms before you add it, keep volumes low, and review every application before you send it.

## What it does

- **Paste a job ad, get a CV and cover letter.** Claude researches the company (its problems, its words,
  the right person to address) and writes a letter about what *they* need, with your experience as the
  evidence.
- **Find jobs for you.** Searches the job sites you configure, drops anything irrelevant, too senior,
  too old or already seen, reads each remaining ad, scores it against your facts (strong, decent,
  stretch, skip) and writes applications for the best ones.
- **Edit by chatting.** Open any application and tell Claude what to change ("make paragraph 2
  shorter", "lead with my analytics work"). The PDFs update.
- **Never invents things.** Every claim must trace to your `facts.md`, built from your CV and edited by
  you. Automatic checks block claims about technologies you have not used, puffery ("passionate",
  "results-driven"), and gap admissions.
- **One page or fail.** Each document is measured in a real browser. If it overflows, Claude shortens it.
- **Tracks everything.** Status per application (ready, applied, interview, offer...) and a follow-up
  reminder 10 days after you apply.

## Quick start

You need **Python 3.10+** and **one** way to reach Claude:

- **Claude Code** (recommended if you have it): install it with `npm install -g @anthropic-ai/claude-code`
  and run `claude` once to log in. Uses your Claude subscription or your own key.
- **or a Claude API key** from [console.anthropic.com](https://console.anthropic.com). You paste it into
  the app during setup. *(Experimental: the API engine is newer and less tested than the Claude Code
  engine. Please report issues.)*

Then:

```bash
git clone https://github.com/jpmccrossan/claude_application_pipeline.git
cd claude_application_pipeline
./start.sh
```

That's it. The first run creates a Python environment, installs the packages, downloads Chromium (for
PDFs, about 150 MB), starts the app and opens **http://127.0.0.1:8765** in your browser. Setup then
walks you through:

1. **The disclaimer.**
2. **Connecting Claude** (Claude Code or an API key), with a connection test.
3. **Your CV** (PDF, Word or text) and an optional photo. Claude builds your profile in about a minute.
4. **Checking your facts** and a preview of your CV.
5. **Job preferences**: roles, locations, level, what to avoid.
6. **Job sites** to search, each with a Test button.

Next time, just run `./start.sh` again. Stop it with Ctrl+C.

Works on macOS, Linux and Windows through WSL. Options: `./start.sh --port 9000`, `./start.sh --no-browser`.

## Using it

| Page | What it is for |
|---|---|
| **Home** | Paste job ads into the inbox, press Generate. Follow-ups due and recent applications. |
| **Applications** | Every application with its status. Click one to see the letter, CV, research notes, how to apply, and a chat to edit it. |
| **Find jobs** | Run the scout and see every listing it considered, with its score and reason. |
| **Chat with Claude** | Change your facts, profile or writing style in plain words. |
| **Profile & facts** | Your source of truth (`facts.md`), writing preferences, CV layout, photo, CV preview. |
| **Job preferences** | What the scout searches for and how it filters and scores. |
| **Job sites** | Where the scout looks. Add, test, turn on and off. |
| **Settings** | Claude engine, model, speed, where your data lives. |

**Tip:** answer the `TODO` questions in your facts (numbers, outcomes, team sizes). They are ignored
until answered, and they make the letters much stronger.

**Applying:** applications start as **ready**. Read both PDFs, apply on the company's site, then set
the status to **applied** to start the follow-up clock.

## Job sites

On the Sites page, paste the address of any job site, anywhere in the world: ideally a page that lists
the jobs you want, such as a search results page. It is tested straight away:

- **Jobs found:** done. Job links are recognised automatically, and if the address contains one of your
  search terms, every search term is searched.
- **No jobs found:** press **Ask Claude to fix it**. The app reads the page (respecting robots.txt) and
  Claude works out the search address and which links are job ads. Its answer is tested before you can
  keep it.
- **Not allowed:** if the site's robots.txt forbids automated access, it is refused. Paste its ads by hand.

If a site you saved stops working later (sites change their layout), the scout asks Claude for new
settings once during the run, and saves them only if they find jobs.

| Type | Use for | How |
|---|---|---|
| **Greenhouse**, **Lever**, **Ashby** | Thousands of company careers pages | Public job APIs. Add company slugs, e.g. `example-co` for `boards.greenhouse.io/example-co`. The most reliable option. |
| **RSS / Atom feed** | Any board that offers a feed | Paste the feed URL. Use `{query}` and `{location}` to search each of your terms. |
| **Any job website** | Everything else | Paste the address. Optional settings (search address with `{query}` / `{location}`, a link pattern) are filled in by Claude when needed. |
| **Web search** | Anything else | Optional: Claude searches the web and the careers pages of companies you list. |

Every source is polite by default: robots.txt is checked before any page is fetched, requests to a site
are spaced out, and the tool identifies itself. Sites whose terms forbid automated access are deliberately
not built in: open the job, copy the page, and paste it on Home instead.

## How it works

```
CV ──► Claude builds profile.json (CV layout) + facts.md (source of truth) ──► you review
job ad ──► Claude researches + writes content.json ──► rule checks ──► HTML ──► PDF ──► one-page check
                     ▲                                       │ problems
                     └──────── same conversation, up to 3 fix rounds ◄─┘
```

- **Claude does the thinking; the app does everything mechanical.** Research and writing come back as
  structured text; the app validates it, writes the files, renders the PDFs, measures them, and sends
  any problems back to Claude to fix.
- **Least privilege.** Research agents only get web search and web fetch: no shell and no file access,
  so a malicious job ad cannot make them run anything. Site setup gets no tools at all: the app opens the
page itself (robots.txt respected), and tests Claude's suggested settings before using them. The chat agent can edit files in your `data/`
  folder only, has no web access, and cannot read `data/config/` (where an API key is kept). With Claude
  Code, agents run in `--restricted` mode with an explicit tool list.
- **Local only.** The server refuses requests whose Host or Origin is not this computer, so other
  websites you visit cannot drive it.
- **Two engines, one interface.** `claude -p` (Claude Code, headless) or the Claude API through the
  Anthropic Python SDK with a local tool loop (experimental).
- **Local and single-user.** The server binds to 127.0.0.1 only, has no login, and runs as one process.
  Never expose it to a network.

### Project layout

```
start.sh                 the one command
applypipe/               the Python core (usable without the UI)
  pipeline.py            generate, scout, onboarding, chat: orchestration and fix loops
  agent/engines.py       Claude Code CLI engine and Claude API engine
  agent/tasks.py         prompts in, tagged replies out
  render.py, check.py    HTML/PDF rendering, one-page guard, rule checks
  scout.py, sites.py     listing collection, filtering, fetching, site adapters
  profile.py, tracker.py profile and facts, application tracker
server/app.py            FastAPI: JSON API + the built UI
web/                     React + TypeScript UI (prebuilt in web/dist)
prompts/                 what Claude is told: brief, style, scoring, onboarding, chat
templates/               CV and letter layouts (Jinja), fonts, icons
examples/                a fictional person and default settings, used until you set up your own
data/                    YOUR data, git-ignored: profile, CV, settings, applications, tracker
```

### Your data

Everything personal lives in `data/` (git-ignored): your profile, CV, photo, settings, API key,
applications and tracker. Set `APPLYPIPE_DATA=/some/folder` to keep it elsewhere. Job ads, your facts and
your writing preferences are sent to Claude when generating. Back up `data/` if your history matters.

### Customising

- **Writing style for everyone:** `prompts/style.md`. **For you only:** Profile → Writing style.
- **What Claude is told:** the files in `prompts/`.
- **Layout and design:** `templates/cv.html` and `templates/letter.html` (Jinja). Keep the footer's
  `margin:auto` style, which the one-page check uses to find it. The accent colour is `accent` in
  `profile.json`.
- **Rule checks:** `BANNED` and `TECH` in `applypipe/check.py`, or `banned_phrases` in `profile.json`.

## Development

```bash
./start.sh --no-browser                        # API + built UI on :8765
cd web && npm install && npm run dev           # UI with hot reload on :5173 (proxies /api to :8765)
.venv/bin/python -m applypipe.render --example # render the example person as a self-test
```

API docs while running: http://127.0.0.1:8765/api/docs. After UI changes, run `npm run build` in `web/`
and commit `web/dist` so users do not need Node.

## Troubleshooting

| Problem | Fix |
|---|---|
| "No Claude engine available" | Install Claude Code and run `claude` once to log in, or add an API key in Settings. Then press Test connection. |
| A site's Test finds nothing | Check the slug or address in a browser. For a website, press **Ask Claude to fix it**. Some sites block automated access: paste their ads instead. |
| "does not fit on one page" after 3 fixes | Open the application and ask the chat to shorten it, or trim long default bullets in your profile. |
| Chromium errors | `.venv/bin/python -m playwright install --with-deps chromium` |
| Port in use | `./start.sh --port 9000` |

## Licence

[PolyForm Noncommercial 1.0.0](LICENSE): free to use, change and share for any non-commercial purpose
(personal job hunting, study, research, charities, schools). Commercial use is not allowed.
Provided as is, with no warranty. See [DISCLAIMER.md](DISCLAIMER.md) for responsible use.
Bundled fonts and icons keep their own licences: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
