# Todoist‑MCP (Deep Research Connector)

A **true Deep‑Research MCP** for ChatGPT that exposes exactly two SSE tools:

- `POST /sse/search` → returns `[ { id, title, text, url } ]`
- `POST /sse/fetch`  → returns `{ id, title, text, url, metadata }`

No OpenAPI manifest, no Actions/Plugin files — Deep Research calls the SSE routes directly.

## Deploy (Fly.io)

```bash
fly secrets set TODOIST_TOKEN=xxxxxxxxxxxxxxxxxxxx
fly deploy