# Todoist MCP Connector

Minimal MCP server that lets ChatGPT Deep Research search & fetch Todoist tasks.

## Setup
```bash
python -m venv env && source env/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit token
```

## Run
```bash
python todoist_mcp.py
```

## Overview

This connector exposes your Todoist tasks to ChatGPT via the MCP (Machine Connector Protocol) interface. It implements:

- `search(query)` – Find tasks by keyword.
- `fetch(id)` – Fetch full details for a specific task.

See [`todoist_mcp.py`](todoist_mcp.py) for the annotated implementation.

## Quick Start

1. Obtain your Todoist API token: https://todoist.com/personal-token
2. Copy `.env.example` to `.env` and paste your token.
3. Run the server locally (see above).
4. Optionally expose your server using [ngrok](https://ngrok.com/) for remote access.

## Integration with ChatGPT

1. Open ChatGPT (GPT 4-Turbo or newer).
2. Go to **Custom GPTs → Data → Add Integration (MCP)**.
3. Paste your server URL (e.g., `http://localhost:8000`).
4. ChatGPT will detect the `search` & `fetch` endpoints.
5. Prompt ChatGPT to search your Todoist tasks!

---

See the full guide in this repository for advanced features, production setup, and troubleshooting.