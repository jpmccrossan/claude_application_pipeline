"""Two ways to run Claude, behind one interface.

ClaudeCodeEngine  runs the Claude Code CLI headless (`claude -p`). Uses the user's Claude Code login
                  (subscription or API key). Restricted mode: no shell, file tools confined to the
                  working directory, only the tools each task names.
ApiEngine         calls the Claude API with the Anthropic Python SDK and runs the tool loop here.
                  Needs an API key (Settings page, or ANTHROPIC_API_KEY).

Both expose run(prompt, task=..., session=...) -> Result, and stream progress through on_event.
A session id lets a later call continue the same conversation (fix-up rounds and chat).

Tool sets ("task profiles"):
    "web"    web search and web fetch only, no files (research, scoring, onboarding)
    "none"   no tools
    "files"  read, edit and write files inside one folder, no web (chat reads scraped ads, so no way out)
A session must keep the same task for every turn: changing the tool list mid-conversation can
invalidate earlier thinking on the API.
"""
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from ..paths import CHATS, DATA

DEFAULT_API_MODEL = "claude-opus-5-5"


@dataclass
class Result:
    ok: bool
    text: str = ""
    session: str = ""
    error: str = ""
    cost_usd: float | None = None
    events: list = field(default_factory=list)


class Stopped(Exception):
    pass


def claude_cli() -> str:
    return shutil.which("claude") or ""


def choose_engine() -> str:
    """'claude-code', 'api' or '' (none available), honouring the user's setting."""
    wanted = config.settings().get("engine", "auto")
    if wanted == "claude-code":
        return "claude-code" if claude_cli() else ""
    if wanted == "api":
        return "api" if config.api_key() else ""
    if claude_cli():
        return "claude-code"
    return "api" if config.api_key() else ""


def get_engine():
    name = choose_engine()
    if name == "claude-code":
        return ClaudeCodeEngine()
    if name == "api":
        return ApiEngine()
    raise RuntimeError("No Claude engine available: install Claude Code (and log in), or add an API key in Settings.")


# ---------------------------------------------------------------- Claude Code CLI

class ClaudeCodeEngine:
    name = "claude-code"

    def run(self, prompt: str, *, task: str = "web", workdir: Path | None = None, session: str = "",
            system: str = "", on_event=None, should_stop=lambda: False, timeout_s: int = 1800) -> Result:
        workdir = Path(workdir or DATA)
        workdir.mkdir(parents=True, exist_ok=True)
        tools = {"web": "WebSearch,WebFetch", "none": "", "files": "Read,Write,Edit,Glob,Grep"}[task]
        cmd = [claude_cli(), "-p", "--output-format", "stream-json", "--verbose", "--restricted",
               "--strict-mcp-config", "--permission-mode", "dontAsk", "--tools", tools]
        if tools:
            allowed = tools.split(",")
            if task == "files":
                allowed = ["Read", "Glob", "Grep", "Write(**)", "Edit(**)"]
            cmd += ["--allowedTools", *allowed]
        if task == "files":
            cmd += ["--disallowedTools", "Read(config/**)", "Edit(config/**)", "Write(config/**)"]
        model = config.settings().get("model", "").strip()
        if model:
            cmd += ["--model", model]
        if system:
            cmd += ["--append-system-prompt", system]
        if session:
            cmd += ["--resume", session]
        env = os.environ.copy()
        proc = subprocess.Popen(cmd, cwd=workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
        proc.stdin.write(prompt)
        proc.stdin.close()
        stderr: list[str] = []
        threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True).start()
        result, session_id, started = None, session, time.monotonic()
        try:
            for line in proc.stdout:
                if should_stop():
                    proc.kill()
                    raise Stopped()
                if time.monotonic() - started > timeout_s:
                    proc.kill()
                    return Result(False, error="timed out", session=session_id)
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = msg.get("session_id") or session_id
                if msg.get("type") == "assistant" and on_event:
                    for block in msg["message"].get("content", []):
                        if block.get("type") == "tool_use":
                            on_event(describe_tool(block.get("name", ""), block.get("input") or {}))
                        elif block.get("type") == "text" and block.get("text", "").strip():
                            on_event({"kind": "text", "text": block["text"]})
                elif msg.get("type") == "result":
                    result = msg
        finally:
            proc.wait()
        if result is None:
            err = "".join(stderr).strip()[-600:] or f"claude exited with code {proc.returncode}"
            return Result(False, error=err, session=session_id)
        if result.get("is_error") or result.get("subtype") != "success":
            return Result(False, text=result.get("result", ""), error=result.get("result") or result.get("subtype", "error"),
                          session=session_id, cost_usd=result.get("total_cost_usd"))
        return Result(True, text=result.get("result", ""), session=session_id, cost_usd=result.get("total_cost_usd"))


def describe_tool(name: str, args: dict) -> dict:
    if name in ("WebSearch", "web_search"):
        return {"kind": "tool", "text": f"searching: {args.get('query', '')}"}
    if name in ("WebFetch", "web_fetch"):
        return {"kind": "tool", "text": f"reading {args.get('url', '')}"}
    if name in ("Read", "read_file"):
        return {"kind": "tool", "text": f"reading {args.get('file_path') or args.get('path', '')}"}
    if name in ("Write", "Edit", "write_file", "edit_file"):
        return {"kind": "tool", "text": f"editing {args.get('file_path') or args.get('path', '')}"}
    return {"kind": "tool", "text": name}


# ---------------------------------------------------------------- Claude API (Anthropic SDK)

FILE_TOOLS = [
    {
        "name": "list_files",
        "description": "List files and folders under a folder (relative path; '.' for the root). Returns one path per line.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
                         "additionalProperties": False},
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file (relative path). Returns its contents.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
                         "additionalProperties": False},
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file (relative path) with the full content given.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                         "required": ["path", "content"], "additionalProperties": False},
    },
    {
        "name": "edit_file",
        "description": "Replace one exact, unique occurrence of old_string with new_string in a text file (relative path).",
        "input_schema": {"type": "object",
                         "properties": {"path": {"type": "string"}, "old_string": {"type": "string"},
                                        "new_string": {"type": "string"}},
                         "required": ["path", "old_string", "new_string"], "additionalProperties": False},
    },
]
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 12},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 12},
]


class ApiEngine:
    name = "api"

    def __init__(self):
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=config.api_key() or None, max_retries=4)
        self.model = config.settings().get("model", "").strip() or DEFAULT_API_MODEL

    # Sessions are the message history, kept on disk so a later call (fix-up or chat) can continue.
    def _load(self, session: str) -> list:
        path = CHATS / "api_sessions" / f"{session}.json"
        return json.loads(path.read_text()) if session and path.exists() else []

    def _save(self, session: str, messages: list) -> None:
        folder = CHATS / "api_sessions"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{session}.json").write_text(json.dumps(messages))

    def run(self, prompt: str, *, task: str = "web", workdir: Path | None = None, session: str = "",
            system: str = "", on_event=None, should_stop=lambda: False, timeout_s: int = 1800) -> Result:
        session = session or uuid.uuid4().hex
        messages = self._load(session) + [{"role": "user", "content": prompt}]
        tools = {"web": WEB_TOOLS, "none": [], "files": FILE_TOOLS}[task]
        root = Path(workdir or DATA).resolve()
        started, cost, turns = time.monotonic(), 0.0, 0
        while True:
            if should_stop():
                raise Stopped()
            if time.monotonic() - started > timeout_s or turns > 60:
                return Result(False, error="timed out", session=session)
            turns += 1
            kwargs = dict(model=self.model, max_tokens=64000, messages=messages,
                          cache_control={"type": "ephemeral"}, output_config={"effort": "high"})
            if system:
                kwargs["system"] = system
            if tools:
                kwargs["tools"] = tools
            try:
                with self.client.messages.stream(**kwargs) as stream:
                    response = stream.get_final_message()
            except self.anthropic.AuthenticationError:
                return Result(False, error="The API key was rejected. Check it in Settings.", session=session)
            except self.anthropic.RateLimitError:
                return Result(False, error="Rate limited by the API. Try again in a minute.", session=session)
            except self.anthropic.APIStatusError as exc:
                return Result(False, error=f"API error {exc.status_code}: {exc.message}", session=session)
            except self.anthropic.APIConnectionError:
                return Result(False, error="Could not reach the Claude API. Check your connection.", session=session)
            cost += usage_cost(self.model, response.usage)
            content = [block.model_dump(exclude_none=True) for block in response.content]
            messages.append({"role": "assistant", "content": content})
            for block in response.content:
                if on_event and block.type == "server_tool_use":
                    on_event(describe_tool(block.name, block.input if isinstance(block.input, dict) else {}))
                elif on_event and block.type == "text" and block.text.strip():
                    on_event({"kind": "text", "text": block.text})
            if response.stop_reason == "refusal":
                self._save(session, messages)
                return Result(False, error="Claude declined this request.", session=session, cost_usd=cost)
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason == "tool_use":
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if on_event:
                        on_event(describe_tool(block.name, block.input))
                    output, is_error = run_file_tool(root, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": output,
                                    "is_error": is_error})
                messages.append({"role": "user", "content": results})
                continue
            self._save(session, messages)
            if response.stop_reason == "max_tokens":
                return Result(False, error="The reply was cut off (too long).", session=session, cost_usd=cost)
            text = "\n".join(b.text for b in response.content if b.type == "text")
            return Result(True, text=text, session=session, cost_usd=cost)


PRICES = {"opus": (4.0, 20.0), "sonnet": (2.0, 10.0), "haiku": (0.10, 0.50), "fable": (8.0, 40.0)}


def usage_cost(model: str, usage) -> float:
    tier = next((k for k in PRICES if k in model), "opus")
    p_in, p_out = PRICES[tier]
    tokens_in = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25 \
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
    return (tokens_in * p_in + (usage.output_tokens or 0) * p_out) / 1_000_000


BLOCKED_PARTS = {"config", ".git", ".venv", "api_sessions"}


def safe_path(root: Path, rel_path: str) -> Path:
    path = (root / rel_path).resolve()
    if path != root and root not in path.parents:
        raise PermissionError("path is outside the allowed folder")
    if BLOCKED_PARTS & set(path.relative_to(root).parts):
        raise PermissionError("that folder is not available")
    return path


def run_file_tool(root: Path, name: str, args: dict) -> tuple[str, bool]:
    try:
        path = safe_path(root, str(args.get("path", ".")))
        if name == "list_files":
            if not path.is_dir():
                return "not a folder", True
            items = sorted(p for p in path.rglob("*") if not (BLOCKED_PARTS & set(p.relative_to(root).parts)))
            return "\n".join(str(p.relative_to(root)) + ("/" if p.is_dir() else "") for p in items[:400]) or "(empty)", False
        if name == "read_file":
            return path.read_text()[:100_000], False
        if name == "write_file":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(args.get("content", "")))
            return f"wrote {path.relative_to(root)}", False
        if name == "edit_file":
            text = path.read_text()
            old, new = str(args.get("old_string", "")), str(args.get("new_string", ""))
            if text.count(old) != 1:
                return f"old_string must occur exactly once (found {text.count(old)})", True
            path.write_text(text.replace(old, new))
            return f"edited {path.relative_to(root)}", False
        return f"unknown tool {name}", True
    except (OSError, PermissionError, UnicodeDecodeError) as exc:
        return str(exc), True
