import os
import sys
import json
import stat
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import httpx
from textual.app import App, ComposeResult, Screen
from textual.widgets import (
    Header, Footer, DirectoryTree, Input, Select, Switch, Label,
    ProgressBar, RichLog, Button, Static
)
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical

CONFIG_DIR = Path.home() / ".pxforge"
CONFIG_FILE = CONFIG_DIR / "config.json"
BIN_DIR = Path.home() / ".local" / "bin"
SCRIPT_PATH = Path(__file__).resolve()


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

    print(f"✓ Installed: {wrapper}")
    print(f"✓ PATH entry added to: {rc_file}")
    print(f"\nRestart your shell or run:  source {rc_file}")
    print("Then use:  pxforge            # scans current directory")
    print("           pxforge /some/path # scans given path")

IGNORED_DIRS = {
    '.git', 'node_modules', 'dist', 'build', '__pycache__',
    '.venv', 'env', 'venv', '.next', '.nuxt', 'coverage', '.cache'
}
IGNORED_EXT = {
    '.pyc', '.pyo', '.exe', '.dll', '.so', '.dylib', '.whl',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.bin', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
    '.pdf', '.mp3', '.mp4', '.avi', '.lock', '.bmp', '.webp',
    '.tiff', '.wav', '.ogg', '.flac', '.ttf', '.woff', '.woff2', '.eot'
}
BINARY_MARKERS = {b'\x7fELF', b'\x89PNG', b'\xff\xd8\xff\xe0', b'%PDF-1.', b'PK\x03\x04'}
CHUNK_SIZE = 4000

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
    "OpenAI": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "Anthropic (Claude)": [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-3-5-sonnet-20241022",
    ],
    "Groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    "OpenRouter": [
        "meta-llama/llama-3.3-70b-instruct",
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash-001",
    ],
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

/* ── Dir Select ─────────────────────────────────────── */

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

/* ── Settings ───────────────────────────────────────── */

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

/* ── Progress ───────────────────────────────────────── */

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

/* ── Output ─────────────────────────────────────────── */

#output_outer {
    width: 100%;
    height: 1fr;
    padding: 0 2;
}

#scroll_area {
    height: 100%;
    border: round $primary;
    background: $surface-darken-1;
}

#output_text {
    padding: 1 2;
}

#output_buttons {
    height: 3;
    align: right middle;
    padding: 0 2;
    margin-top: 1;
    margin-bottom: 1;
}

Button {
    margin-left: 1;
}
"""


def load_config() -> Dict[str, str]:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(config: Dict[str, str]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


API_CONCURRENCY = 8

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

    def __init__(self, provider: str, api_key: str, model: str, mode: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.max_tokens = 4000 if mode == "high_quality" else 2000
        self._http = httpx.AsyncClient(timeout=120.0)

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> Dict[str, str]:
        base = {"Content-Type": "application/json"}
        if self.provider == "Anthropic (Claude)":
            return {**base, "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        if self.provider == "OpenRouter":
            return {**base, "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "pxforge", "X-Title": "pxForge"}
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
            return blocks[0].get("text", "") if blocks else ""
        choices = data.get("choices", [])
        return choices[0].get("message", {}).get("content", "") if choices else ""

    async def generate(self, prompt: str, system: str = SYSTEM_ANALYST) -> str:
        url = self.URLS.get(self.provider, "")
        if not url:
            raise ValueError(f"Unknown provider: {self.provider}")
        resp = await self._http.post(url, headers=self._headers(), json=self._payload(prompt, system))
        resp.raise_for_status()
        return self._extract(resp.json())


def _listdir_filtered(dirpath: str) -> List[Tuple[str, str, bool]]:
    try:
        entries = sorted(os.scandir(dirpath), key=lambda e: e.name)
    except PermissionError:
        return []
    result = []
    for entry in entries:
        if entry.name in IGNORED_DIRS:
            continue
        if entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in IGNORED_EXT:
            continue
        result.append((entry.name, entry.path, entry.is_dir(follow_symlinks=False)))
    return result


def _read_file_sync(filepath: str) -> Optional[Dict[str, Any]]:
    ext = Path(filepath).suffix.lower()
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
        if any(header.startswith(m) for m in BINARY_MARKERS):
            return {"path": filepath, "type": ext, "is_binary": True, "content": None}
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"path": filepath, "type": ext, "is_binary": False, "content": content}
    except Exception:
        return None


class ProjectScanner:
    async def scan(self, path: str, log: RichLog) -> Tuple[str, List[Dict[str, Any]]]:
        log.write(f"Walking directory tree...")
        tree_lines, files = await self._walk(path, "")
        return "\n".join(tree_lines), files

    async def _walk(self, dirpath: str, prefix: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        entries = await asyncio.to_thread(_listdir_filtered, dirpath)
        tree_lines: List[str] = []
        file_paths: List[str] = []
        subdir_tasks: List[Tuple[int, Any]] = []

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
                *[self._walk(full_path, child_prefix) for _, full_path, child_prefix in subdir_tasks]
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
        self._sem = asyncio.Semaphore(API_CONCURRENCY)

    async def analyze(
        self,
        files: List[Dict[str, Any]],
        on_progress: Any,
    ) -> Dict[str, str]:
        total = len(files)
        results: Dict[str, Optional[str]] = {f["path"]: None for f in files}

        async def process(f: Dict[str, Any], idx: int) -> None:
            name = os.path.basename(f["path"])
            if f["is_binary"] or f["content"] is None:
                results[f["path"]] = f"[{f['type'].upper() or 'BINARY'}] {f['path']}"
                on_progress(idx + 1, total)
                return

            content = f["content"]
            chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]

            async def analyze_chunk(ci: int, chunk: str) -> str:
                prompt = (
                    "Analyze this code/text. Concisely extract:\n"
                    "- Purpose\n- Key functions/classes\n- Dependencies\n- Important logic\n\n"
                    f"Content:\n{chunk}"
                )
                async with self._sem:
                    self.log.write(f"  [{idx+1}/{total}] {name} — chunk {ci+1}/{len(chunks)}")
                    try:
                        return await self.client.generate(prompt, system=SYSTEM_ANALYST)
                    except Exception as e:
                        self.log.write(f"  [!] {name} chunk {ci+1}: {e}")
                        return ""

            summaries = [s for s in await asyncio.gather(
                *[analyze_chunk(ci, chunk) for ci, chunk in enumerate(chunks)]
            ) if s]

            if not summaries:
                results[f["path"]] = f"[NO CONTENT] {f['path']}"
            elif len(summaries) == 1:
                results[f["path"]] = summaries[0]
            else:
                self.log.write(f"  Merging {len(summaries)} chunks for {name}")
                merge_prompt = (
                    "Merge these analysis chunks into one coherent summary. "
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
    MAX_CTX_CHARS = 80_000

    async def build(
        self,
        tree: str,
        file_summaries: Dict[str, str],
        client: LLMClient,
        log: RichLog,
    ) -> str:
        log.write("Generating project summary...")
        ctx_lines = [
            f"{os.path.basename(p)}: {s}" for p, s in file_summaries.items()
        ]
        ctx = "\n".join(ctx_lines)
        if len(ctx) > self.MAX_CTX_CHARS:
            ctx = ctx[:self.MAX_CTX_CHARS] + "\n...[truncated]"

        project_summary = await client.generate(
            "Analyze the project structure and file summaries below. "
            "Write a concise PROJECT SUMMARY covering: technology stack, architecture, and core functionality.\n\n"
            f"Tree:\n{tree}\n\nFiles:\n{ctx}",
            system=SYSTEM_ARCHITECT,
        )
        key_sections: List[str] = []
        other_lines: List[str] = []
        for p, s in file_summaries.items():
            if s.startswith("["):
                other_lines.append(f"{p}: {s}")
            else:
                key_sections.append(f"### {p}\n{s}")

        body = (
            f"# PROJECT SUMMARY\n{project_summary}\n\n"
            f"# DIRECTORY STRUCTURE\n```\n{tree}\n```\n\n"
            "# KEY FILE SUMMARIES\n" + "\n\n".join(key_sections)
        )
        if other_lines:
            body += "\n\n# OTHER FILES\n" + "\n".join(other_lines)

        log.write("Building final AI-ready prompt...")
        final_prompt_input = body if len(body) <= self.MAX_CTX_CHARS else body[:self.MAX_CTX_CHARS] + "\n...[truncated]"
        final_prompt = await client.generate(
            "Generate a comprehensive, AI-ready system prompt for a developer assistant "
            "working on this project. Base it on the context below.\n\n" + final_prompt_input,
            system=SYSTEM_PROMPT_ENGINEER,
        )
        return body + f"\n\n# AI SYSTEM PROMPT\n{final_prompt}"


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
        providers = [(p, p) for p in PROVIDER_MODELS]
        current_provider = self.app.state["provider"]
        models = [(m, m) for m in PROVIDER_MODELS[current_provider]]
        scan_path = self.app.state["path"]
        yield Header()
        yield ScrollableContainer(
            Vertical(
                Label(f"Scanning: {scan_path}", id="lbl_path"),
                Label("Provider:"),
                Select(providers, value=current_provider, id="sel_provider"),
                Label("API Key:"),
                Input(placeholder="Enter API key (or leave blank to use saved/env)", id="inp_key", password=True),
                Label("Model:"),
                Select(models, value=PROVIDER_MODELS[current_provider][0], id="sel_model"),
                Label("Mode:"),
                Horizontal(
                    Label("Fast"),
                    Switch(value=self.app.state["mode"] == "high_quality", id="sw_mode"),
                    Label("High Quality"),
                    id="mode_row",
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
        key = config.get(PROVIDER_KEYS.get(provider, ""), "")
        if not key:
            key = os.getenv(PROVIDER_ENV.get(provider, ""), "")
        if key:
            self.query_one("#inp_key", Input).value = key

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel_provider":
            provider = str(event.value)
            self.app.state["provider"] = provider
            models = PROVIDER_MODELS.get(provider, [])
            self.query_one("#sel_model", Select).set_options([(m, m) for m in models])
            if models:
                self.query_one("#sel_model", Select).value = models[0]
                self.app.state["model"] = models[0]
            self.query_one("#inp_key", Input).value = ""
            self._load_saved_key()
        elif event.select.id == "sel_model":
            self.app.state["model"] = str(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        self.app.state["mode"] = "high_quality" if event.value else "fast"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            if self.app.screen_stack and len(self.app.screen_stack) > 1:
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
            save_config(config)
            self.app.push_screen(ProgressScreen())


class ProgressScreen(Screen):
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
        self.run_worker(self._run_scan(), exclusive=True)

    async def _run_scan(self) -> None:
        log = self.query_one("#scan_log", RichLog)
        prog = self.query_one("#prog_bar", ProgressBar)
        state = self.app.state

        client = LLMClient(state["provider"], state["api_key"], state["model"], state["mode"])

        log.write(f"[bold]Scanning:[/bold] {state['path']}")
        scanner = ProjectScanner()
        tree, files = await scanner.scan(state["path"], log)
        log.write(f"Found [bold]{len(files)}[/bold] files to process.")
        prog.advance(5)

        analyzable = [f for f in files if not f["is_binary"] and f["content"] is not None]

        if analyzable:
            file_progress_budget = 75.0

            def on_file_progress(done: int, total: int) -> None:
                prog.advance(file_progress_budget / total)

            analyzer = FileAnalyzer(client, log)
            file_summaries = await analyzer.analyze(files, on_file_progress)
        else:
            log.write("No text files to analyze.")
            prog.advance(75)
            file_summaries = {
                f["path"]: f"[{f['type'].upper() or 'BINARY'}] {f['path']}" for f in files
            }

        log.write("Building final prompt...")
        builder = PromptBuilder()
        final_output = await builder.build(tree, file_summaries, client, log)

        state["output"] = final_output
        state["output_dir"] = state["path"]
        prog.advance(20)
        await client.close()

        log.write("[bold green]✓ Complete.[/bold green]")
        await asyncio.sleep(0.6)
        self.app.push_screen(OutputScreen())


class OutputScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            ScrollableContainer(
                Static(id="output_text", markup=False),
                id="scroll_area",
            ),
            id="output_outer",
        )
        yield Horizontal(
            Button("Save to File", variant="success", id="btn_save"),
            Button("Copy to Clipboard", id="btn_copy"),
            Button("Exit", variant="error", id="btn_exit"),
            id="output_buttons",
        )
        yield Footer()

    def on_mount(self) -> None:
        out = self.app.state.get("output", "No output generated.")
        self.query_one("#output_text", Static).update(out)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        out = self.app.state.get("output", "")
        if event.button.id == "btn_save":
            self._save(out)
        elif event.button.id == "btn_copy":
            self._copy(out)
        elif event.button.id == "btn_exit":
            self.app.exit()

    def _save(self, content: str) -> None:
        try:
            out_dir = Path(self.app.state.get("output_dir", "."))
            out_path = out_dir / "pxforge_output.md"
            out_path.write_text(content, encoding="utf-8")
            self.notify(f"Saved to {out_path}", severity="information")
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")

    def _copy(self, content: str) -> None:
        import subprocess
        try:
            if sys.platform == "darwin":
                proc = subprocess.run(["pbcopy"], input=content, text=True)
            elif sys.platform == "win32":
                proc = subprocess.run(["clip"], input=content, text=True, shell=True)
            else:
                proc = subprocess.run(["xclip", "-selection", "clipboard"], input=content, text=True)
            if proc.returncode == 0:
                self.notify("Copied to clipboard.", severity="information")
            else:
                self.notify("Clipboard copy failed.", severity="error")
        except FileNotFoundError:
            self.notify("Clipboard tool not found (install xclip on Linux).", severity="error")
        except Exception as e:
            self.notify(f"Clipboard error: {e}", severity="error")


class pxForgeApp(App):
    TITLE = "pxForge"
    CSS = APP_CSS
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, start_path: Optional[str] = None) -> None:
        super().__init__()
        self.start_path = start_path
        resolved = start_path or str(Path.cwd())
        self.state: Dict[str, Any] = {
            "path": resolved,
            "output_dir": resolved,
            "provider": "OpenAI",
            "api_key": "",
            "model": "gpt-4o",
            "mode": "fast",
            "output": "",
        }

    def on_mount(self) -> None:
        if self.start_path:
            self.push_screen(SettingsScreen())
        else:
            self.push_screen(DirSelectScreen())


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] in ("install",):
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
