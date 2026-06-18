<div align="center">

# pxForge

**Turn your entire codebase into a single AI-ready prompt.**

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-black.svg)]()
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg)]()
[![Made by 669px](https://img.shields.io/badge/made%20by-669px-purple.svg)](https://github.com/669px)

pxForge scans your project recursively, analyzes every file with an LLM, and outputs a structured context document you can drop directly into any AI coding assistant — Claude, ChatGPT, Gemini, or Cursor.

</div>

---

## What It Does

Most AI assistants don't know your codebase. You paste snippets, explain context, repeat yourself. pxForge fixes that.

It walks your entire project, reads every file, and produces a single Markdown document containing:

- A high-level project summary
- Your full directory tree
- Per-file breakdowns (purpose, logic, dependencies)
- A ready-to-use system prompt tailored to your exact codebase

Paste it once. Your AI assistant is now a collaborator who actually knows the code.

---

## Features

- **Recursive scanning** — walks the full project tree, skips binaries, build artifacts, and lock files automatically
- **LLM-powered analysis** — every file is analyzed for purpose, key functions, dependencies, and non-obvious logic
- **Multi-provider support** — works with OpenAI, Anthropic (Claude), Groq, OpenRouter, and Ollama (local)
- **Ollama auto-detection** — detects every model you have pulled locally, no API key required
- **Parallel processing** — files are analyzed concurrently with provider-aware rate limiting
- **Smart chunking** — large files are split, analyzed in parts, then merged into a single coherent summary
- **`.gitignore` aware** — automatically respects the project's `.gitignore` so custom virtual environments, build output, and local config files are never analyzed
- **Fast file I/O** — optimized reading with binary detection and concurrent disk access
- **Cross-platform** — runs natively on Linux, macOS, and Windows with platform-specific clipboard and path handling
- **Open with AI** — one-click buttons open Claude, ChatGPT, Gemini, Grok, and more directly in your browser
- **Token estimator** — shows approximate token count before you paste
- **Saves your config** — API keys, provider, model, and preferred AI are remembered between runs
- **Terminal UI** — fully interactive TUI built with Textual, no browser required

---

## Installation

**Requirements:** Python 3.10+, Git

> **Quick check:** `python --version` or `python3 --version` — must be 3.10 or higher.

---

### Linux

**Debian / Ubuntu / Mint**

```bash
# Clipboard support
sudo apt update
sudo apt install -y git xclip          # X11
# or
sudo apt install -y git wl-clipboard   # Wayland

# Clone and install
git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python3 pxforge.py install
```

**Arch / Manjaro**

```bash
sudo pacman -S git xclip     # X11
# or
sudo pacman -S git wl-clipboard  # Wayland

git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python3 pxforge.py install
```

**Fedora / RHEL / CentOS**

```bash
sudo dnf install -y git xclip

git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python3 pxforge.py install
```

Reload your shell after installing:

```bash
source ~/.bashrc   # bash
source ~/.zshrc    # zsh
exec fish          # fish
```

The `install` command writes a wrapper script to `~/.local/bin/pxforge` and adds it to your `PATH` automatically.

---

### macOS

**Homebrew (recommended)**

```bash
# Install Python if needed
brew install python git

git clone https://github.com/669px/pxforge.git
cd pxforge
pip3 install -r requirements.txt
python3 pxforge.py install
source ~/.zshrc
```

**Without Homebrew**

```bash
git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python pxforge.py install
source ~/.zshrc
```

Clipboard support works out of the box via `pbcopy` — no extra dependencies needed. If you use Fish shell: `exec fish` instead of sourcing a profile.

---

### Windows

**Option 1 — PowerShell (recommended)**

Open PowerShell as a regular user (no admin required):

```powershell
# Install Python from the Microsoft Store or python.org if not already installed
# Then:

git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python pxforge.py install
```

The `install` command adds pxForge to `%APPDATA%\pxforge\` and registers it in your user `PATH`. Restart PowerShell, then run:

```powershell
pxforge .
```

**Option 2 — Windows Subsystem for Linux (WSL2)**

If you have WSL2 set up, the Linux install path works identically inside your WSL environment. Clipboard integration between WSL and Windows requires `clip.exe`, which is available by default in WSL2.

```bash
git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python3 pxforge.py install
source ~/.bashrc
```

**Option 3 — CMD**

```cmd
git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python pxforge.py install
```

Restart CMD, then `pxforge` is available globally.

> **Windows note:** Clipboard support uses `pyperclip` on Windows, which requires no extra system packages. If you hit a `pyperclip` error, run `pip install pyperclip`.

---

### Without installing to PATH

Works on all platforms — no install step needed:

```bash
# Linux / macOS
python3 pxforge.py .
python3 pxforge.py /path/to/project

# Windows
python pxforge.py .
python pxforge.py C:\Users\you\myproject
```

---

## Usage

```bash
pxforge                  # launch with interactive directory picker
pxforge .                # scan current directory
pxforge /path/to/project # scan a specific project
pxforge install          # install the pxforge CLI command
pxforge --help           # show help
```

On Windows, the same commands work in PowerShell, CMD, and Windows Terminal.

---

## First Run

1. Launch `pxforge` or point it at a directory
2. Select your **provider** (OpenAI, Anthropic, Groq, OpenRouter, or Ollama)
3. Enter your **API key** — saved to `~/.pxforge/config.json` for future runs *(not required for Ollama)*
4. Pick a **model** and **mode** (Fast or High Quality)
5. Choose your **preferred AI** for one-click output viewing
6. Hit **Start Scan**

When complete, the output screen gives you options to:

- Save to `pxforge_output.md` in the scanned directory
- Copy the full prompt to clipboard
- Open any supported AI directly in your browser with the prompt pre-copied

> **Config location by platform:**
> - Linux / macOS: `~/.pxforge/config.json`
> - Windows: `%USERPROFILE%\.pxforge\config.json`

---

## Using Ollama (Local Models)

pxForge supports fully local inference via [Ollama](https://ollama.com) — no API key, no cost, no data leaving your machine.

**Setup (Linux / macOS)**

```bash
curl -fsSL https://ollama.com/install.sh | sh

ollama pull llama3
ollama pull mistral
ollama pull codellama

ollama serve
```

**Setup (Windows)**

Download the installer from [ollama.com](https://ollama.com) and run it. Then in PowerShell:

```powershell
ollama pull llama3
ollama pull mistral
ollama serve
```

**In pxForge:**

1. Select **Ollama (Local)** as the provider
2. pxForge auto-detects all downloaded models — no API key needed
3. A live status indicator shows whether Ollama is reachable
4. Hit **↻ Refresh** to re-detect models after pulling new ones

> **Note:** Local models process files sequentially (concurrency = 2). Large projects will take longer than cloud providers — use a capable model like `llama3`, `mistral`, or `codellama` for best results.

---

## Supported AI Services

One-click open from the output screen:

| Service | URL |
|---|---|
| Claude | claude.ai |
| ChatGPT | chatgpt.com |
| Gemini | gemini.google.com |
| Grok | grok.com |
| Perplexity | perplexity.ai |
| Mistral | chat.mistral.ai |
| DeepSeek | chat.deepseek.com |

---

## Supported Providers

| Provider | Models | API Key |
|---|---|---|
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo, o3-mini | Required |
| **Anthropic** | claude-sonnet-4, claude-opus-4, claude-haiku-4 | Required |
| **Groq** | llama-3.3-70b, llama-3.1-8b, gemma2-9b, mixtral-8x7b | Required |
| **OpenRouter** | claude, gpt-4o, llama-3.3-70b, gemini-flash, deepseek-r1 | Required |
| **Ollama (Local)** | any model you have pulled (`ollama list`) | Not required |

---

## Output Structure

```
pxforge_output.md
│
├── PROJECT SUMMARY
├── DIRECTORY STRUCTURE
├── FILE ANALYSES
├── SKIPPED / BINARY FILES
└── AI SYSTEM PROMPT
```

---

## What Gets Ignored

pxForge automatically skips files and directories that add noise:

**Directories:** `.git`, `node_modules`, `dist`, `build`, `__pycache__`, `.venv`, `venv`, `env`, `.tox`, `.nox`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `site-packages`, `htmlcov`, `.terraform`, `.serverless`, `.coverage`, `.next`, `.nuxt`, `out`, `.gradle`, `.idea`, `.vscode`, `vendor`, `target`, and more

**File types:** images, videos, audio, fonts, compiled binaries, archives, lock files, minified assets

**Large files:** anything over 500KB is skipped with a note

**`.gitignore` patterns:** If your project has a `.gitignore`, pxForge respects it automatically. Custom virtual environments, local env files, build artifacts, and anything else you already ignore will be skipped without wasting API tokens.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+S` | Save output to file |
| `Ctrl+Y` | Copy output to clipboard |
| `Ctrl+Q` | Quit |
| `Escape` | Cancel scan in progress |

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.10+ |
| Terminal UI | [Textual](https://github.com/Textualize/textual) |
| HTTP client | [httpx](https://www.python-httpx.org/) |
| Concurrency | asyncio |

---

## Configuration

Config is stored at `~/.pxforge/config.json` (Linux/macOS) or `%USERPROFILE%\.pxforge\config.json` (Windows) and persists:

- API keys per provider
- Last used provider and model
- Last used mode (fast / high quality)
- Preferred AI service for browser open

Ollama does not store any credentials — it connects to `http://localhost:11434` automatically.

---

## Troubleshooting

**`pxforge: command not found` after install**
Reload your shell (`source ~/.bashrc`, `source ~/.zshrc`, or restart your terminal). On Windows, open a new PowerShell window.

**Clipboard not working on Linux**
Install `xclip` (X11) or `wl-clipboard` (Wayland) via your package manager. Confirm your session type with `echo $XDG_SESSION_TYPE`.

**Textual fails to render on Windows CMD**
Use Windows Terminal or PowerShell — CMD has limited ANSI support. WSL2 works without any restrictions.

**`pip install` fails due to permissions**
Add `--user` flag: `pip install --user -r requirements.txt`. Never use `sudo pip` on a system Python.

**Ollama not detected**
Ensure `ollama serve` is running. Confirm it's reachable: `curl http://localhost:11434/api/tags`. Hit **↻ Refresh** in the provider screen.

**Large project times out**
Switch to Fast mode or use a smaller Ollama model. Cloud providers (Groq, OpenRouter) handle parallel file analysis significantly faster than local inference.

---

## Philosophy

> If something slows you down twice, automate it.

pxForge exists because pasting context into AI assistants manually is tedious, error-prone, and doesn't scale. One command should be enough to make any AI fully aware of any codebase.

---

## License

MIT License — Copyright (c) 2026 [669px](https://github.com/669px)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
