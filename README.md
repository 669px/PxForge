<div align="center">

# pxForge

**Turn your entire codebase into a single AI-ready prompt.**

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-black.svg)]()
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
- **Multi-provider support** — works with OpenAI, Anthropic (Claude), Groq, and OpenRouter
- **Parallel processing** — files are analyzed concurrently with provider-aware rate limiting
- **Smart chunking** — large files are split, analyzed in parts, then merged into a single coherent summary
- **Open with AI** — one-click buttons open Claude, ChatGPT, Gemini, Grok, and more directly in your browser
- **Token estimator** — shows approximate token count before you paste
- **Saves your config** — API keys, provider, model, and preferred AI are remembered between runs
- **Terminal UI** — fully interactive TUI built with Textual, no browser required

---

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/669px/pxforge.git
cd pxforge
pip install -r requirements.txt
python pxforge.py install
```

Then reload your shell:

```bash
source ~/.bashrc   # bash
source ~/.zshrc    # zsh
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

---

## First Run

1. Launch `pxforge` or point it at a directory
2. Select your **provider** (OpenAI, Anthropic, Groq, OpenRouter)
3. Enter your **API key** — saved to `~/.pxforge/config.json` for future runs
4. Pick a **model** and **mode** (Fast or High Quality)
5. Choose your **preferred AI** for one-click output viewing
6. Hit **Start Scan**

When complete, the output screen gives you options to:

- Save to `pxforge_output.md` in the scanned directory
- Copy the full prompt to clipboard
- Open any supported AI directly in your browser with the prompt pre-copied

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

| Provider | Models |
|---|---|
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo, o3-mini |
| **Anthropic** | claude-sonnet-4, claude-opus-4, claude-haiku-4 |
| **Groq** | llama-3.3-70b, llama-3.1-8b, gemma2-9b, mixtral-8x7b |
| **OpenRouter** | claude, gpt-4o, llama-3.3-70b, gemini-flash, deepseek-r1 |

---

## Output Structure

```
pxforge_output.md
│
├── PROJECT SUMMARY          ← stack, architecture, core functionality
├── DIRECTORY STRUCTURE      ← full annotated tree
├── FILE ANALYSES            ← per-file: purpose, functions, deps, logic
├── SKIPPED / BINARY FILES   ← what was found but not analyzed
└── AI SYSTEM PROMPT         ← drop this into any AI assistant
```

---

## What Gets Ignored

pxForge automatically skips files and directories that add noise:

**Directories:** `.git`, `node_modules`, `dist`, `build`, `__pycache__`, `.venv`, `.next`, `vendor`, `target`, `.idea`, `.vscode`

**File types:** images, videos, audio, fonts, compiled binaries, archives, lock files, minified assets

**Large files:** anything over 500KB is skipped with a note

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+S` | Save output to file |
| `Ctrl+C` | Copy output to clipboard |
| `Ctrl+Q` | Quit |

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

Config is stored at `~/.pxforge/config.json` and persists:

- API keys per provider
- Last used provider and model
- Last used mode (fast / high quality)
- Preferred AI service for browser open

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
