#!/usr/bin/env python3
"""pxForge — turn a codebase into an AI-ready context prompt."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import random
import re
import stat
import subprocess
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from textual.app import App, ComposeResult, Screen
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
    Switch,
    TextArea,
)

CONFIG_DIR = Path.home() / ".pxforge"
CONFIG_FILE = CONFIG_DIR / "config.json"
BIN_DIR = Path.home() / ".local" / "bin"
SCRIPT_PATH = Path(__file__).resolve()

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_PROVIDER = "Ollama (Local)"

_CPU = os.cpu_count() or 4
IO_WORKERS = min(64, max(16, _CPU * 8))
READ_BATCH = 96
IO_EXECUTOR = ThreadPoolExecutor(max_workers=IO_WORKERS, thread_name_prefix="pxforge-io")

AI_BROWSER_SERVICES = {
    "Claude": "https://claude.ai",
    "ChatGPT": "https://chatgpt.com",
    "Gemini": "https://gemini.google.com",
    "Grok": "https://grok.com",
    "Perplexity": "https://perplexity.ai",
    "Mistral": "https://chat.mistral.ai",
    "DeepSeek": "https://chat.deepseek.com",
}
AI_SERVICE_KEYS = list(AI_BROWSER_SERVICES.keys())

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env",
    "node_modules", "bower_components", "vendor",
    "dist", "build", "out", "target", "__pycache__",
    ".next", ".nuxt", ".svelte-kit", ".output", ".vercel", ".netlify",
    ".cache", ".turbo", ".parcel-cache", ".yarn",
    "coverage", "htmlcov", ".nyc_output", ".hypothesis",
    ".idea", ".vscode", ".vs",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox",
    "egg-info", ".eggs", "site-packages", "__pypackages__",
    ".terraform", ".serverless", ".gradle", ".dart_tool",
    "Pods", "DerivedData", ".dSYM",
}
IGNORED_EXT = {
    ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".whl",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".bin", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico",
    ".pdf", ".mp3", ".mp4", ".mov", ".avi", ".lock", ".bmp", ".webp",
    ".tiff", ".heic", ".psd", ".wav", ".ogg", ".flac",
    ".ttf", ".woff", ".woff2", ".eot",
    ".class", ".o", ".a", ".lib", ".pdb", ".map",
    ".suo", ".user", ".orig", ".rej",
}
IGNORED_FILES = {
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "go.sum",
    "yarn.lock", "Cargo.lock", "poetry.lock", "composer.lock",
}
BINARY_MARKERS = (
    b"\x7fELF", b"\x89PNG", b"\xff\xd8\xff",
    b"%PDF-1.", b"PK\x03\x04", b"GIF8",
)
CHUNK_SIZE_FAST = 8000
CHUNK_SIZE_HQ = 6000
MIN_CONTENT_LEN = 20
MAX_FILE_SIZE_BYTES = 500_000
MAX_FAST_LOCAL_CHARS = 12_000
NO_MODEL_SENTINELS = frozenset({
    "(no models found)",
    "(no models — refresh below)",
})

PROVIDER_KEYS = {
    "OpenAI": "openai_key",
    "Anthropic (Claude)": "anthropic_key",
    "Groq": "groq_key",
    "OpenRouter": "openrouter_key",
    OLLAMA_PROVIDER: "",
}
PROVIDER_ENV = {
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic (Claude)": "ANTHROPIC_API_KEY",
    "Groq": "GROQ_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
    OLLAMA_PROVIDER: "",
}
PROVIDER_MODELS: Dict[str, List[str]] = {
    "OpenAI": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
    "Anthropic (Claude)": [
        "claude-sonnet-5",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-haiku-4-5-20251001",
    ],
    "Groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "mixtral-8x7b-32768",
    ],
    "OpenRouter": [
        "anthropic/claude-sonnet-4-5",
        "meta-llama/llama-3.3-70b-instruct",
        "openai/gpt-4o",
        "google/gemini-2.0-flash-001",
        "deepseek/deepseek-r1",
    ],
    OLLAMA_PROVIDER: [],
}
PROVIDER_NAMES: List[str] = list(PROVIDER_MODELS.keys())
PROVIDER_CONCURRENCY = {
    "OpenAI": 8,
    "Anthropic (Claude)": 5,
    "Groq": 3,
    "OpenRouter": 5,
    OLLAMA_PROVIDER: 2,
}
PROVIDER_CONCURRENCY_FAST = {
    "OpenAI": 12,
    "Anthropic (Claude)": 8,
    "Groq": 5,
    "OpenRouter": 8,
    OLLAMA_PROVIDER: 3,
}

_RE_SYMBOL = re.compile(
    r"^(?:export\s+)?(?:async\s+)?"
    r"(?:def|class|function|fn|func|type|interface|struct|enum|trait|impl|"
    r"pub\s+(?:fn|struct|enum|trait|type)|"
    r"const|let|var)\s+([A-Za-z_][\w]*)",
    re.MULTILINE,
)
_RE_IMPORT = re.compile(
    r"^(?:import\s.+|from\s+\S+\s+import\s.+|require\(['\"][^'\"]+['\"]\)|"
    r"#include\s*[<\"].+|use\s+[\w:]+|package\s+[\w.]+)",
    re.MULTILINE,
)


def detect_shell() -> Tuple[str, Path]:
    shell = os.environ.get("SHELL", "")
    name = Path(shell).name if shell else ""
    rc_map = {
        "zsh": Path.home() / ".zshrc",
        "bash": Path.home() / ".bashrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
        "ksh": Path.home() / ".kshrc",
    }
    return name, rc_map.get(name, Path.home() / ".bashrc")


def install_to_path() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = BIN_DIR / "pxforge"
    wrapper.write_text(
        f"#!/usr/bin/env sh\nexec {sys.executable} {SCRIPT_PATH} \"$@\"\n"
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    shell_name, rc_file = detect_shell()
    bin_str = str(BIN_DIR)
    rc_file.parent.mkdir(parents=True, exist_ok=True)
    existing = rc_file.read_text() if rc_file.exists() else ""
    if bin_str not in existing:
        line = (
            f"fish_add_path {bin_str}"
            if shell_name == "fish"
            else f'export PATH="{bin_str}:$PATH"'
        )
        with open(rc_file, "a", encoding="utf-8") as f:
            f.write(f"\n# pxforge\n{line}\n")
    print(f"Installed: {wrapper}")
    print(f"PATH entry added to: {rc_file}")
    print(f"\nRestart your shell or run:  source {rc_file}")
    print("Then use:  pxforge            # scans current directory")
    print("           pxforge /some/path # scans given path")


async def fetch_ollama_models() -> Tuple[List[str], str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", []) if m.get("name")]
            if not models:
                return [], "connected — no models downloaded"
            return models, f"connected — {len(models)} model(s) found"
    except httpx.ConnectError:
        return [], "offline — is Ollama running? (ollama serve)"
    except httpx.TimeoutException:
        return [], "timeout — Ollama not responding"
    except Exception as e:
        return [], f"error — {e}"


class GitignoreParser:
    __slots__ = ("prefix", "rules")

    def __init__(self, dir_path: str):
        self.prefix = dir_path + os.sep
        self.rules: List[Tuple[str, bool]] = []
        gi = os.path.join(dir_path, ".gitignore")
        try:
            with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("!"):
                        self.rules.append((line[1:].rstrip("/"), True))
                    else:
                        self.rules.append((line.rstrip("/"), False))
        except (FileNotFoundError, PermissionError, IsADirectoryError):
            pass

    @staticmethod
    def _match(rel_str: str, rel_dir: str, pat: str, parts: List[str]) -> bool:
        if pat.startswith("/"):
            p = pat[1:]
            return fnmatch.fnmatch(rel_str, p) or fnmatch.fnmatch(rel_dir, p + "/")
        if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(rel_dir, pat + "/"):
            return True
        for i in range(len(parts)):
            sub = "/".join(parts[i:])
            if fnmatch.fnmatch(sub, pat) or fnmatch.fnmatch(sub + "/", pat + "/"):
                return True
        return False


def path_is_ignored(path: str, chain: Tuple[GitignoreParser, ...]) -> bool:
    ignored = False
    for gi in chain:
        if not gi.rules or not path.startswith(gi.prefix):
            continue
        rel_str = path[len(gi.prefix):].replace(os.sep, "/")
        rel_dir = rel_str + "/"
        parts = rel_str.split("/")
        for pat, is_negation in gi.rules:
            if GitignoreParser._match(rel_str, rel_dir, pat, parts):
                ignored = not is_negation
    return ignored


APP_CSS = """
Screen {
    background: #1a1814;
}
Header {
    background: #2a241c;
    color: #f0e6d3;
    text-style: bold;
}
Footer {
    background: #141210;
    color: #a89880;
}

.hidden {
    display: none !important;
}

#dir_select_container {
    width: 100%;
    height: 100%;
    padding: 1 2;
}
#dir_label {
    height: 1;
    margin-bottom: 1;
    text-style: bold;
    color: #e8a045;
}
#dir_path_row {
    height: 3;
    margin-bottom: 1;
}
#dir_path_input {
    width: 1fr;
}
#dir_tree {
    height: 1fr;
    border: round #5c4a32;
    background: #12100e;
    margin-bottom: 1;
}
#dir_selected_label {
    height: 1;
    color: #8a7a68;
    margin-bottom: 1;
    padding: 0 1;
}
#dir_buttons {
    height: 3;
    align: right middle;
}

#settings_scroll {
    width: 100%;
    height: 100%;
}
#settings_inner {
    width: 100%;
    height: auto;
    padding: 1 2;
}
#lbl_path {
    height: auto;
    color: #e8a045;
    text-style: bold;
    margin-bottom: 1;
    padding: 0 1;
    border-left: thick #e8a045;
}
#settings_inner Label {
    height: 1;
    margin-top: 1;
    color: #a89880;
    text-style: bold;
}
#mode_row {
    height: 3;
    align: left middle;
    margin-top: 1;
    margin-bottom: 1;
}
#mode_row Label {
    margin: 0 1;
    color: #f0e6d3;
}
#mode_hint {
    height: auto;
    color: #6e6256;
    margin-bottom: 1;
    padding: 0 1;
}
#share_privacy_row {
    height: 3;
    align: left middle;
    margin-top: 1;
    margin-bottom: 0;
}
#share_privacy_row Label {
    margin: 0 1;
    color: #f0e6d3;
}
#share_hint {
    height: auto;
    color: #6e6256;
    margin-bottom: 1;
    padding: 0 1;
}
#ollama_status_row {
    height: 2;
    align: left middle;
    margin-top: 1;
    padding: 0 1;
}
#ollama_status_label {
    height: 2;
    width: 1fr;
    color: #8a7a68;
    text-style: italic;
}
#btn_ollama_refresh {
    height: 2;
    min-width: 12;
}
#settings_buttons {
    height: 3;
    align: right middle;
    margin-top: 2;
}

#progress_container {
    width: 100%;
    height: 100%;
    padding: 1 2;
}
#progress_label {
    height: 1;
    text-style: bold;
    color: #e8a045;
    margin-bottom: 1;
}
#progress_meta {
    height: 1;
    color: #8a7a68;
    margin-bottom: 1;
}
#prog_bar {
    margin-bottom: 1;
}
#scan_log {
    height: 1fr;
    border: round #5c4a32;
    background: #12100e;
    padding: 0 1;
}
#progress_buttons {
    height: 3;
    align: right middle;
    margin-top: 1;
}

#output_section {
    width: 100%;
    height: 100%;
}
#stats_bar {
    height: 1;
    color: #8a7a68;
    padding: 0 2;
}
#token_label {
    height: 1;
    color: #d4a017;
    padding: 0 2;
    text-style: italic;
    margin-bottom: 1;
}
#scroll_area {
    height: 1fr;
    border: round #5c4a32;
    background: #12100e;
    margin: 0 2;
}
#output_text {
    height: 100%;
}
#bottom_panel {
    height: auto;
    width: 100%;
    border-top: solid #3a3024;
    padding: 1 0 0 0;
}
#ai_open_row {
    height: 3;
    align: left middle;
    padding: 0 2;
    width: 100%;
    overflow-x: auto;
    scrollbar-size: 0 0;
}
#ai_open_label {
    height: 3;
    color: #8a7a68;
    text-style: bold;
    width: auto;
    content-align: left middle;
    padding: 0 1 0 0;
}
.ai_btn {
    margin: 0 1 0 0;
    min-width: 11;
    height: 3;
}
#output_buttons {
    height: 3;
    align: right middle;
    padding: 0 2;
    margin-top: 1;
}
#share_row {
    height: 3;
    align: left middle;
    padding: 0 2;
    margin-top: 1;
}
#share_status {
    height: 1;
    color: #8a7a68;
    padding: 0 2;
    margin-top: 0;
}
Button {
    margin-left: 1;
}
"""


def load_config() -> Dict[str, Any]:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def save_config(config: Dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def resolve_api_key(provider: str, typed: str = "") -> str:
    typed = (typed or "").strip()
    if typed:
        return typed
    config_key = PROVIDER_KEYS.get(provider, "")
    env_key = PROVIDER_ENV.get(provider, "")
    config = load_config()
    if config_key:
        saved = (config.get(config_key) or "").strip()
        if saved:
            return saved
    if env_key:
        return (os.getenv(env_key) or "").strip()
    return ""


def resolve_github_token(typed: str = "") -> str:
    """GitHub token for private team gists: typed → config → env → gh CLI."""
    typed = (typed or "").strip()
    if typed:
        return typed
    config = load_config()
    saved = (config.get("github_token") or "").strip()
    if saved:
        return saved
    for env_name in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = (os.getenv(env_name) or "").strip()
        if val:
            return val
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            token = (result.stdout or "").strip()
            if token:
                return token
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


async def create_team_share_gist(
    content: str,
    *,
    project_name: str,
    token: str,
    private: bool = True,
) -> str:
    """Upload context markdown as a GitHub Gist. Returns the html_url."""
    if not content.strip():
        raise ValueError("Nothing to share — output is empty.")
    if not token:
        raise ValueError(
            "GitHub token required. Set GITHUB_TOKEN, run `gh auth login`, "
            "or paste a token in Settings."
        )

    safe_name = re.sub(r"[^\w.\-]+", "_", project_name.strip()) or "project"
    filename = f"pxforge_{safe_name}.md"
    description = f"pxForge team context — {project_name}"
    payload = {
        "description": description[:200],
        "public": not private,
        "files": {filename: {"content": content}},
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pxForge",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.github.com/gists",
            headers=headers,
            json=payload,
        )
        if resp.status_code == 401:
            raise RuntimeError(
                "GitHub rejected the token (401). Check GITHUB_TOKEN / gh auth."
            )
        if resp.status_code == 403:
            raise RuntimeError(
                "GitHub forbidden (403). Token needs the 'gist' scope."
            )
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("message", "")
            except Exception:
                detail = resp.text[:200]
            raise RuntimeError(
                f"Gist create failed ({resp.status_code}): {detail or resp.reason_phrase}"
            )
        data = resp.json()
        url = data.get("html_url") or ""
        if not url:
            raise RuntimeError("Gist created but no URL returned.")
        return url


def copy_to_clipboard(content: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["pbcopy"], input=content, text=True, check=True, timeout=5
            )
            return True
        if sys.platform == "win32":
            subprocess.run(
                ["clip"], input=content, text=True, shell=True, check=True, timeout=5
            )
            return True
        for cmd in (
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            try:
                subprocess.run(cmd, input=content, text=True, check=True, timeout=5)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        return False
    except Exception:
        return False


def local_summarize(filepath: str, content: str) -> str:
    """Heuristic per-file summary used in fast mode (no LLM round-trip)."""
    name = os.path.basename(filepath)
    sample = content if len(content) <= MAX_FAST_LOCAL_CHARS else content[:MAX_FAST_LOCAL_CHARS]
    lines = sample.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    symbols = list(dict.fromkeys(_RE_SYMBOL.findall(sample)))[:24]
    imports = [m.group(0).strip() for m in _RE_IMPORT.finditer(sample)][:12]

    purpose = f"Source file `{name}` ({len(lines)} lines)."
    for ln in non_empty[:8]:
        s = ln.strip()
        if s.startswith(('"""', "'''", "//!", "///", "/*", "*", "#")) and len(s) > 4:
            purpose = s.strip('#"\'/ *')[:160]
            break

    parts = [f"Purpose: {purpose}"]
    if symbols:
        parts.append("Key symbols: " + ", ".join(symbols))
    if imports:
        parts.append("Dependencies:\n- " + "\n- ".join(imports))
    else:
        parts.append("Dependencies: none detected at top level")
    parts.append(
        "Logic: local scan (fast mode) — symbols and imports extracted without LLM."
    )
    return "\n".join(parts)


SYSTEM_ANALYST = """You are a senior code analyst producing a structured summary of one file for another AI's context window. Output exactly these sections, in this order, omitting any section with nothing to report:

Purpose: one to two sentences — what this file does and why it exists.
Key symbols: functions, classes, exported constants that matter to callers. Name plus one-line role each. Skip trivial getters/setters and obvious boilerplate.
Dependencies: imports and what they're used for; internal modules this file couples to.
Logic: non-obvious algorithms, invariants, side effects, error handling, or architectural decisions a new contributor would miss by skimming.

Rules:
- Bullets only, no prose paragraphs.
- Never restate code verbatim or narrate what's visible on the screen.
- Never pad with generic filler ("this file contains code", "imports bring in dependencies").
- For config/data files: state what they configure, which values are load-bearing, and what breaks if they're wrong.
- If the file is trivial (barrel export, empty __init__, generated file), say so in one line and stop.
"""

SYSTEM_ARCHITECT = """You are a senior software architect writing the orientation a new engineer gets on day one. Using the directory tree and per-file analyses, write a PROJECT SUMMARY with these sections:

Stack: languages, frameworks, and libraries that actually shape design decisions. Skip incidental dependencies.
Architecture: the pattern in use, how major components communicate, where state lives.
Entry points & data flow: where execution starts, how input travels through the system.
Watch out for: non-obvious coupling, implicit conventions, or footguns visible in the analyses — omit entirely if nothing qualifies.

Rules:
- Direct technical prose, 3-5 short paragraphs, no per-file recap.
- State what's actually true of this codebase — never generic architecture commentary.
- If the analyses don't support a claim, say so instead of guessing.
"""

SYSTEM_PROMPT_ENGINEER = """You are an expert prompt engineer producing a system prompt that another AI coding assistant will load before touching this codebase. Write it in second person, addressed to that assistant, structured exactly as:

1. Role — one or two sentences establishing it as an expert collaborator on this specific codebase.
2. Project — what this project is, its stack, its architecture, in 2-3 sentences pulled from the analyses, not boilerplate.
3. Conventions — naming, structure, and idioms actually observed in the analyses. Name the pattern and where it shows up.
4. Always — concrete, checkable behaviors: reuse existing utilities instead of duplicating them, match observed patterns, follow the established file layout for new files.
5. Never — concrete failure modes: don't add a dependency without checking one isn't already used for that purpose, don't break an existing interface, don't duplicate a utility that already exists.
6. Layout — the directory tree, so the assistant knows where things live without exploring first.

Rules:
- Every instruction must be specific enough to verify against this codebase. No advice that would apply to any project.
- If the analyses don't support a section with something specific, keep that section short — never invent detail.
- Output the prompt itself only. No preamble, no "Here is a system prompt", no meta-commentary, nothing before section 1 or after section 6.
- Under 600 words.
"""


class LLMClient:
    URLS = {
        "OpenAI": "https://api.openai.com/v1/chat/completions",
        "Anthropic (Claude)": "https://api.anthropic.com/v1/messages",
        "Groq": "https://api.groq.com/openai/v1/chat/completions",
        "OpenRouter": "https://openrouter.ai/api/v1/chat/completions",
        OLLAMA_PROVIDER: f"{OLLAMA_BASE_URL}/v1/chat/completions",
    }
    MAX_RETRIES = 5

    def __init__(self, provider: str, api_key: str, model: str, mode: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.mode = mode
        self.max_tokens = 4096 if mode == "high_quality" else 2048
        timeout = 300.0 if provider == OLLAMA_PROVIDER else 180.0
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> Dict[str, str]:
        base = {"Content-Type": "application/json"}
        if self.provider == "Anthropic (Claude)":
            return {
                **base,
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
        if self.provider == OLLAMA_PROVIDER:
            return {**base, "Authorization": "Bearer ollama"}
        if self.provider == "OpenRouter":
            return {
                **base,
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/byte4day/PxForge",
                "X-Title": "pxForge",
            }
        return {**base, "Authorization": f"Bearer {self.api_key}"}

    def _payload(self, prompt: str, system: str) -> Dict[str, Any]:
        if self.provider == "Anthropic (Claude)":
            return {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }

    def _extract(self, data: Dict[str, Any]) -> str:
        if self.provider == "Anthropic (Claude)":
            blocks = data.get("content", [])
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            return "\n".join(t for t in texts if t)
        choices = data.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""

    async def generate(self, prompt: str, system: str = SYSTEM_ANALYST) -> str:
        url = self.URLS.get(self.provider)
        if not url:
            raise ValueError(f"Unknown provider: {self.provider}")
        last_exc: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = await self._http.post(
                    url, headers=self._headers(), json=self._payload(prompt, system)
                )
                if resp.status_code == 429:
                    wait = min((2 ** attempt) + random.uniform(0, 1), 30.0)
                    await asyncio.sleep(wait)
                    last_exc = Exception("Rate limited (429)")
                    continue
                if resp.status_code in (500, 502, 503):
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                resp.raise_for_status()
                result = self._extract(resp.json())
                if not result:
                    raise ValueError("Empty response from API")
                return result
            except httpx.TimeoutException as exc:
                last_exc = exc
                if self.provider == OLLAMA_PROVIDER:
                    raise RuntimeError(
                        f"Ollama timeout for model '{self.model}'. "
                        "Large models may need more time — try a smaller model."
                    ) from exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except httpx.ConnectError as exc:
                if self.provider == OLLAMA_PROVIDER:
                    raise RuntimeError(
                        "Cannot connect to Ollama. Make sure it is running: ollama serve"
                    ) from exc
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(1)
        raise last_exc or RuntimeError("Max retries exceeded")


def _read_file_sync(filepath: str) -> Optional[Dict[str, Any]]:
    ext = os.path.splitext(filepath)[1].lower()
    try:
        with open(filepath, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            if size > MAX_FILE_SIZE_BYTES:
                return {
                    "path": filepath,
                    "type": ext,
                    "is_binary": False,
                    "content": None,
                    "skipped": True,
                    "reason": f"too large ({size // 1024}KB)",
                }
            header = f.read(8192)
            if any(header.startswith(m) for m in BINARY_MARKERS) or b"\x00" in header:
                return {
                    "path": filepath,
                    "type": ext,
                    "is_binary": True,
                    "content": None,
                    "skipped": False,
                }
            raw = header if size <= 8192 else header + f.read()
        content = raw.decode("utf-8", errors="ignore")
        return {
            "path": filepath,
            "type": ext,
            "is_binary": False,
            "content": content,
            "skipped": False,
        }
    except PermissionError:
        return {
            "path": filepath,
            "type": ext,
            "is_binary": False,
            "content": None,
            "skipped": True,
            "reason": "permission denied",
        }
    except Exception:
        return None


class ProjectScanner:
    async def scan(
        self,
        path: str,
        log: RichLog,
        on_read_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        loop = asyncio.get_running_loop()
        log.write("[bold #e8a045]Walking directory tree...[/]")
        tree, file_paths = await loop.run_in_executor(
            IO_EXECUTOR, self._build_tree, path
        )
        log.write(f"[bold #e8a045]Reading {len(file_paths)} files...[/]")
        files = await self._read_files(file_paths, loop, on_read_progress)
        return tree, files

    def _build_tree(self, path: str) -> Tuple[str, List[str]]:
        base = str(Path(path).resolve())
        tree_lines: List[str] = [Path(base).name + "/"]
        file_paths: List[str] = []

        def walk(
            dirpath: str, prefix: str, gitignores: Tuple[GitignoreParser, ...]
        ) -> None:
            try:
                raw_entries = list(os.scandir(dirpath))
            except (PermissionError, OSError):
                return

            local_gi = GitignoreParser(dirpath)
            active = gitignores + (local_gi,) if local_gi.rules else gitignores

            filtered: List[Tuple[os.DirEntry, bool]] = []
            for entry in raw_entries:
                name = entry.name
                if name == ".gitignore":
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    is_file = entry.is_file(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    if name in IGNORED_DIRS:
                        continue
                    if active and path_is_ignored(entry.path, active):
                        continue
                    filtered.append((entry, True))
                elif is_file:
                    if name in IGNORED_FILES:
                        continue
                    if os.path.splitext(name)[1].lower() in IGNORED_EXT:
                        continue
                    if active and path_is_ignored(entry.path, active):
                        continue
                    filtered.append((entry, False))

            filtered.sort(key=lambda t: (not t[1], t[0].name.lower()))

            for i, (entry, is_dir) in enumerate(filtered):
                is_last = i == len(filtered) - 1
                connector = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{connector}{entry.name}")
                if is_dir:
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    walk(entry.path, child_prefix, active)
                else:
                    file_paths.append(entry.path)

        walk(base, "", ())
        return "\n".join(tree_lines), file_paths

    async def _read_files(
        self,
        file_paths: List[str],
        loop: asyncio.AbstractEventLoop,
        on_read_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        if not file_paths:
            return []

        total = len(file_paths)
        results: List[Dict[str, Any]] = []
        # Batch submissions so we don't spawn tens of thousands of coroutines.
        for start in range(0, total, READ_BATCH):
            batch = file_paths[start : start + READ_BATCH]
            # Fan out within the batch across the shared thread pool.
            partial = await asyncio.gather(
                *[
                    loop.run_in_executor(IO_EXECUTOR, _read_file_sync, fp)
                    for fp in batch
                ]
            )
            results.extend(r for r in partial if r is not None)
            done = min(start + len(batch), total)
            if on_read_progress:
                on_read_progress(done, total)
        return results


class FileAnalyzer:
    def __init__(self, client: LLMClient, log: RichLog, mode: str):
        self.client = client
        self.log = log
        self.mode = mode
        table = (
            PROVIDER_CONCURRENCY_FAST
            if mode == "fast"
            else PROVIDER_CONCURRENCY
        )
        self._sem = asyncio.Semaphore(table.get(client.provider, 5))
        self._chunk_size = CHUNK_SIZE_FAST if mode == "fast" else CHUNK_SIZE_HQ

    async def analyze(
        self,
        files: List[Dict[str, Any]],
        on_progress: Callable[[int, int], None],
    ) -> Dict[str, str]:
        total = len(files)
        results: Dict[str, str] = {}
        done_count = 0
        lock = asyncio.Lock()

        async def mark_done() -> None:
            nonlocal done_count
            async with lock:
                done_count += 1
                current = done_count
            on_progress(current, total)

        async def process(f: Dict[str, Any]) -> None:
            name = os.path.basename(f["path"])
            content = f.get("content") or ""

            if f.get("skipped"):
                reason = f.get("reason", "skipped")
                results[f["path"]] = f"[SKIPPED:{reason}]"
                await mark_done()
                return

            if f["is_binary"] or len(content.strip()) < MIN_CONTENT_LEN:
                label = "BINARY" if f["is_binary"] else "SKIPPED:empty"
                results[f["path"]] = f"[{label}]"
                await mark_done()
                return

            # Fast mode: local heuristics only — no per-file LLM calls.
            if self.mode == "fast":
                results[f["path"]] = local_summarize(f["path"], content)
                await mark_done()
                return

            chunks = [
                content[i : i + self._chunk_size]
                for i in range(0, len(content), self._chunk_size)
            ]

            async def analyze_chunk(ci: int, chunk: str) -> str:
                chunk_note = (
                    f" (chunk {ci + 1}/{len(chunks)} — partial content, not the whole file)"
                    if len(chunks) > 1
                    else ""
                )
                prompt = f"File: {name}{chunk_note}\nContent:\n{chunk}"
                async with self._sem:
                    self.log.write(
                        f"  [[bold]{done_count + 1}/{total}[/bold]] {name}"
                        + (f" — chunk {ci + 1}/{len(chunks)}" if len(chunks) > 1 else "")
                    )
                    try:
                        return await self.client.generate(prompt, system=SYSTEM_ANALYST)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        self.log.write(f"  [red][!] {name}: {e}[/red]")
                        return ""

            summaries = [
                s
                for s in await asyncio.gather(
                    *[analyze_chunk(ci, chunk) for ci, chunk in enumerate(chunks)]
                )
                if s.strip()
            ]

            if not summaries:
                results[f["path"]] = "[FAILED]"
            elif len(summaries) == 1:
                results[f["path"]] = summaries[0]
            else:
                self.log.write(
                    f"  [yellow]Merging {len(summaries)} chunks for {name}[/yellow]"
                )
                merge_prompt = (
                    f"Merge these partial analyses of '{name}' into one coherent summary.\n"
                    "Preserve: Purpose, Key functions/classes, Dependencies, Important logic.\n\n"
                    + "\n---\n".join(summaries)
                )
                async with self._sem:
                    try:
                        merged = await self.client.generate(
                            merge_prompt, system=SYSTEM_ANALYST
                        )
                        results[f["path"]] = merged if merged else "\n".join(summaries)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        results[f["path"]] = "\n".join(summaries)

            await mark_done()

        await asyncio.gather(*[process(f) for f in files])
        return results


class PromptBuilder:
    MAX_CTX_CHARS = 100_000

    async def build(
        self,
        tree: str,
        file_summaries: Dict[str, str],
        client: LLMClient,
        log: RichLog,
        base_path: str = "",
    ) -> str:
        log.write("[bold #e8a045]Generating project summary...[/]")

        def rel(p: str) -> str:
            try:
                return os.path.relpath(p, base_path) if base_path else os.path.basename(p)
            except ValueError:
                return os.path.basename(p)

        valid_summaries = {
            p: s for p, s in file_summaries.items() if not s.startswith("[")
        }
        skipped_summaries = {
            p: s for p, s in file_summaries.items() if s.startswith("[")
        }

        ctx_lines = [f"{rel(p)}: {s}" for p, s in valid_summaries.items()]
        ctx = "\n".join(ctx_lines)
        if len(ctx) > self.MAX_CTX_CHARS:
            ctx = ctx[: self.MAX_CTX_CHARS] + "\n...[truncated for context window]"

        tree_for_summary = (
            tree if len(tree) <= 10_000 else tree[:10_000] + "\n...[tree truncated]"
        )

        project_summary = await client.generate(
            "Analyze the project structure and file summaries below. "
            "Write a concise PROJECT SUMMARY covering: technology stack, architecture, "
            "core functionality, and key design patterns.\n\n"
            f"Directory Tree:\n{tree_for_summary}\n\nFile Analyses:\n{ctx}",
            system=SYSTEM_ARCHITECT,
        )

        key_sections = [f"### {rel(p)}\n{s}" for p, s in valid_summaries.items()]
        other_lines = [f"{rel(p)}: {s}" for p, s in skipped_summaries.items()]

        body = (
            f"# PROJECT SUMMARY\n{project_summary}\n\n"
            f"# DIRECTORY STRUCTURE\n```\n{tree}\n```\n\n"
            "# FILE ANALYSES\n" + "\n\n".join(key_sections)
        )
        if other_lines:
            body += "\n\n# SKIPPED / BINARY FILES\n" + "\n".join(other_lines)

        log.write("[bold #e8a045]Building AI-ready system prompt...[/]")
        ctx_for_prompt = (
            body
            if len(body) <= self.MAX_CTX_CHARS
            else body[: self.MAX_CTX_CHARS] + "\n...[truncated]"
        )
        final_prompt = await client.generate(
            "Generate a comprehensive, immediately-usable AI system prompt for a developer assistant "
            "working on this exact project. Be specific to this codebase.\n\n"
            + ctx_for_prompt,
            system=SYSTEM_PROMPT_ENGINEER,
        )

        stats_comment = (
            f"<!-- pxForge | files analyzed: {len(valid_summaries)} | "
            f"skipped: {len(skipped_summaries)} | "
            f"~{estimate_tokens(body):,} tokens -->"
        )
        return body + f"\n\n# AI SYSTEM PROMPT\n{final_prompt}\n\n{stats_comment}"


class DirSelectScreen(Screen):
    BINDINGS = [
        Binding("enter", "confirm", "Confirm", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def compose(self) -> ComposeResult:
        cwd = str(Path(self.app.state.get("path", Path.cwd())).resolve())
        yield Header()
        yield Container(
            Label("Select target directory", id="dir_label"),
            Horizontal(
                Input(value=cwd, placeholder="Path or paste a directory…", id="dir_path_input"),
                Button("Use Path", variant="default", id="btn_use_path"),
                id="dir_path_row",
            ),
            DirectoryTree(cwd, id="dir_tree"),
            Label(f"Selected: {cwd}", id="dir_selected_label"),
            Horizontal(
                Button("Cancel", variant="error", id="btn_cancel"),
                Button("Confirm", variant="primary", id="btn_confirm"),
                id="dir_buttons",
            ),
            id="dir_select_container",
        )
        yield Footer()

    def _set_path(self, path: str) -> None:
        try:
            resolved = str(Path(path).expanduser().resolve())
        except Exception:
            self.notify(f"Invalid path: {path}", severity="error")
            return
        if not Path(resolved).is_dir():
            self.notify("Not a directory.", severity="error")
            return
        self.app.state["path"] = resolved
        self.query_one("#dir_selected_label", Label).update(f"Selected: {resolved}")
        try:
            self.query_one("#dir_path_input", Input).value = resolved
        except Exception:
            pass

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._set_path(str(event.path))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "dir_path_input":
            self._set_path(event.value.strip())

    def action_confirm(self) -> None:
        self.app.push_screen(SettingsScreen())

    def action_cancel(self) -> None:
        self.app.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.app.exit()
        elif event.button.id == "btn_use_path":
            path = self.query_one("#dir_path_input", Input).value.strip()
            self._set_path(path)
        elif event.button.id == "btn_confirm":
            # Apply typed path if it differs / is valid
            typed = self.query_one("#dir_path_input", Input).value.strip()
            if typed:
                p = Path(typed).expanduser()
                if p.is_dir():
                    self.app.state["path"] = str(p.resolve())
            self.app.push_screen(SettingsScreen())


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back", show=True)]

    def _safe_provider(self) -> str:
        p = self.app.state.get("provider", "")
        return p if p in PROVIDER_MODELS else PROVIDER_NAMES[0]

    def _model_options(self, provider: str) -> List[str]:
        if provider == OLLAMA_PROVIDER:
            models = list(self.app.state.get("ollama_models") or [])
            saved = self.app.state.get("model", "")
            if saved and saved not in models and saved not in NO_MODEL_SENTINELS:
                models = [saved] + models
            return models or ["(no models — refresh below)"]
        return list(PROVIDER_MODELS.get(provider, [])) or ["(no models found)"]

    def _safe_model(self, provider: str) -> str:
        models = self._model_options(provider)
        saved = self.app.state.get("model", "")
        if saved in models:
            return saved
        return models[0]

    def _safe_preferred_ai(self) -> str:
        ai = self.app.state.get("preferred_ai", "Claude")
        return ai if ai in AI_BROWSER_SERVICES else AI_SERVICE_KEYS[0]

    def compose(self) -> ComposeResult:
        provider = self._safe_provider()
        model = self._safe_model(provider)
        preferred_ai = self._safe_preferred_ai()
        scan_path = self.app.state.get("path", str(Path.cwd()))
        is_ollama = provider == OLLAMA_PROVIDER
        models = self._model_options(provider)

        yield Header()
        yield ScrollableContainer(
            Vertical(
                Label(f"Scanning: {scan_path}", id="lbl_path"),
                Label("Provider:"),
                Select(
                    [(p, p) for p in PROVIDER_NAMES],
                    value=provider,
                    id="sel_provider",
                ),
                Label("API Key:"),
                Input(
                    placeholder=(
                        "Not required for Ollama"
                        if is_ollama
                        else "Leave blank to use saved key / env var"
                    ),
                    id="inp_key",
                    password=True,
                    disabled=is_ollama,
                ),
                Label("Model:"),
                Select(
                    [(m, m) for m in models],
                    value=model if model in models else Select.BLANK,
                    id="sel_model",
                ),
                Horizontal(
                    Label("⬤  Checking Ollama...", id="ollama_status_label"),
                    Button("↻ Refresh", id="btn_ollama_refresh", variant="default"),
                    id="ollama_status_row",
                    classes="" if is_ollama else "hidden",
                ),
                Label("Mode:"),
                Horizontal(
                    Label("Fast"),
                    Switch(
                        value=self.app.state.get("mode") == "high_quality",
                        id="sw_mode",
                    ),
                    Label("High Quality"),
                    id="mode_row",
                ),
                Static(
                    "Fast = local file summaries + 2 LLM calls.  "
                    "High Quality = LLM analysis per file.",
                    id="mode_hint",
                ),
                Label("Preferred AI for viewing output:"),
                Select(
                    [(name, name) for name in AI_SERVICE_KEYS],
                    value=preferred_ai,
                    id="sel_preferred_ai",
                ),
                Label("GitHub token (team share):"),
                Input(
                    placeholder="Leave blank for GITHUB_TOKEN / gh auth",
                    id="inp_github",
                    password=True,
                ),
                Horizontal(
                    Label("Share as private gist"),
                    Switch(
                        value=bool(self.app.state.get("share_private", True)),
                        id="sw_share_private",
                    ),
                    id="share_privacy_row",
                ),
                Static(
                    "Team Share uploads the prompt as a GitHub Gist and copies the URL.",
                    id="share_hint",
                ),
                Horizontal(
                    Button("Back", variant="default", id="btn_back"),
                    Button("Start Scan", variant="primary", id="btn_start"),
                    id="settings_buttons",
                ),
                id="settings_inner",
            ),
            id="settings_scroll",
        )
        yield Footer()

    def on_mount(self) -> None:
        provider = self._safe_provider()
        self._load_github_token()
        if provider == OLLAMA_PROVIDER:
            self.run_worker(self._probe_ollama(), exclusive=False)
        else:
            self._load_saved_key()
            self._hide_ollama_row()

    def action_go_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()

    def _hide_ollama_row(self) -> None:
        try:
            self.query_one("#ollama_status_row", Horizontal).add_class("hidden")
        except Exception:
            pass

    def _show_ollama_row(self) -> None:
        try:
            self.query_one("#ollama_status_row", Horizontal).remove_class("hidden")
        except Exception:
            pass

    async def _probe_ollama(self) -> None:
        self._show_ollama_row()
        try:
            self.query_one("#ollama_status_label", Label).update(
                "⬤  Connecting to Ollama..."
            )
        except Exception:
            pass

        models, status_msg = await fetch_ollama_models()

        try:
            lbl = self.query_one("#ollama_status_label", Label)
            dot_color = "green" if models else "red"
            lbl.update(f"[{dot_color}]⬤[/{dot_color}]  Ollama: {status_msg}")
        except Exception:
            pass

        if models:
            self.app.state["ollama_models"] = models
            saved = self.app.state.get("model", "")
            pick = saved if saved in models else models[0]
            self._repopulate_model_select(models, preferred=pick)

    def _load_saved_key(self) -> None:
        provider = self.app.state.get("provider", "")
        key = resolve_api_key(provider, "")
        if key:
            try:
                self.query_one("#inp_key", Input).value = key
            except Exception:
                pass

    def _load_github_token(self) -> None:
        token = resolve_github_token("")
        if token:
            try:
                self.query_one("#inp_github", Input).value = token
            except Exception:
                pass

    def _repopulate_model_select(
        self, models: List[str], preferred: str = ""
    ) -> None:
        if not models:
            models = ["(no models found)"]
        try:
            sel = self.query_one("#sel_model", Select)
            sel.set_options([(m, m) for m in models])
            pick = preferred if preferred in models else models[0]
            sel.value = pick
            self.app.state["model"] = pick
        except Exception:
            pass

    def _update_model_select(self, provider: str) -> None:
        self._repopulate_model_select(self._model_options(provider))

    def _toggle_key_input(self, is_ollama: bool) -> None:
        try:
            inp = self.query_one("#inp_key", Input)
            inp.disabled = is_ollama
            inp.placeholder = (
                "Not required for Ollama"
                if is_ollama
                else "Leave blank to use saved key / env var"
            )
            if is_ollama:
                inp.value = ""
        except Exception:
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        sel_id = event.select.id

        if sel_id == "sel_provider":
            provider = str(event.value)
            self.app.state["provider"] = provider
            is_ollama = provider == OLLAMA_PROVIDER
            self._toggle_key_input(is_ollama)

            if is_ollama:
                self._show_ollama_row()
                self.run_worker(self._probe_ollama(), exclusive=False)
            else:
                self._hide_ollama_row()
                self.call_later(self._update_model_select, provider)
                self.call_later(self._load_saved_key)

        elif sel_id == "sel_model":
            self.app.state["model"] = str(event.value)

        elif sel_id == "sel_preferred_ai":
            self.app.state["preferred_ai"] = str(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "sw_mode":
            self.app.state["mode"] = "high_quality" if event.value else "fast"
        elif event.switch.id == "sw_share_private":
            self.app.state["share_private"] = bool(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ollama_refresh":
            self.run_worker(self._probe_ollama(), exclusive=False)
            return

        if event.button.id == "btn_back":
            self.action_go_back()
            return

        if event.button.id == "btn_start":
            provider = self.app.state.get("provider", "")
            is_ollama = provider == OLLAMA_PROVIDER

            if is_ollama:
                model = self.app.state.get("model", "")
                if not model or model in NO_MODEL_SENTINELS:
                    self.notify(
                        "No Ollama model selected. Pull one first: ollama pull llama3",
                        severity="error",
                    )
                    return
                self.app.state["api_key"] = "ollama"
            else:
                typed = self.query_one("#inp_key", Input).value
                key = resolve_api_key(provider, typed)
                if not key:
                    self.notify(
                        "API key required (enter one, or set the provider env var).",
                        severity="error",
                    )
                    return
                self.app.state["api_key"] = key

            # Prefer Select widget value if state drifted
            try:
                sel_model = self.query_one("#sel_model", Select).value
                if sel_model is not Select.BLANK:
                    self.app.state["model"] = str(sel_model)
            except Exception:
                pass

            try:
                gh_typed = self.query_one("#inp_github", Input).value
                gh_token = resolve_github_token(gh_typed)
                self.app.state["github_token"] = gh_token
            except Exception:
                self.app.state["github_token"] = resolve_github_token("")

            try:
                self.app.state["share_private"] = bool(
                    self.query_one("#sw_share_private", Switch).value
                )
            except Exception:
                self.app.state.setdefault("share_private", True)

            config = load_config()
            if not is_ollama:
                config_key = PROVIDER_KEYS.get(provider, "")
                if config_key:
                    config[config_key] = self.app.state["api_key"]
            config["last_provider"] = provider
            config["last_model"] = self.app.state.get("model", "")
            config["last_mode"] = self.app.state.get("mode", "fast")
            config["preferred_ai"] = self.app.state.get("preferred_ai", "Claude")
            config["share_private"] = bool(self.app.state.get("share_private", True))
            gh_token = (self.app.state.get("github_token") or "").strip()
            if gh_token:
                config["github_token"] = gh_token
            save_config(config)

            self.app.push_screen(ProgressScreen())


class ProgressScreen(Screen):
    BINDINGS = [Binding("escape", "cancel_scan", "Cancel", show=True)]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Initializing…", id="progress_label"),
            Static("", id="progress_meta"),
            ProgressBar(total=100, show_eta=False, id="prog_bar"),
            RichLog(id="scan_log", wrap=True, highlight=True, markup=True),
            Horizontal(
                Button("Cancel  Esc", variant="error", id="btn_cancel_scan"),
                id="progress_buttons",
            ),
            id="progress_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._cancelled = False
        self._worker = self.run_worker(self._run_scan(), exclusive=True)

    def action_cancel_scan(self) -> None:
        self._cancelled = True
        if hasattr(self, "_worker"):
            self._worker.cancel()
        self.notify("Scan cancelled.", severity="warning")
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel_scan":
            self.action_cancel_scan()

    def _set_progress(self, value: int) -> None:
        prog = self.query_one("#prog_bar", ProgressBar)
        value = max(0, min(100, int(value)))
        # ProgressBar has no absolute set in all versions — advance from tracked baseline.
        current = getattr(self, "_prog_value", 0)
        delta = value - current
        if delta > 0:
            prog.advance(delta)
            self._prog_value = value

    async def _run_scan(self) -> None:
        log = self.query_one("#scan_log", RichLog)
        lbl = self.query_one("#progress_label", Label)
        meta = self.query_one("#progress_meta", Static)
        state = self.app.state
        client: Optional[LLMClient] = None
        self._prog_value = 0

        try:
            provider = state["provider"]
            mode = state.get("mode", "fast")
            is_ollama = provider == OLLAMA_PROVIDER

            if is_ollama:
                log.write(
                    f"[bold]Provider:[/] {provider}  "
                    f"[bold]Model:[/] {state['model']}  "
                    f"[dim](local)[/]"
                )
            else:
                log.write(
                    f"[bold]Provider:[/] {provider}  [bold]Model:[/] {state['model']}"
                )
            log.write(f"[bold]Path:[/] {state['path']}")
            log.write(
                f"[bold]Mode:[/] {'Fast (local file summaries)' if mode == 'fast' else 'High Quality (LLM per file)'}"
            )

            client = LLMClient(
                provider, state["api_key"], state["model"], mode
            )

            lbl.update("Scanning project…")
            meta.update("Walking tree & reading files")

            def on_read_progress(done: int, total: int) -> None:
                if total <= 0:
                    return
                # Scan phase: 0 → 15
                self._set_progress(int(15 * done / total))
                meta.update(f"Reading files  {done}/{total}")

            scanner = ProjectScanner()
            tree, files = await scanner.scan(
                state["path"], log, on_read_progress=on_read_progress
            )

            total_files = len(files)
            binary_count = sum(1 for f in files if f.get("is_binary"))
            skipped_count = sum(1 for f in files if f.get("skipped"))
            analyzable = total_files - binary_count - skipped_count

            log.write(
                f"Found [bold]{total_files}[/] files — "
                f"[green]{analyzable}[/] analyzable, "
                f"[dim]{binary_count} binary, {skipped_count} skipped[/]"
            )

            if mode == "fast":
                log.write(
                    "[dim]Fast mode: summarizing files locally (no per-file API calls).[/]"
                )
            elif is_ollama and analyzable > 10:
                log.write(
                    f"[yellow]⚠  Ollama concurrency is limited. "
                    f"{analyzable} files may take a while.[/]"
                )

            self._set_progress(15)

            def on_file_progress(done: int, total: int) -> None:
                if total <= 0:
                    self._set_progress(85)
                    return
                # Analyze phase: 15 → 85
                self._set_progress(15 + int(70 * done / total))
                verb = "Summarizing" if mode == "fast" else "Analyzing"
                lbl.update(f"{verb} files… [{done}/{total}]")
                meta.update(f"{done}/{total} files")

            lbl.update(
                "Summarizing files…" if mode == "fast" else "Analyzing files…"
            )
            analyzer = FileAnalyzer(client, log, mode)
            file_summaries = await analyzer.analyze(files, on_file_progress)
            self._set_progress(85)

            lbl.update("Building final prompt…")
            meta.update("Project summary + system prompt")
            log.write("[bold]Building AI-ready context document…[/]")
            builder = PromptBuilder()
            final_output = await builder.build(
                tree, file_summaries, client, log, state["path"]
            )

            state["output"] = final_output
            state["output_dir"] = state["path"]
            state["file_stats"] = {
                "total": total_files,
                "analyzed": analyzable,
                "binary": binary_count,
                "skipped": skipped_count,
            }
            self._set_progress(100)
            lbl.update("Done!")
            meta.update("Complete")
            log.write("[bold green]Complete.[/]")
            await asyncio.sleep(0.35)
            if not self._cancelled:
                self.app.push_screen(OutputScreen())

        except asyncio.CancelledError:
            log.write("[yellow]Cancelled.[/]")
            raise
        except Exception as e:
            log.write(f"[bold red]Error: {type(e).__name__}: {e}[/]")
            lbl.update(f"Failed: {type(e).__name__}")
            meta.update(str(e)[:80])
            self.notify(str(e), severity="error", timeout=10)
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass


class OutputScreen(Screen):
    BINDINGS = [
        Binding("ctrl+s", "save_file", "Save"),
        Binding("ctrl+y", "copy_output", "Copy"),
        Binding("ctrl+t", "share_team", "Share"),
        Binding("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        stats = self.app.state.get("file_stats", {})
        stats_text = (
            f"  {stats.get('total', 0)} files total  |  "
            f"{stats.get('analyzed', 0)} analyzed  |  "
            f"{stats.get('binary', 0)} binary  |  "
            f"{stats.get('skipped', 0)} skipped"
        ) if stats else ""

        out = self.app.state.get("output", "")
        token_est = estimate_tokens(out)
        preferred_ai = self.app.state.get("preferred_ai", "Claude")
        last_share = self.app.state.get("share_url", "")

        ai_btns: List[Any] = [Label("Open with AI: ", id="ai_open_label")]
        for ai_name in AI_SERVICE_KEYS:
            variant = "primary" if ai_name == preferred_ai else "default"
            safe_id = (
                "btn_ai_"
                + ai_name.lower()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
            )
            ai_btns.append(
                Button(ai_name, id=safe_id, variant=variant, classes="ai_btn")
            )

        yield Header()
        yield Vertical(
            Static(stats_text, id="stats_bar"),
            Static(f"  ~{token_est:,} tokens estimated", id="token_label"),
            Container(
                TextArea(id="output_text", read_only=True, show_line_numbers=False),
                id="scroll_area",
            ),
            Vertical(
                Horizontal(*ai_btns, id="ai_open_row"),
                Horizontal(
                    Button("Share Team Link  Ctrl+T", variant="primary", id="btn_share"),
                    Button(
                        "Open Share",
                        variant="default",
                        id="btn_open_share",
                        disabled=not bool(last_share),
                    ),
                    id="share_row",
                ),
                Static(
                    f"  Last share: {last_share}" if last_share else "  No team link yet",
                    id="share_status",
                ),
                Horizontal(
                    Button("Back", variant="default", id="btn_back"),
                    Button("Save  Ctrl+S", variant="success", id="btn_save"),
                    Button("Copy  Ctrl+Y", variant="default", id="btn_copy"),
                    Button("Save & Open AI", variant="warning", id="btn_save_open"),
                    Button("Exit", variant="error", id="btn_exit"),
                    id="output_buttons",
                ),
                id="bottom_panel",
            ),
            id="output_section",
        )
        yield Footer()

    def on_mount(self) -> None:
        out = self.app.state.get("output", "No output generated.")
        area = self.query_one("#output_text", TextArea)
        area.load_text(out)

    def action_save_file(self) -> None:
        self._save(self.app.state.get("output", ""))

    def action_copy_output(self) -> None:
        self._do_copy(self.app.state.get("output", ""))

    def action_share_team(self) -> None:
        self.run_worker(self._share_team_link(), exclusive=True, thread=False)

    def action_go_back(self) -> None:
        # Pop output + finished progress so Back lands on settings.
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        if len(self.app.screen_stack) > 1 and isinstance(
            self.app.screen, ProgressScreen
        ):
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        out = self.app.state.get("output", "")
        btn_id = event.button.id or ""

        if btn_id == "btn_save":
            self._save(out)
        elif btn_id == "btn_copy":
            self._do_copy(out)
        elif btn_id == "btn_back":
            self.action_go_back()
        elif btn_id == "btn_share":
            self.action_share_team()
        elif btn_id == "btn_open_share":
            url = self.app.state.get("share_url", "")
            if url:
                try:
                    webbrowser.open(url)
                except Exception as e:
                    self.notify(f"Could not open browser: {e}", severity="error")
            else:
                self.notify("No share link yet — create one first.", severity="warning")
        elif btn_id == "btn_save_open":
            saved_path = self._save(out, notify=False)
            preferred_ai = self.app.state.get("preferred_ai", "Claude")
            self._open_ai_browser(preferred_ai, out, saved_path)
        elif btn_id == "btn_exit":
            self.app.exit()
        elif btn_id.startswith("btn_ai_"):
            raw = btn_id[len("btn_ai_") :]
            matched = next(
                (
                    name
                    for name in AI_SERVICE_KEYS
                    if name.lower()
                    .replace(" ", "_")
                    .replace("(", "")
                    .replace(")", "")
                    == raw
                ),
                None,
            )
            if matched:
                self._open_ai_browser(matched, out)

    async def _share_team_link(self) -> None:
        content = self.app.state.get("output", "")
        if not content.strip():
            self.notify("Nothing to share.", severity="error")
            return

        token = (
            (self.app.state.get("github_token") or "").strip()
            or resolve_github_token("")
        )
        private = bool(self.app.state.get("share_private", True))
        project = Path(self.app.state.get("path", ".")).name or "project"

        try:
            btn = self.query_one("#btn_share", Button)
            btn.disabled = True
            status = self.query_one("#share_status", Static)
            visibility = "private" if private else "public"
            status.update(f"  Uploading {visibility} gist…")
        except Exception:
            btn = None
            status = None

        try:
            url = await create_team_share_gist(
                content,
                project_name=project,
                token=token,
                private=private,
            )
            self.app.state["share_url"] = url
            self.app.state["github_token"] = token

            config = load_config()
            if token:
                config["github_token"] = token
            config["share_private"] = private
            config["last_share_url"] = url
            save_config(config)

            copied = copy_to_clipboard(url)
            visibility = "private" if private else "public"
            msg = f"Team link ({visibility}) ready"
            if copied:
                msg += " — URL copied"
            self.notify(msg, severity="information", timeout=10)
            if status:
                status.update(f"  Share: {url}")
            try:
                open_btn = self.query_one("#btn_open_share", Button)
                open_btn.disabled = False
            except Exception:
                pass
        except Exception as e:
            self.notify(str(e), severity="error", timeout=12)
            if status:
                last = self.app.state.get("share_url", "")
                status.update(
                    f"  Share failed. {('Last: ' + last) if last else 'No team link yet'}"
                )
        finally:
            if btn is not None:
                try:
                    btn.disabled = False
                except Exception:
                    pass

    def _save(self, content: str, notify: bool = True) -> Optional[Path]:
        try:
            out_dir = Path(self.app.state.get("output_dir", "."))
            out_path = out_dir / "pxforge_output.md"
            out_path.write_text(content, encoding="utf-8")
            if notify:
                self.notify(f"Saved to {out_path}", severity="information")
            return out_path
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")
            return None

    def _do_copy(self, content: str) -> None:
        if copy_to_clipboard(content):
            self.notify("Copied to clipboard.", severity="information")
        else:
            self.notify(
                "No clipboard tool found. Install wl-copy, xclip, or xsel.",
                severity="warning",
            )

    def _open_ai_browser(
        self,
        ai_name: str,
        content: str,
        saved_path: Optional[Path] = None,
    ) -> None:
        url = AI_BROWSER_SERVICES.get(ai_name, "")
        if not url:
            self.notify(f"Unknown AI service: {ai_name}", severity="error")
            return
        copied = copy_to_clipboard(content)
        try:
            webbrowser.open(url)
            if copied:
                self.notify(
                    f"Opened {ai_name}. Prompt copied — paste it in.",
                    severity="information",
                    timeout=8,
                )
            elif saved_path:
                self.notify(
                    f"Opened {ai_name}. Copy the prompt from {saved_path.name}",
                    severity="information",
                    timeout=8,
                )
            else:
                self.notify(
                    f"Opened {ai_name}. Use Save to get the prompt.",
                    severity="information",
                    timeout=8,
                )
        except Exception as e:
            self.notify(f"Could not open browser: {e}", severity="error")


class pxForgeApp(App):
    TITLE = "pxForge"
    SUB_TITLE = "AI-ready project context"
    CSS = APP_CSS
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, start_path: Optional[str] = None) -> None:
        super().__init__()
        self.start_path = start_path
        resolved = start_path or str(Path.cwd())
        config = load_config()

        saved_provider = config.get("last_provider", "Anthropic (Claude)")
        if saved_provider not in PROVIDER_MODELS:
            saved_provider = PROVIDER_NAMES[0]

        saved_model = config.get("last_model", "") or ""
        known = PROVIDER_MODELS.get(saved_provider, [])
        if saved_provider == OLLAMA_PROVIDER:
            # Keep last Ollama model even before live probe fills the list.
            pass
        elif saved_model not in known:
            saved_model = known[0] if known else ""

        preferred_ai = config.get("preferred_ai", "Claude")
        if preferred_ai not in AI_BROWSER_SERVICES:
            preferred_ai = AI_SERVICE_KEYS[0]

        last_mode = config.get("last_mode", "fast")
        if last_mode not in ("fast", "high_quality"):
            last_mode = "fast"

        self.state: Dict[str, Any] = {
            "path": resolved,
            "output_dir": resolved,
            "provider": saved_provider,
            "api_key": "",
            "model": saved_model,
            "mode": last_mode,
            "output": "",
            "preferred_ai": preferred_ai,
            "file_stats": {},
            "ollama_models": [],
            "github_token": resolve_github_token(""),
            "share_private": bool(config.get("share_private", True)),
            "share_url": (config.get("last_share_url") or ""),
        }

    def on_mount(self) -> None:
        if self.start_path:
            self.push_screen(SettingsScreen())
        else:
            self.push_screen(DirSelectScreen())


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] == "install":
        install_to_path()
        sys.exit(0)

    if args and args[0] in ("-h", "--help"):
        print("pxforge — AI-ready project prompt generator\n")
        print("Usage:")
        print("  pxforge                  Launch with directory picker")
        print("  pxforge .                Scan current directory")
        print("  pxforge /path/to/project Scan given directory")
        print("  pxforge install          Install 'pxforge' command to your shell PATH")
        print("\nOptions:")
        print("  -h, --help               Show this message")
        sys.exit(0)

    target: Optional[str] = None
    if args:
        p = Path(args[0]).resolve()
        if not p.exists():
            print(f"Error: path does not exist: {p}", file=sys.stderr)
            sys.exit(1)
        if not p.is_dir():
            print(f"Error: not a directory: {p}", file=sys.stderr)
            sys.exit(1)
        target = str(p)

    pxForgeApp(start_path=target).run()
