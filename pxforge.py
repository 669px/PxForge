import os
import sys
import json
import stat
import asyncio
import random
import webbrowser
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import httpx
from textual.app import App, ComposeResult, Screen
from textual.widgets import (
    Header, Footer, DirectoryTree, Input, Select, Switch, Label,
    ProgressBar, RichLog, Button, Static, Collapsible, RadioSet, RadioButton
)
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.binding import Binding

CONFIG_DIR = Path.home() / ".pxforge"
CONFIG_FILE = CONFIG_DIR / "config.json"
BIN_DIR = Path.home() / ".local" / "bin"
SCRIPT_PATH = Path(__file__).resolve()

AI_BROWSER_SERVICES = {
    "Claude": "https://claude.ai",
    "ChatGPT": "https://chatgpt.com",
    "Gemini": "https://gemini.google.com",
    "Grok": "https://grok.com",
    "Perplexity": "https://perplexity.ai",
    "Mistral": "https://chat.mistral.ai",
    "DeepSeek": "https://chat.deepseek.com",
}

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
        line = f"fish_add_path {bin_str}" if shell_name == "fish" else f'export PATH="{bin_str}:$PATH"'
        with open(rc_file, "a") as f:
            f.write(f"\n# pxforge\n{line}\n")
    print(f"Installed: {wrapper}")
    print(f"PATH entry added to: {rc_file}")
    print(f"\nRestart your shell or run:  source {rc_file}")
    print("Then use:  pxforge            # scans current directory")
    print("           pxforge /some/path # scans given path")


IGNORED_DIRS = {
    '.git', 'node_modules', 'dist', 'build', '__pycache__',
    '.venv', 'env', 'venv', '.next', '.nuxt', 'coverage', '.cache',
    '.idea', '.vscode', '.DS_Store', 'target', 'out', '.gradle',
    '.mypy_cache', '.pytest_cache', '.ruff_cache', 'vendor'
}
IGNORED_EXT = {
    '.pyc', '.pyo', '.exe', '.dll', '.so', '.dylib', '.whl',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.bin', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
    '.pdf', '.mp3', '.mp4', '.avi', '.lock', '.bmp', '.webp',
    '.tiff', '.wav', '.ogg', '.flac', '.ttf', '.woff', '.woff2', '.eot',
    '.class', '.o', '.a', '.lib', '.pdb', '.map', '.min.js', '.min.css',
    '.DS_Store', '.suo', '.user', '.orig', '.rej',
}
BINARY_MARKERS = {b'\x7fELF', b'\x89PNG', b'\xff\xd8\xff\xe0', b'%PDF-1.', b'PK\x03\x04', b'\x00\x00\x00\x00'}
CHUNK_SIZE = 6000
MIN_CONTENT_LEN = 20
MAX_FILE_SIZE_BYTES = 500_000

PROVIDER_KEYS = {
    "OpenAI": "openai_key",
    "Anthropic (Claude)": "anthropic_key",
    "Groq": "groq_key",
    "OpenRouter": "openrouter_key",
}

PROVIDER_ENV = {
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic (Claude)": "ANTHROPIC_API_KEY",
    "Groq": "GROQ_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
}

PROVIDER_MODELS = {
    "OpenAI": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
    "Anthropic (Claude)": [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022",
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
}

PROVIDER_CONCURRENCY = {
    "OpenAI": 8,
    "Anthropic (Claude)": 5,
    "Groq": 3,
    "OpenRouter": 5,
}

APP_CSS = """
Screen {
    background: $surface;
}

Header {
    background: $primary;
    color: $text;
    text-style: bold;
}

Footer {
    background: $primary-darken-2;
}

#dir_select_container {
    width: 100%;
    height: 100%;
    padding: 1 2;
}

#dir_label {
    margin-bottom: 1;
    text-style: bold;
    color: $accent;
}

#dir_tree {
    height: 1fr;
    border: round $primary;
    background: $surface-darken-1;
    margin-bottom: 1;
}

#dir_selected_label {
    color: $text-muted;
    margin-bottom: 1;
    padding: 0 1;
}

#dir_buttons {
    height: 3;
    align: right middle;
    margin-top: 1;
}

#settings_container {
    width: 100%;
    height: 100%;
    padding: 1 2;
}

#lbl_path {
    color: $accent;
    text-style: bold italic;
    margin-bottom: 1;
    padding: 0 1;
    border-left: thick $accent;
}

#settings_container Label {
    margin-top: 1;
    color: $text-muted;
    text-style: bold;
}

#settings_container Select {
    margin-bottom: 0;
}

#settings_container Input {
    margin-bottom: 0;
}

#mode_row {
    height: 3;
    align: left middle;
    margin-top: 1;
    margin-bottom: 1;
}

#mode_row Label {
    margin: 0 1;
    color: $text;
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
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

#prog_bar {
    margin-bottom: 1;
}

#scan_log {
    height: 1fr;
    border: round $primary;
    background: $surface-darken-1;
    padding: 0 1;
}

#scroll_area {
    height: 1fr;
    border: round $primary;
    background: $surface-darken-1;
    margin: 0 2;
}

#output_text {
    padding: 1 2;
}

#output_buttons {
    height: auto;
    align: right middle;
    padding: 0 2;
    margin: 1 0;
}

#ai_open_row {
    height: auto;
    align: left middle;
    padding: 0 2;
    margin-bottom: 1;
    width: 100%;
}

#ai_open_label {
    color: $text-muted;
    text-style: bold;
    padding: 0 1;
    margin-right: 1;
}

.ai_btn {
    margin-left: 1;
    min-width: 12;
}

#stats_bar {
    color: $text-muted;
    padding: 0 2;
    margin-bottom: 1;
    height: 1;
}

Button {
    margin-left: 1;
}

#output_section {
    height: 100%;
    width: 100%;
}

#bottom_panel {
    height: auto;
    width: 100%;
    border-top: solid $primary;
    padding-top: 1;
}

#token_label {
    color: $warning;
    padding: 0 2;
    margin-bottom: 1;
    text-style: italic;
}
"""


def load_config() -> Dict[str, Any]:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(config: Dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def copy_to_clipboard(content: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=content, text=True, check=True, timeout=5)
            return True
        if sys.platform == "win32":
            subprocess.run(["clip"], input=content, text=True, shell=True, check=True, timeout=5)
            return True
        for cmd in [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
            try:
                subprocess.run(cmd, input=content, text=True, check=True, timeout=5)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        return False
    except Exception:
        return False


SYSTEM_ANALYST = """\
You are an expert code analyst embedded in pxForge, a tool that generates AI-ready project context documents.

Your job is to analyze source code and text files with precision and brevity. For every file or chunk you receive:
- Identify the primary purpose of the code
- List key functions, classes, or components and what they do
- Note external dependencies and imports
- Highlight non-obvious logic, patterns, or architectural decisions

Rules:
- Be concise. Bullet points over prose.
- Never summarize what is obvious from the code structure alone.
- Do not include line numbers, only names and behaviors.
- If the content is configuration or data (JSON, YAML, env), describe what it configures and what values matter.
- If the content is a markup or template file, describe its role in the UI or build pipeline.
"""

SYSTEM_ARCHITECT = """\
You are a senior software architect embedded in pxForge, a tool that generates AI-ready project context documents.

Your job is to synthesize file-level analyses into a high-level project overview. You will receive a directory tree and per-file summaries.

Produce a concise PROJECT SUMMARY that covers:
- The technology stack (languages, frameworks, major libraries)
- The architectural pattern (MVC, microservices, monolith, CLI tool, etc.)
- The core functionality and purpose of the project
- How the major components relate to each other

Rules:
- Write in clear, direct technical prose. No fluff.
- Three to six paragraphs maximum.
- Do not repeat information that is obvious from the file names alone.
- Focus on what a new developer needs to understand to be productive immediately.
"""

SYSTEM_PROMPT_ENGINEER = """\
You are an expert AI prompt engineer embedded in pxForge, a tool that generates AI-ready project context documents.

Your job is to produce a system prompt that will be used to configure an AI coding assistant working on this specific project. You will receive a full project summary, directory structure, and per-file analyses.

The system prompt you write must:
- Establish the AI's role as a knowledgeable collaborator on this exact codebase
- Summarize the project's purpose, stack, and architecture in two to three sentences
- List the key conventions, patterns, and constraints the AI must respect (naming, structure, idioms)
- Describe what the AI should always do (e.g. follow existing patterns, use existing utilities, write idiomatic code)
- Describe what the AI must never do (e.g. introduce new dependencies without asking, break existing interfaces)
- Include a section on the directory layout so the AI knows where things live

Rules:
- Write in second person ("You are...", "You must...", "Never...").
- Be specific to this project. Generic advice that applies to any codebase has no value here.
- The prompt must be immediately usable as a system prompt in any AI coding assistant (Cursor, Claude, Copilot Chat, etc.).
- Keep it under 800 words.
"""


class LLMClient:
    URLS = {
        "OpenAI": "https://api.openai.com/v1/chat/completions",
        "Anthropic (Claude)": "https://api.anthropic.com/v1/messages",
        "Groq": "https://api.groq.com/openai/v1/chat/completions",
        "OpenRouter": "https://openrouter.ai/api/v1/chat/completions",
    }
    MAX_RETRIES = 5

    def __init__(self, provider: str, api_key: str, model: str, mode: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.max_tokens = 4096 if mode == "high_quality" else 2048
        self._http = httpx.AsyncClient(timeout=180.0)

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> Dict[str, str]:
        base = {"Content-Type": "application/json"}
        if self.provider == "Anthropic (Claude)":
            return {**base, "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        if self.provider == "OpenRouter":
            return {**base, "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/pxforge", "X-Title": "pxForge"}
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
        msg = choices[0].get("message", {})
        return msg.get("content", "") or ""

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
                    last_exc = Exception(f"Rate limited (429), retried after {wait:.1f}s")
                    continue
                if resp.status_code in (503, 502, 500):
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
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(1)
        raise last_exc or RuntimeError("Max retries exceeded")


def _listdir_filtered(dirpath: str) -> List[Tuple[str, str, bool]]:
    try:
        entries = sorted(os.scandir(dirpath), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return []
    result = []
    for entry in entries:
        if entry.name.startswith('.') and entry.name in IGNORED_DIRS:
            continue
        if entry.name in IGNORED_DIRS:
            continue
        ext = Path(entry.name).suffix.lower()
        if entry.is_file(follow_symlinks=False) and ext in IGNORED_EXT:
            continue
        result.append((entry.name, entry.path, entry.is_dir(follow_symlinks=False)))
    return result


def _read_file_sync(filepath: str) -> Optional[Dict[str, Any]]:
    ext = Path(filepath).suffix.lower()
    try:
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE_BYTES:
            return {"path": filepath, "type": ext, "is_binary": False,
                    "content": None, "skipped": True, "reason": f"file too large ({size // 1024}KB)"}
        with open(filepath, "rb") as f:
            header = f.read(16)
        if any(header.startswith(m) for m in BINARY_MARKERS):
            return {"path": filepath, "type": ext, "is_binary": True, "content": None, "skipped": False}
        if b'\x00' in header:
            return {"path": filepath, "type": ext, "is_binary": True, "content": None, "skipped": False}
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"path": filepath, "type": ext, "is_binary": False, "content": content, "skipped": False}
    except PermissionError:
        return {"path": filepath, "type": ext, "is_binary": False,
                "content": None, "skipped": True, "reason": "permission denied"}
    except Exception:
        return None


class ProjectScanner:
    async def scan(self, path: str, log: RichLog) -> Tuple[str, List[Dict[str, Any]]]:
        log.write("[bold cyan]Walking directory tree...[/bold cyan]")
        tree_lines, files = await self._walk(path, "")
        return "\n".join(tree_lines), files

    async def _walk(self, dirpath: str, prefix: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        entries = await asyncio.to_thread(_listdir_filtered, dirpath)
        tree_lines: List[str] = []
        file_paths: List[str] = []
        subdir_tasks: List[Tuple[int, str, str]] = []

        for i, (name, full_path, is_dir) in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")
            tree_lines.append(f"{prefix}{connector}{name}")
            if is_dir:
                subdir_tasks.append((len(tree_lines) - 1, full_path, child_prefix))
            else:
                file_paths.append(full_path)

        file_infos: List[Dict[str, Any]] = []
        if file_paths:
            read_results = await asyncio.gather(
                *[asyncio.to_thread(_read_file_sync, p) for p in file_paths]
            )
            file_infos = [r for r in read_results if r is not None]

        if subdir_tasks:
            sub_results = await asyncio.gather(
                *[self._walk(fp, cp) for _, fp, cp in subdir_tasks]
            )
            final_lines = list(tree_lines)
            offset = 0
            for (insert_idx, _, _), (sub_lines, sub_files) in zip(subdir_tasks, sub_results):
                pos = insert_idx + 1 + offset
                final_lines[pos:pos] = sub_lines
                offset += len(sub_lines)
                file_infos.extend(sub_files)
            return final_lines, file_infos

        return tree_lines, file_infos


class FileAnalyzer:
    def __init__(self, client: LLMClient, log: RichLog):
        self.client = client
        self.log = log
        self._sem = asyncio.Semaphore(PROVIDER_CONCURRENCY.get(client.provider, 5))

    async def analyze(
        self,
        files: List[Dict[str, Any]],
        on_progress: Any,
    ) -> Dict[str, str]:
        total = len(files)
        results: Dict[str, Optional[str]] = {f["path"]: None for f in files}

        async def process(f: Dict[str, Any], idx: int) -> None:
            name = os.path.basename(f["path"])
            content = f.get("content") or ""

            if f.get("skipped"):
                reason = f.get("reason", "skipped")
                results[f["path"]] = f"[SKIPPED:{reason}] {f['path']}"
                on_progress(idx + 1, total)
                return

            if f["is_binary"] or len(content.strip()) < MIN_CONTENT_LEN:
                label = "BINARY" if f["is_binary"] else "SKIPPED:empty"
                results[f["path"]] = f"[{label}] {f['path']}"
                on_progress(idx + 1, total)
                return

            chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]

            async def analyze_chunk(ci: int, chunk: str) -> str:
                prompt = (
                    "Analyze this code/text. Concisely extract:\n"
                    "- Purpose\n- Key functions/classes\n- Dependencies\n- Important logic\n\n"
                    f"File: {name}\nContent:\n{chunk}"
                )
                async with self._sem:
                    self.log.write(
                        f"  [[bold]{idx+1}/{total}[/bold]] {name}"
                        + (f" — chunk {ci+1}/{len(chunks)}" if len(chunks) > 1 else "")
                    )
                    try:
                        return await self.client.generate(prompt, system=SYSTEM_ANALYST)
                    except Exception as e:
                        self.log.write(f"  [red][!] {name} chunk {ci+1}: {e}[/red]")
                        return ""

            summaries = [s for s in await asyncio.gather(
                *[analyze_chunk(ci, chunk) for ci, chunk in enumerate(chunks)]
            ) if s.strip()]

            if not summaries:
                results[f["path"]] = f"[FAILED] {f['path']}"
            elif len(summaries) == 1:
                results[f["path"]] = summaries[0]
            else:
                self.log.write(f"  [yellow]Merging {len(summaries)} chunks for {name}[/yellow]")
                merge_prompt = (
                    "Merge these partial analyses of the same file into one coherent summary. "
                    "File: " + name + "\n"
                    "Preserve: Purpose, Key functions/classes, Dependencies, Important logic.\n\n"
                    + "\n---\n".join(summaries)
                )
                async with self._sem:
                    try:
                        merged = await self.client.generate(merge_prompt, system=SYSTEM_ANALYST)
                        results[f["path"]] = merged if merged else "\n".join(summaries)
                    except Exception:
                        results[f["path"]] = "\n".join(summaries)

            on_progress(idx + 1, total)

        await asyncio.gather(*[process(f, i) for i, f in enumerate(files)])
        return {k: v or "" for k, v in results.items()}


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
        log.write("[bold cyan]Generating project summary...[/bold cyan]")

        def rel(p: str) -> str:
            try:
                return os.path.relpath(p, base_path) if base_path else os.path.basename(p)
            except ValueError:
                return os.path.basename(p)

        valid_summaries = {p: s for p, s in file_summaries.items() if not s.startswith("[")}
        skipped_summaries = {p: s for p, s in file_summaries.items() if s.startswith("[")}

        ctx_lines = [f"{rel(p)}: {s}" for p, s in valid_summaries.items()]
        ctx = "\n".join(ctx_lines)
        if len(ctx) > self.MAX_CTX_CHARS:
            ctx = ctx[:self.MAX_CTX_CHARS] + "\n...[truncated for context window]"

        tree_for_summary = tree
        if len(tree) > 10_000:
            tree_for_summary = tree[:10_000] + "\n...[tree truncated]"

        project_summary = await client.generate(
            "Analyze the project structure and file summaries below. "
            "Write a concise PROJECT SUMMARY covering: technology stack, architecture, core functionality, and key design patterns.\n\n"
            f"Directory Tree:\n{tree_for_summary}\n\nFile Analyses:\n{ctx}",
            system=SYSTEM_ARCHITECT,
        )

        key_sections: List[str] = []
        for p, s in valid_summaries.items():
            key_sections.append(f"### {rel(p)}\n{s}")

        other_lines = [f"{rel(p)}: {s}" for p, s in skipped_summaries.items()]

        body = (
            f"# PROJECT SUMMARY\n{project_summary}\n\n"
            f"# DIRECTORY STRUCTURE\n```\n{tree}\n```\n\n"
            "# FILE ANALYSES\n" + "\n\n".join(key_sections)
        )
        if other_lines:
            body += "\n\n# SKIPPED / BINARY FILES\n" + "\n".join(other_lines)

        log.write("[bold cyan]Building AI-ready system prompt...[/bold cyan]")
        ctx_for_prompt = body if len(body) <= self.MAX_CTX_CHARS else body[:self.MAX_CTX_CHARS] + "\n...[truncated]"
        final_prompt = await client.generate(
            "Generate a comprehensive, immediately-usable AI system prompt for a developer assistant "
            "working on this exact project. Be specific. Base it on the full context below.\n\n" + ctx_for_prompt,
            system=SYSTEM_PROMPT_ENGINEER,
        )

        stats = (
            f"<!-- pxForge Stats: {len(valid_summaries)} files analyzed, "
            f"{len(skipped_summaries)} skipped, "
            f"~{estimate_tokens(body):,} tokens -->"
        )
        return body + f"\n\n# AI SYSTEM PROMPT\n{final_prompt}\n\n{stats}"


class DirSelectScreen(Screen):
    def compose(self) -> ComposeResult:
        cwd = str(Path.cwd())
        yield Header()
        yield Container(
            Label("Select target directory:", id="dir_label"),
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

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.app.state["path"] = str(event.path)
        self.query_one("#dir_selected_label", Label).update(f"Selected: {event.path}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel":
            self.app.exit()
        elif event.button.id == "btn_confirm":
            self.app.push_screen(SettingsScreen())


class SettingsScreen(Screen):
    def compose(self) -> ComposeResult:
        current_provider = self.app.state["provider"]
        current_model = self.app.state["model"]
        providers = [(p, p) for p in PROVIDER_MODELS]
        provider_models = PROVIDER_MODELS.get(current_provider, [])
        if not provider_models:
            current_provider = "OpenAI"
            provider_models = PROVIDER_MODELS["OpenAI"]
        models = [(m, m) for m in provider_models]
        default_model = current_model if current_model in provider_models else provider_models[0]
        scan_path = self.app.state["path"]
        yield Header()
        yield ScrollableContainer(
            Vertical(
                Label(f"Scanning: {scan_path}", id="lbl_path"),
                Label("Provider:"),
                Select(providers, value=current_provider, id="sel_provider"),
                Label("API Key:"),
                Input(
                    placeholder="Enter API key (or leave blank to use saved/env)",
                    id="inp_key",
                    password=True,
                ),
                Label("Model:"),
                Select(models, value=default_model, id="sel_model"),
                Label("Mode:"),
                Horizontal(
                    Label("Fast"),
                    Switch(value=self.app.state["mode"] == "high_quality", id="sw_mode"),
                    Label("High Quality"),
                    id="mode_row",
                ),
                Label("Preferred AI for viewing output:"),
                Select(
                    [(name, name) for name in AI_BROWSER_SERVICES],
                    value=self.app.state.get("preferred_ai", "Claude"),
                    id="sel_preferred_ai",
                ),
                Horizontal(
                    Button("Back", variant="default", id="btn_back"),
                    Button("Start Scan", variant="primary", id="btn_start"),
                    id="settings_buttons",
                ),
                id="settings_container",
            )
        )
        yield Footer()

    def on_mount(self) -> None:
        self._load_saved_key()

    def _load_saved_key(self) -> None:
        provider = self.app.state["provider"]
        config = load_config()
        key_field = PROVIDER_KEYS.get(provider, "")
        key = config.get(key_field, "")
        if not key:
            key = os.getenv(PROVIDER_ENV.get(provider, ""), "")
        if key:
            self.query_one("#inp_key", Input).value = key

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            return
        sel_id = event.select.id
        if sel_id == "sel_provider":
            provider = str(event.value)
            self.app.state["provider"] = provider
            models = PROVIDER_MODELS.get(provider, [])
            self.query_one("#sel_model", Select).set_options([(m, m) for m in models])
            if models:
                self.query_one("#sel_model", Select).value = models[0]
                self.app.state["model"] = models[0]
            self.query_one("#inp_key", Input).value = ""
            self._load_saved_key()
        elif sel_id == "sel_model":
            self.app.state["model"] = str(event.value)
        elif sel_id == "sel_preferred_ai":
            self.app.state["preferred_ai"] = str(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        self.app.state["mode"] = "high_quality" if event.value else "fast"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            if len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            else:
                self.app.exit()
        elif event.button.id == "btn_start":
            key = self.query_one("#inp_key", Input).value.strip()
            if not key:
                self.notify("API key is required.", severity="error")
                return
            self.app.state["api_key"] = key
            config = load_config()
            config[PROVIDER_KEYS.get(self.app.state["provider"], "")] = key
            config["last_provider"] = self.app.state["provider"]
            config["last_model"] = self.app.state["model"]
            config["last_mode"] = self.app.state["mode"]
            config["preferred_ai"] = self.app.state.get("preferred_ai", "Claude")
            save_config(config)
            self.app.push_screen(ProgressScreen())


class ProgressScreen(Screen):
    BINDINGS = [Binding("ctrl+c", "cancel_scan", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Scanning and generating prompt...", id="progress_label"),
            ProgressBar(total=100, show_eta=False, id="prog_bar"),
            RichLog(id="scan_log", wrap=True, highlight=True),
            id="progress_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._worker = self.run_worker(self._run_scan(), exclusive=True)

    def action_cancel_scan(self) -> None:
        if hasattr(self, "_worker"):
            self._worker.cancel()
        self.app.exit()

    async def _run_scan(self) -> None:
        log = self.query_one("#scan_log", RichLog)
        prog = self.query_one("#prog_bar", ProgressBar)
        lbl = self.query_one("#progress_label", Label)
        state = self.app.state
        client: Optional[LLMClient] = None

        try:
            client = LLMClient(state["provider"], state["api_key"], state["model"], state["mode"])
            log.write(f"[bold]Provider:[/bold] {state['provider']} / [bold]Model:[/bold] {state['model']}")
            log.write(f"[bold]Scanning:[/bold] {state['path']}")

            scanner = ProjectScanner()
            tree, files = await scanner.scan(state["path"], log)

            total_files = len(files)
            binary_count = sum(1 for f in files if f.get("is_binary"))
            skipped_count = sum(1 for f in files if f.get("skipped"))
            analyzable = total_files - binary_count - skipped_count

            log.write(
                f"Found [bold]{total_files}[/bold] files "
                f"([green]{analyzable}[/green] analyzable, "
                f"[dim]{binary_count} binary, {skipped_count} skipped[/dim])"
            )
            prog.advance(5)

            if total_files > 0:
                file_step = 70.0 / total_files
            else:
                file_step = 0

            done_count = 0

            def on_file_progress(done: int, total: int) -> None:
                nonlocal done_count
                done_count = done
                prog.advance(file_step)
                lbl.update(f"Analyzing files... [{done}/{total}]")

            log.write(f"[bold]Analyzing [green]{analyzable}[/green] text files...[/bold]")
            analyzer = FileAnalyzer(client, log)
            file_summaries = await analyzer.analyze(files, on_file_progress)

            if not files:
                prog.advance(70)

            lbl.update("Building final prompt...")
            log.write("[bold]Building AI-ready context document...[/bold]")
            builder = PromptBuilder()
            final_output = await builder.build(tree, file_summaries, client, log, state["path"])

            state["output"] = final_output
            state["output_dir"] = state["path"]
            state["file_stats"] = {
                "total": total_files,
                "analyzed": analyzable,
                "binary": binary_count,
                "skipped": skipped_count,
            }
            prog.advance(25)
            log.write("[bold green]Complete! Generating output screen...[/bold green]")
            await asyncio.sleep(0.3)
            self.app.push_screen(OutputScreen())

        except asyncio.CancelledError:
            log.write("[yellow]Scan cancelled.[/yellow]")
        except Exception as e:
            log.write(f"[bold red]Error: {type(e).__name__}: {e}[/bold red]")
            lbl.update(f"Failed: {type(e).__name__}")
            self.notify(str(e), severity="error", timeout=10)
        finally:
            if client:
                await client.close()


class OutputScreen(Screen):
    BINDINGS = [
        Binding("ctrl+s", "save_file", "Save"),
        Binding("ctrl+c", "copy_output", "Copy"),
    ]

    def compose(self) -> ComposeResult:
        stats = self.app.state.get("file_stats", {})
        stats_text = (
            f"Files: {stats.get('total', 0)} total | "
            f"{stats.get('analyzed', 0)} analyzed | "
            f"{stats.get('binary', 0)} binary | "
            f"{stats.get('skipped', 0)} skipped"
        ) if stats else ""

        out = self.app.state.get("output", "")
        token_est = estimate_tokens(out)

        preferred_ai = self.app.state.get("preferred_ai", "Claude")

        ai_buttons = [Label("Open with AI:", id="ai_open_label")]
        for ai_name in AI_BROWSER_SERVICES:
            variant = "primary" if ai_name == preferred_ai else "default"
            ai_buttons.append(
                Button(ai_name, id=f"btn_ai_{ai_name.lower().replace(' ', '_')}", variant=variant, classes="ai_btn")
            )

        yield Header()
        yield Vertical(
            Static(stats_text, id="stats_bar"),
            Static(f"Estimated tokens: ~{token_est:,}", id="token_label"),
            ScrollableContainer(
                Static(id="output_text", markup=False),
                id="scroll_area",
            ),
            Vertical(
                Horizontal(*ai_buttons, id="ai_open_row"),
                Horizontal(
                    Button("Save to File", variant="success", id="btn_save"),
                    Button("Copy to Clipboard", variant="default", id="btn_copy"),
                    Button("Save & Open Preferred AI", variant="warning", id="btn_save_open"),
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
        self.query_one("#output_text", Static).update(out)

    def action_save_file(self) -> None:
        self._save(self.app.state.get("output", ""))

    def action_copy_output(self) -> None:
        self._do_copy(self.app.state.get("output", ""))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        out = self.app.state.get("output", "")
        btn_id = event.button.id or ""

        if btn_id == "btn_save":
            self._save(out)
        elif btn_id == "btn_copy":
            self._do_copy(out)
        elif btn_id == "btn_save_open":
            saved_path = self._save(out, notify=False)
            preferred_ai = self.app.state.get("preferred_ai", "Claude")
            self._open_ai_browser(preferred_ai, out, saved_path)
        elif btn_id == "btn_exit":
            self.app.exit()
        elif btn_id.startswith("btn_ai_"):
            ai_label = btn_id[len("btn_ai_"):]
            matched = next(
                (name for name in AI_BROWSER_SERVICES
                 if name.lower().replace(" ", "_") == ai_label),
                None
            )
            if matched:
                self._open_ai_browser(matched, out)

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
            msg = f"Opened {ai_name} in browser."
            if copied:
                msg += " Prompt copied to clipboard — paste it!"
            elif saved_path:
                msg += f" Open {saved_path} to copy the prompt."
            else:
                msg += " Use Save to File to get the prompt."
            self.notify(msg, severity="information", timeout=8)
        except Exception as e:
            self.notify(f"Could not open browser: {e}", severity="error")


class pxForgeApp(App):
    TITLE = "pxForge — AI-Ready Project Context Generator"
    CSS = APP_CSS
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, start_path: Optional[str] = None) -> None:
        super().__init__()
        self.start_path = start_path
        resolved = start_path or str(Path.cwd())
        config = load_config()
        saved_provider = config.get("last_provider", "Anthropic (Claude)")
        if saved_provider not in PROVIDER_MODELS:
            saved_provider = "OpenAI"
        saved_model = config.get("last_model", PROVIDER_MODELS[saved_provider][0])
        if saved_model not in PROVIDER_MODELS.get(saved_provider, []):
            saved_model = PROVIDER_MODELS[saved_provider][0]
        preferred_ai = config.get("preferred_ai", "Claude")
        if preferred_ai not in AI_BROWSER_SERVICES:
            preferred_ai = "Claude"
        self.state: Dict[str, Any] = {
            "path": resolved,
            "output_dir": resolved,
            "provider": saved_provider,
            "api_key": "",
            "model": saved_model,
            "mode": config.get("last_mode", "fast"),
            "output": "",
            "preferred_ai": preferred_ai,
            "file_stats": {},
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
