# 669px / pxForge

<p align="center">
  <b>Building tools that make the machine work for you</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" />
  <img src="https://img.shields.io/badge/status-active-black.svg" />
</p>

---

## pxForge

> Turn your entire codebase into a single AI-ready prompt.

pxForge scans your entire project and generates a structured system prompt compatible with modern AI coding assistants.

**Supported providers:**
OpenAI · Anthropic (Claude) · Groq · OpenRouter

---

## Features

* Recursive project scanning (ignores binaries & build artifacts)
* Full codebase analysis using LLMs
* Extracts structure, logic, and dependencies
* Generates:

  * Project summary
  * Directory overview
  * File-by-file breakdown
* Outputs a ready-to-use system prompt

---

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/669px/pxforge.git
cd pxforge
pip install textual httpx
python pxforge.py install
```

Reload your shell:

```bash
source ~/.bashrc
# or
source ~/.zshrc
```

---

## Usage

```bash
pxforge        # interactive mode
pxforge .      # current directory
pxforge /path  # specific project
```

---

## First Run

* Configure API key and model
* Stored at:

```
~/.pxforge/config.json
```

---

## Workflow

```
scan → analyze → summarize → generate → output
```

Final output is saved to:

```
pxforge_output.md
```

---

## CLI Options

| Command         | Description                  |
| --------------- | ---------------------------- |
| pxforge         | interactive directory picker |
| pxforge .       | scan current directory       |
| pxforge /path   | scan specific path           |
| pxforge install | install CLI                  |
| pxforge --help  | help menu                    |

---

## Tech Stack

* Python
* Textual
* asyncio
* httpx

---

## Philosophy

> If something slows you down twice, automate it.

---

## License

MIT License

Copyright (c) 2026 669px

Permission is hereby granted, free of charge, to any person obtaining a copy...
