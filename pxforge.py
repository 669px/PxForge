import os
import sys
import json
import stat
import asyncio
import random
import fnmatch
import webbrowser
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import httpx
from textual.app import App, ComposeResult, Screen
from textual.widgets import (
    Header, Footer, DirectoryTree, Input, Select, Switch, Label,
    ProgressBar, RichLog, Button, Static,
)
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.binding import Binding

CONFIG_DIR = Path.home() / ".pxforge"
CONFIG_FILE = CONFIG_DIR / "config.json"
BIN_DIR = Path.home() / ".local" / "bin"
SCRIPT_PATH = Path(__file__).resolve()

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_PROVIDER = "Ollama (Local)"

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
    '.idea', '.vscode', 'target', 'out', '.gradle',
    '.mypy_cache', '.pytest_cache', '.ruff_cache', 'vendor',
    '.tox', '.nox', '.eggs', '.egg-info', 'pip-wheel-metadata',
    'htmlcov', 'site-packages', 'lib64', 'parts', 'sdist', 'wheels',
    'celerybeat-schedule', '.scrapy', '.spyderproject',
    '.spyproject', '.ropeproject', '.dmypy.json',
    '.pyre', '.pytype', 'cython_debug', '__pypackages__',
    '.terraform', '.serverless', '.nyc_output', '.hypothesis',
    '.coverage', '.serverless_nextjs', '.serverless_nuxt', '.vuepress',
    '.docusaurus', '.gatsby', '.gridsome', '.sapper', '.svelte-kit',
    '.output', '.nitro', '.wrangler', '.vercel', '.netlify',
    '.now', '.heroku', '.fly', '.render', '.k8s', '.kubernetes',
    '.helm', '.chart', '.argo', '.tekton', '.jenkins', '.travis',
    '.circleci', '.appveyor', '.codecov', '.coveralls', '.snyk',
    '.dependabot', '.renovate', '.pre-commit', '.husky',
    '.lint-staged', '.commitlint', '.semantic-release', '.changeset',
    '.buildkite', '.drone', '.semaphore', '.wercker', '.codeship',
    '.shippable', '.snap', '.snapcraft', '.flatpak', '.appimage',
    '.deb', '.rpm', '.pkg', '.msi', '.dmg', '.unity', '.unreal',
    '.godot', '.cocos', '.defold', '.love', '.panda3d', '.raylib',
    '.sfml', '.sdl', '.glfw', '.glew', '.glm', '.stb', '.imgui',
    '.implot', '.imnodes', '.imguizmo', '.nuklear', '.microui',
    '.raygui', '.cimgui', '.imfiledialog', '.imgui_memory_editor',
    '.imgui_club', '.imgui_markdown', '.imgui_tex_inspect',
    '.imgui_toggle', '.imgui_knobs', '.imgui_color_text_edit',
    '.imgui_color_picker', '.imgui_color_gradient', '.imgui_color_palette',
    '.imgui_color_wheel', '.imgui_color_box', '.imgui_color_button',
    '.imgui_color_popup', '.imgui_color_tooltip', '.imgui_color_picker_flags',
    '.imgui_color_edit_flags', '.imgui_color_display_flags',
    '.imgui_color_input_flags', '.imgui_color_button_flags',
    '.imgui_color_flags', '.imgui_color', '.imgui', '.implot',
    '.imnodes', '.imguizmo', '.imfd', '.ime', '.imgui_markdown',
    '.imgui_tex_inspect', '.imgui_toggle', '.imgui_knobs',
    '.imgui_color_text_edit', '.imgui_color_picker', '.imgui_color_gradient',
    '.imgui_color_palette', '.imgui_color_wheel', '.imgui_color_box',
    '.imgui_color_button', '.imgui_color_popup', '.imgui_color_tooltip',
    '.imgui_color_picker_flags', '.imgui_color_edit_flags',
    '.imgui_color_display_flags', '.imgui_color_input_flags',
    '.imgui_color_button_flags', '.imgui_color_flags', '.imgui_color',
    '.env', '.env.local', '.env.development', '.env.production',
    '.env.test', '.env.staging', '.env.example', '.env.sample',
    '.env.template', '.env.backup', '.env.bak', '.env.old',
    '.env.previous', '.env.orig', '.env.rej', '.env.dist',
    '.env.dev', '.env.prod', '.env.ci', '.env.docker',
    '.env.kubernetes', '.env.k8s', '.env.helm', '.env.chart',
    '.env.argo', '.env.tekton', '.env.jenkins', '.env.travis',
    '.env.circleci', '.env.appveyor', '.env.codecov', '.env.coveralls',
    '.env.snyk', '.env.dependabot', '.env.renovate', '.env.pre-commit',
    '.env.husky', '.env.lint-staged', '.env.commitlint',
    '.env.semantic-release', '.env.changeset', '.env.buildkite',
    '.env.drone', '.env.semaphore', '.env.wercker', '.env.codeship',
    '.env.shippable', '.env.snap', '.env.snapcraft', '.env.flatpak',
    '.env.appimage', '.env.deb', '.env.rpm', '.env.pkg', '.env.msi',
    '.env.dmg', '.env.unity', '.env.unreal', '.env.godot', '.env.cocos',
    '.env.defold', '.env.love', '.env.panda3d', '.env.raylib',
    '.env.sfml', '.env.sdl', '.env.glfw', '.env.glew', '.env.glm',
    '.env.stb', '.env.imgui', '.env.implot', '.env.imnodes',
    '.env.imguizmo', '.env.nuklear', '.env.microui', '.env.raygui',
    '.env.cimgui', '.env.imfiledialog', '.env.imgui_memory_editor',
    '.env.imgui_club', '.env.imgui_markdown', '.env.imgui_tex_inspect',
    '.env.imgui_toggle', '.env.imgui_knobs', '.env.imgui_color_text_edit',
    '.env.imgui_color_picker', '.env.imgui_color_gradient',
    '.env.imgui_color_palette', '.env.imgui_color_wheel',
    '.env.imgui_color_box', '.env.imgui_color_button',
    '.env.imgui_color_popup', '.env.imgui_color_tooltip',
    '.env.imgui_color_picker_flags', '.env.imgui_color_edit_flags',
    '.env.imgui_color_display_flags', '.env.imgui_color_input_flags',
    '.env.imgui_color_button_flags', '.env.imgui_color_flags',
    '.env.imgui_color', '.env.imgui', '.env.implot', '.env.imnodes',
    '.env.imguizmo', '.env.imfd', '.env.ime', '.env.imgui_markdown',
    '.env.imgui_tex_inspect', '.env.imgui_toggle', '.env.imgui_knobs',
    '.env.imgui_color_text_edit', '.env.imgui_color_picker',
    '.env.imgui_color_gradient', '.env.imgui_color_palette',
    '.env.imgui_color_wheel', '.env.imgui_color_box',
    '.env.imgui_color_button', '.env.imgui_color_popup',
    '.env.imgui_color_tooltip', '.env.imgui_color_picker_flags',
    '.env.imgui_color_edit_flags', '.env.imgui_color_display_flags',
    '.env.imgui_color_input_flags', '.env.imgui_color_button_flags',
    '.env.imgui_color_flags', '.env.imgui_color', '.env',
}
IGNORED_EXT = {
    '.pyc', '.pyo', '.exe', '.dll', '.so', '.dylib', '.whl',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.bin', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
    '.pdf', '.mp3', '.mp4', '.avi', '.lock', '.bmp', '.webp',
    '.tiff', '.wav', '.ogg', '.flac', '.ttf', '.woff', '.woff2', '.eot',
    '.class', '.o', '.a', '.lib', '.pdb', '.map',
    '.suo', '.user', '.orig', '.rej',
}
BINARY_MARKERS = (
    b'\x7fELF', b'\x89PNG', b'\xff\xd8\xff',
    b'%PDF-1.', b'PK\x03\x04', b'GIF8',
)
CHUNK_SIZE = 6000
MIN_CONTENT_LEN = 20
MAX_FILE_SIZE_BYTES = 500_000

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


async def fetch_ollama_models() -> Tuple[List[str], str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
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
    def __init__(self, base_path: str):
        self.base = Path(base_path).resolve()
        self.patterns = []
        self.negations = []
        gi = self.base / ".gitignore"
        if gi.exists():
            with open(gi, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if line.startswith("!"):
                            self.negations.append(line[1:].rstrip("/"))
                        else:
                            self.patterns.append(line.rstrip("/"))

    def is_ignored(self, path: str) -> bool:
        try:
            rel = Path(path).resolve().relative_to(self.base)
        except ValueError:
            return False
        rel_str = str(rel).replace(os.sep, "/")
        rel_dir = rel_str + "/"
        parts = rel.parts

        for pat in self.patterns:
            if self._match(rel_str, rel_dir, pat, parts):
                for neg in self.negations:
                    if self._match(rel_str, rel_dir, neg, parts):
                        break
                else:
                    return True
        return False

    def _match(self, rel_str, rel_dir, pat, parts):
        if pat.startswith("/"):
            p = pat[1:]
            if fnmatch.fnmatch(rel_str, p) or fnmatch.fnmatch(rel_dir, p + "/"):
                return True
        else:
            if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(rel_dir, pat + "/"):
                return True
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if fnmatch.fnmatch(sub, pat) or fnmatch.fnmatch(sub + "/", pat + "/"):
                    return True
        return False


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
    height: 1;
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
    height: 1;
    color: $text-muted;
    margin-bottom: 1;
    padding: 0 1;
}
#dir_buttons {
    height: 3;
    align: right middle;
    margin-top: 1;
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
    height: 1;
    color: $accent;
    text-style: bold italic;
    margin-bottom: 1;
    padding: 0 1;
    border-left: thick $accent;
}
#settings_inner Label {
    height: 1;
    margin-top: 1;
    color: $text-muted;
    text-style: bold;
}
#settings_inner Select {
    margin-bottom: 0;
}
#settings_inner Input {
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
#ollama_status_row {
    height: 2;
    align: left middle;
    margin-top: 1;
    padding: 0 1;
}
#ollama_status_label {
    height: 2;
    width: 1fr;
    color: $text-muted;
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

#output_section {
    width: 100%;
    height: 100%;
}
#stats_bar {
    height: 1;
    color: $text-muted;
    padding: 0 2;
}
#token_label {
    height: 1;
    color: $warning;
    padding: 0 2;
    text-style: italic;
    margin-bottom: 1;
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
#bottom_panel {
    height: auto;
    width: 100%;
    border-top: solid $primary-darken-1;
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
    color: $text-muted;
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
Button {
    margin-left: 1;
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


SYSTEM_ANALYST = """You are a senior code analyst. Analyze the provided file and extract:
- Purpose: what this file does
- Key symbols: functions, classes, variables that matter
- Dependencies: imports, external libraries, internal modules it relies on
- Logic: non-obvious patterns, algorithms, or architectural decisions
Rules:
- Be concise. Use bullets.
- No line numbers.
- Skip obvious structural observations.
- For config/data files, describe what they configure and which values are critical.
"""

SYSTEM_ARCHITECT = """You are a senior software architect. Synthesize the directory tree and file analyses into a project overview.
Cover:
1. Technology stack (languages, frameworks, major libraries)
2. Architecture (pattern, how components interact)
3. Core functionality (what this project does)
4. Entry points and data flow
Rules:
- 3-5 paragraphs max.
- Direct technical prose. No fluff.
- Focus on what a new developer needs to be productive immediately.
"""

SYSTEM_PROMPT_ENGINEER = """You are an expert prompt engineer. Generate a system prompt for an AI coding assistant working on this specific project.
The prompt must:
1. Define the AI's role as an expert collaborator on this codebase
2. Summarize the project's purpose, stack, and architecture in 2-3 sentences
3. List key conventions (naming, structure, idioms) the AI must follow
4. State what the AI should always do (use existing utilities, follow patterns, write idiomatic code)
5. State what the AI must never do (add dependencies without approval, break interfaces, duplicate utilities)
6. Include the directory layout so the AI knows where files live
Rules:
- Second person ("You are...", "You must...", "Never...").
- Specific to this project. No generic advice.
- Immediately usable in Cursor, Claude, Copilot Chat, etc.
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
        self.max_tokens = 4096 if mode == "high_quality" else 2048
        timeout = 300.0 if provider == OLLAMA_PROVIDER else 180.0
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> Dict[str, str]:
        base = {"Content-Type": "application/json"}
        if self.provider == "Anthropic (Claude)":
            return {**base, "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        if self.provider == OLLAMA_PROVIDER:
            return {**base, "Authorization": "Bearer ollama"}
        if self.provider == "OpenRouter":
            return {**base, "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://github.com/669px/pxforge", "X-Title": "pxForge"}
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
            except Exception as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(1)
        raise last_exc or RuntimeError("Max retries exceeded")


def _read_file_sync(filepath: str) -> Optional[Dict[str, Any]]:
    ext = Path(filepath).suffix.lower()
    try:
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE_BYTES:
            return {
                "path": filepath, "type": ext, "is_binary": False,
                "content": None, "skipped": True, "reason": f"too large ({size // 1024}KB)",
            }
        with open(filepath, "rb") as f:
            header = f.read(8192)
            if any(header.startswith(m) for m in BINARY_MARKERS) or b'\x00' in header:
                return {"path": filepath, "type": ext, "is_binary": True, "content": None, "skipped": False}
            if size <= 8192:
                raw = header
            else:
                raw = header + f.read()
        content = raw.decode("utf-8", errors="ignore")
        return {"path": filepath, "type": ext, "is_binary": False, "content": content, "skipped": False}
    except PermissionError:
        return {
            "path": filepath, "type": ext, "is_binary": False,
            "content": None, "skipped": True, "reason": "permission denied",
        }
    except Exception:
        return None


class ProjectScanner:
    async def scan(self, path: str, log: RichLog) -> Tuple[str, List[Dict[str, Any]]]:
        log.write("[bold cyan]Walking directory tree...[/bold cyan]")
        tree, file_paths = await asyncio.to_thread(self._build_tree, path)
        log.write(f"[bold cyan]Reading {len(file_paths)} files...[/bold cyan]")
        files = await self._read_files(file_paths)
        return tree, files

    def _build_tree(self, path: str) -> Tuple[str, List[str]]:
        base = Path(path).resolve()
        gitignore = GitignoreParser(str(base))
        tree_lines = []
        file_paths = []

        def walk(dirpath: str, prefix: str):
            try:
                entries = sorted(os.scandir(dirpath), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return

            filtered = []
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in IGNORED_DIRS:
                        continue
                    if gitignore.is_ignored(entry.path):
                        continue
                    filtered.append(entry)
                elif entry.is_file(follow_symlinks=False):
                    ext = Path(entry.name).suffix.lower()
                    if ext in IGNORED_EXT:
                        continue
                    if gitignore.is_ignored(entry.path):
                        continue
                    filtered.append(entry)

            for i, entry in enumerate(filtered):
                is_last = i == len(filtered) - 1
                connector = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{connector}{entry.name}")
                if entry.is_dir():
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    walk(entry.path, child_prefix)
                else:
                    file_paths.append(entry.path)

        walk(str(base), "")
        return "\n".join(tree_lines), file_paths

    async def _read_files(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        sem = asyncio.Semaphore(50)

        async def read_one(fp: str) -> Optional[Dict[str, Any]]:
            async with sem:
                return await asyncio.to_thread(_read_file_sync, fp)

        results = await asyncio.gather(*[read_one(fp) for fp in file_paths])
        return [r for r in results if r is not None]


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
                results[f["path"]] = f"[SKIPPED:{reason}]"
                on_progress(idx + 1, total)
                return

            if f["is_binary"] or len(content.strip()) < MIN_CONTENT_LEN:
                label = "BINARY" if f["is_binary"] else "SKIPPED:empty"
                results[f["path"]] = f"[{label}]"
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
                        self.log.write(f"  [red][!] {name}: {e}[/red]")
                        return ""

            summaries = [s for s in await asyncio.gather(
                *[analyze_chunk(ci, chunk) for ci, chunk in enumerate(chunks)]
            ) if s.strip()]

            if not summaries:
                results[f["path"]] = "[FAILED]"
            elif len(summaries) == 1:
                results[f["path"]] = summaries[0]
            else:
                self.log.write(f"  [yellow]Merging {len(summaries)} chunks for {name}[/yellow]")
                merge_prompt = (
                    f"Merge these partial analyses of '{name}' into one coherent summary.\n"
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

        tree_for_summary = tree if len(tree) <= 10_000 else tree[:10_000] + "\n...[tree truncated]"

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

        log.write("[bold cyan]Building AI-ready system prompt...[/bold cyan]")
        ctx_for_prompt = body if len(body) <= self.MAX_CTX_CHARS else body[:self.MAX_CTX_CHARS] + "\n...[truncated]"
        final_prompt = await client.generate(
            "Generate a comprehensive, immediately-usable AI system prompt for a developer assistant "
            "working on this exact project. Be specific to this codebase.\n\n" + ctx_for_prompt,
            system=SYSTEM_PROMPT_ENGINEER,
        )

        stats_comment = (
            f"<!-- pxForge | files analyzed: {len(valid_summaries)} | "
            f"skipped: {len(skipped_summaries)} | "
            f"~{estimate_tokens(body):,} tokens -->"
        )
        return body + f"\n\n# AI SYSTEM PROMPT\n{final_prompt}\n\n{stats_comment}"


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

    def _safe_provider(self) -> str:
        p = self.app.state.get("provider", "")
        return p if p in PROVIDER_MODELS else PROVIDER_NAMES[0]

    def _safe_model(self, provider: str) -> str:
        models = PROVIDER_MODELS.get(provider, [])
        saved = self.app.state.get("model", "")
        return saved if saved in models else (models[0] if models else "")

    def _safe_preferred_ai(self) -> str:
        ai = self.app.state.get("preferred_ai", "Claude")
        return ai if ai in AI_BROWSER_SERVICES else AI_SERVICE_KEYS[0]

    def compose(self) -> ComposeResult:
        provider = self._safe_provider()
        model = self._safe_model(provider)
        preferred_ai = self._safe_preferred_ai()
        scan_path = self.app.state.get("path", str(Path.cwd()))
        is_ollama = provider == OLLAMA_PROVIDER

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
                    placeholder="Not required for Ollama" if is_ollama else "Enter API key (or leave blank to use saved/env)",
                    id="inp_key",
                    password=True,
                    disabled=is_ollama,
                ),
                Label("Model:"),
                Select(
                    [(m, m) for m in (PROVIDER_MODELS[provider] or ["(no models — refresh below)"])],
                    value=model if model else Select.BLANK,
                    id="sel_model",
                ),
                Horizontal(
                    Label("⬤  Checking Ollama...", id="ollama_status_label"),
                    Button("↻ Refresh", id="btn_ollama_refresh", variant="default"),
                    id="ollama_status_row",
                    classes=None if is_ollama else "hidden",
                ),
                Label("Mode:"),
                Horizontal(
                    Label("Fast"),
                    Switch(value=self.app.state.get("mode") == "high_quality", id="sw_mode"),
                    Label("High Quality"),
                    id="mode_row",
                ),
                Label("Preferred AI for viewing output:"),
                Select(
                    [(name, name) for name in AI_SERVICE_KEYS],
                    value=preferred_ai,
                    id="sel_preferred_ai",
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
        if provider == OLLAMA_PROVIDER:
            self.run_worker(self._probe_ollama(), exclusive=False)
        else:
            self._load_saved_key()
            self._hide_ollama_row()

    def _hide_ollama_row(self) -> None:
        try:
            row = self.query_one("#ollama_status_row", Horizontal)
            row.add_class("hidden")
        except Exception:
            pass

    def _show_ollama_row(self) -> None:
        try:
            row = self.query_one("#ollama_status_row", Horizontal)
            row.remove_class("hidden")
        except Exception:
            pass

    async def _probe_ollama(self) -> None:
        self._show_ollama_row()
        try:
            lbl = self.query_one("#ollama_status_label", Label)
            lbl.update("⬤  Connecting to Ollama...")
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
            self._repopulate_model_select(OLLAMA_PROVIDER, models)

    def _load_saved_key(self) -> None:
        provider = self.app.state.get("provider", "")
        config_key = PROVIDER_KEYS.get(provider, "")
        env_key = PROVIDER_ENV.get(provider, "")
        if not config_key and not env_key:
            return
        config = load_config()
        key = (config.get(config_key, "") if config_key else "") or (os.getenv(env_key, "") if env_key else "")
        if key:
            try:
                self.query_one("#inp_key", Input).value = key
            except Exception:
                pass

    def _repopulate_model_select(self, provider: str, models: List[str]) -> None:
        if not models:
            models = ["(no models found)"]
        try:
            sel = self.query_one("#sel_model", Select)
            sel.set_options([(m, m) for m in models])
            sel.value = models[0]
            self.app.state["model"] = models[0]
        except Exception:
            pass

    def _update_model_select(self, provider: str) -> None:
        models = PROVIDER_MODELS.get(provider, [])
        self._repopulate_model_select(provider, models)

    def _toggle_key_input(self, is_ollama: bool) -> None:
        try:
            inp = self.query_one("#inp_key", Input)
            inp.disabled = is_ollama
            inp.placeholder = (
                "Not required for Ollama"
                if is_ollama
                else "Enter API key (or leave blank to use saved/env)"
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
        self.app.state["mode"] = "high_quality" if event.value else "fast"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ollama_refresh":
            self.run_worker(self._probe_ollama(), exclusive=False)
            return

        if event.button.id == "btn_back":
            if len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            else:
                self.app.exit()
            return

        if event.button.id == "btn_start":
            provider = self.app.state.get("provider", "")
            is_ollama = provider == OLLAMA_PROVIDER
            _no_model_sentinels = {"(no models found)", "(no models — refresh below)"}

            if is_ollama:
                model = self.app.state.get("model", "")
                if not model or model in _no_model_sentinels:
                    self.notify(
                        "No Ollama model selected. Pull one first: ollama pull llama3",
                        severity="error",
                    )
                    return
                self.app.state["api_key"] = "ollama"
            else:
                key = self.query_one("#inp_key", Input).value.strip()
                if not key:
                    self.notify("API key is required.", severity="error")
                    return
                self.app.state["api_key"] = key

            config = load_config()
            if not is_ollama:
                config_key = PROVIDER_KEYS.get(provider, "")
                if config_key:
                    config[config_key] = self.app.state["api_key"]
            config["last_provider"] = provider
            config["last_model"] = self.app.state.get("model", "")
            config["last_mode"] = self.app.state.get("mode", "fast")
            config["preferred_ai"] = self.app.state.get("preferred_ai", "Claude")
            save_config(config)

            self.app.push_screen(ProgressScreen())


class ProgressScreen(Screen):
    BINDINGS = [Binding("escape", "cancel_scan", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Initializing...", id="progress_label"),
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
        self.app.pop_screen()

    async def _run_scan(self) -> None:
        log = self.query_one("#scan_log", RichLog)
        prog = self.query_one("#prog_bar", ProgressBar)
        lbl = self.query_one("#progress_label", Label)
        state = self.app.state
        client: Optional[LLMClient] = None
        progress_given = 0

        def advance(amount: float) -> None:
            nonlocal progress_given
            amt = int(amount)
            if amt > 0:
                prog.advance(amt)
                progress_given += amt

        try:
            provider = state["provider"]
            is_ollama = provider == OLLAMA_PROVIDER

            if is_ollama:
                log.write(
                    f"[bold]Provider:[/bold] {provider}  "
                    f"[bold]Model:[/bold] {state['model']}  "
                    f"[dim](local — no API key needed)[/dim]"
                )
            else:
                log.write(f"[bold]Provider:[/bold] {provider}  [bold]Model:[/bold] {state['model']}")

            log.write(f"[bold]Path:[/bold] {state['path']}")

            client = LLMClient(provider, state["api_key"], state["model"], state["mode"])

            lbl.update("Scanning project...")
            scanner = ProjectScanner()
            tree, files = await scanner.scan(state["path"], log)

            total_files = len(files)
            binary_count = sum(1 for f in files if f.get("is_binary"))
            skipped_count = sum(1 for f in files if f.get("skipped"))
            analyzable = total_files - binary_count - skipped_count

            log.write(
                f"Found [bold]{total_files}[/bold] files — "
                f"[green]{analyzable}[/green] analyzable, "
                f"[dim]{binary_count} binary, {skipped_count} skipped[/dim]"
            )

            if is_ollama and analyzable > 10:
                log.write(
                    f"[yellow]⚠  Ollama processes sequentially (concurrency=2). "
                    f"{analyzable} files may take a while.[/yellow]"
                )

            advance(5)

            per_file = (70 / total_files) if total_files > 0 else 0
            accumulated = 0.0
            last_int = 0

            def on_file_progress(done: int, total: int) -> None:
                nonlocal accumulated, last_int
                accumulated += per_file
                current_int = int(accumulated)
                delta = current_int - last_int
                if delta > 0:
                    prog.advance(delta)
                    last_int = current_int
                lbl.update(f"Analyzing files... [{done}/{total}]")

            log.write(f"[bold]Analyzing [green]{analyzable}[/green] text files...[/bold]")
            analyzer = FileAnalyzer(client, log)
            file_summaries = await analyzer.analyze(files, on_file_progress)

            if not files:
                advance(70)
            else:
                remaining = 70 - last_int
                if remaining > 0:
                    prog.advance(remaining)

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
            advance(25)
            lbl.update("Done!")
            log.write("[bold green]Complete.[/bold green]")
            await asyncio.sleep(0.4)
            self.app.push_screen(OutputScreen())

        except asyncio.CancelledError:
            log.write("[yellow]Cancelled.[/yellow]")
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
        Binding("ctrl+y", "copy_output", "Copy"),
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

        ai_btns: List[Any] = [Label("Open with AI: ", id="ai_open_label")]
        for ai_name in AI_SERVICE_KEYS:
            variant = "primary" if ai_name == preferred_ai else "default"
            safe_id = "btn_ai_" + ai_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
            ai_btns.append(Button(ai_name, id=safe_id, variant=variant, classes="ai_btn"))

        yield Header()
        yield Vertical(
            Static(stats_text, id="stats_bar"),
            Static(f"  ~{token_est:,} tokens estimated", id="token_label"),
            ScrollableContainer(
                Static(id="output_text", markup=False),
                id="scroll_area",
            ),
            Vertical(
                Horizontal(*ai_btns, id="ai_open_row"),
                Horizontal(
                    Button("Save  [Ctrl+S]", variant="success", id="btn_save"),
                    Button("Copy  [Ctrl+Y]", variant="default", id="btn_copy"),
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
            raw = btn_id[len("btn_ai_"):]
            matched = next(
                (
                    name for name in AI_SERVICE_KEYS
                    if name.lower().replace(" ", "_").replace("(", "").replace(")", "") == raw
                ),
                None,
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
            if copied:
                self.notify(
                    f"Opened {ai_name}. Prompt copied to clipboard — paste it!",
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
    SUB_TITLE = "AI-Ready Project Context Generator"
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

        saved_model = config.get("last_model", "")
        if saved_model not in PROVIDER_MODELS.get(saved_provider, []):
            saved_model = PROVIDER_MODELS[saved_provider][0] if PROVIDER_MODELS.get(saved_provider) else ""

        preferred_ai = config.get("preferred_ai", "Claude")
        if preferred_ai not in AI_BROWSER_SERVICES:
            preferred_ai = AI_SERVICE_KEYS[0]

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
            "ollama_models": [],
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
