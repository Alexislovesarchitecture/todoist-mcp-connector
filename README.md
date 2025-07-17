\# Todoist‑MCP — ChatGPT Deep‑Research connector
Minimal search + fetch gateway for Todoist tasks & projects
===========================================================

This project is a **true Deep‑Research MCP connector**: it exposes exactly
two endpoints (`/sse/search`, `/sse/fetch`) that ChatGPT will call to search
and retrieve Todoist content. No plugin manifest or OpenAI “actions” are used.

---

## ✨ Features

* **Search** by free text across *tasks **and** projects*.
* **Fetch** full task/project details, including due‑date, priority & labels.
* Zero‑config **SSE transport** – works out‑of‑the‑box with ChatGPT.
* One secret only: `TODOIST_TOKEN` (set in Fly.io, Render, Railway, etc.).
* 40‑line FastMCP server, <200 LOC total.

---

## 📂 Repo layout

```
.
├── todoist_mcp.py      # FastMCP server (search & fetch)
├── requirements.txt    # Python deps
└── README.md           # You are here
```

*Dockerfile, `fly.toml`, CI, etc. can be added later.*

---

## 🚀 Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export TODOIST_TOKEN=xxxxxxxxxxxxxxxxxxxx   # personal API token
python todoist_mcp.py           # default: http://127.0.0.1:8000
```

Test with `curl`:

```bash
curl -N -H "Content-Type: application/json" \
     -d '{"query":"draft"}' \
     http://127.0.0.1:8000/sse/search
```

---

## 🛫 Deploy to Fly.io (one‑liner version)

```bash
fly launch --no-deploy           # creates fly.toml & Dockerfile
fly secrets set TODOIST_TOKEN=xxxxxxxxxxxxxxxxxxxx
fly deploy                       # build & release
```

After deploy, Fly prints a URL like:

```
https://todoist-mcp.fly.dev
```

---

## 🧩 Connect to ChatGPT

1. Open **ChatGPT → Tools → Run Deep Research → Add sources → Create**.
2. Paste the base URL from Fly (e.g., `https://todoist-mcp.fly.dev`).
   *ChatGPT automatically appends `/sse/search` and `/sse/fetch`.*
3. Save. You can now ask ChatGPT questions that require Todoist context, e.g.:

> “Search Todoist for tasks mentioning ‘invoice’ and show details.”

---

## 🔐 Configuration

| Env var         | Purpose                                                                                                                                                                    |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TODOIST_TOKEN` | Personal / service account token from [https://todoist.com/prefs/integrations](https://todoist.com/prefs/integrations). Store as a secret in Fly.io (`fly secrets set …`). |
| `PORT`          | Override default `8000` (Fly sets this automatically).                                                                                                                     |

*No other configuration is required.*

---

## 📜 API reference (Deep‑Research spec)

### `POST /sse/search`  *(Server‑Sent Events)*

```jsonc
// request
{ "query": "text to search" }

// response  (streamed as a single SSE event data: ...)
[
  {
    "id": "task:2995104339",
    "title": "Pay electric bill",
    "text": "Pay electric bill  (due: 2025‑07‑20, priority: 4)",
    "url": "https://todoist.com/showTask?id=2995104339"
  },
  …
]
```

### `POST /sse/fetch`

```jsonc
// request
{ "id": "task:2995104339" }

// response
{
  "id": "task:2995104339",
  "title": "Pay electric bill",
  "text": "Pay electric bill",
  "url": "https://todoist.com/showTask?id=2995104339",
  "metadata": {
    "due": { "date": "2025‑07‑20" },
    "priority": 4,
    "labels": ["finance", "home"],
    "project_id": 2203309130
  }
}
```

---

## 🛠️ Extending & hardening (roadmap)

* **HTTP transport** (`/http/search`) for hosts that don’t support SSE.
* **OAuth 2.0** flow for multi‑user deployments.
* **Rate‑limit & error handling** (Todoist 429, network hiccups).
* **Vector cache** (SQLite/Faiss) for faster, offline‑tolerant searches.
* **Docker‑compose** dev stack with Hot Reload (`--reload`).
* **CI/CD** GitHub Action → Fly deploy on merge to `main`.

---

## 🤝 Contributing

1. Fork & clone.
2. Create a branch: `git checkout -b feature/your‑feature`.
3. Commit, push, open a PR.
   Bug reports and feature ideas are welcome via Issues.

---

## 🪪 License

MIT — see [`LICENSE`](LICENSE) for full text.
