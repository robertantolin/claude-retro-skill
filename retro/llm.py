"""Shared `claude -p` wrapper for the retro scripts. Standard library only.

Calls run on the user's claude.ai login: the API key is removed from the subprocess
environment. Settings, plugins and MCP servers are not loaded, so each call carries
about 10k tokens of fixed context instead of about 70k.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_LOCK = threading.Lock()
_USAGE = {"calls": 0, "cost_usd": 0.0, "by_model": {}}
FLAGS = ["--no-session-persistence", "--tools", "", "--strict-mcp-config",
         "--setting-sources", "", "--output-format", "json"]


def claude_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def _env():
    return {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}


def call(model: str, prompt: str, timeout: int = 300) -> str:
    # shell=False with the executable resolved by hand: under shell=True a POSIX shell takes only
    # the first list item as the command and drops the flags. which() finds claude.cmd on Windows.
    cmd = [shutil.which("claude") or "claude", "-p", *FLAGS, "--model", model]
    # CREATE_NO_WINDOW (Windows only): the background scan owns no console, so without it every
    # claude.cmd call pops a visible console window for its ~7 s lifetime.
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=_env(), timeout=timeout, shell=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr.strip()[:300]}")
    data = json.loads(r.stdout)
    if data.get("is_error"):
        raise RuntimeError(f"claude error: {data.get('result', '')[:300]}")
    with _LOCK:
        _USAGE["calls"] += 1
        _USAGE["cost_usd"] += float(data.get("total_cost_usd") or 0.0)
        _USAGE["by_model"][model] = _USAGE["by_model"].get(model, 0) + 1
    return data.get("result", "")


def extract_json(text: str):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in reply")
    start = min(starts)
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON in reply")


def run_parallel(fn, items, workers: int = 2) -> list:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def usage_summary() -> str:
    per = " ".join(f"{m}={n}" for m, n in _USAGE["by_model"].items())
    return f"llm calls={_USAGE['calls']} nominal_cost=${_USAGE['cost_usd']:.2f} {per}".strip()


if __name__ == "__main__":
    print(call(sys.argv[1] if len(sys.argv) > 1 else "haiku", sys.stdin.read()))
