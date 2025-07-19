"""
Todoist Deep‑Research MCP Connector
===================================

Implements the two required tools (`search`, `fetch`) for a ChatGPT
Deep‑Research connector. Interacts with Todoist’s REST API to surface
tasks and projects.

Run locally with:
    python todoist_mcp.py
"""

import os
import json
import yaml
import pathlib
from typing import Dict, List, Optional, Set, Tuple

import httpx  # type: ignore
from pydantic import BaseModel, Field  # type: ignore
from fastmcp import FastMCP  # type: ignore
from fastmcp.tools import Tool  # type: ignore
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# ──────────────────────────────────────────────────────────────────────────────
# App initialization
# ──────────────────────────────────────────────────────────────────────────────

app = FastMCP(
    name="Todoist Deep-Research Connector",
    instructions="Search and fetch Todoist tasks & projects using the Deep Research protocol",
)

# ──────────────────────────────────────────────────────────────────────────────
# Static file setup (manifest)
# ──────────────────────────────────────────────────────────────────────────────

STATIC_DIR = pathlib.Path("static")
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / ".well-known").mkdir(parents=True, exist_ok=True)

manifest = {
    "schema_version": "v1",
    "name_for_human": "Todoist MCP Connector",
    "name_for_model": "todoist_mcp",
    "description_for_human": "Search & fetch your Todoist tasks from ChatGPT.",
    "description_for_model": "Provides `search` and `fetch` tools for Todoist data.",
    "auth": {"type": "none"},
    "api": {"type": "openapi", "url": "https://todoist-mcp-connector.fly.dev/openapi.yaml"},
    "logo_url": "https://todoist-mcp-connector.fly.dev/logo.png",
    "contact_email": "you@example.com",
    "legal_info_url": "https://example.com/legal"
}
manifest_path = STATIC_DIR / ".well-known" / "ai-plugin.json"
manifest_path.write_text(json.dumps(manifest, indent=2))

# CORS so ChatGPT’s browser client can call the server
app.fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route to serve the manifest
@app.get("/.well-known/ai-plugin.json", include_in_schema=False)
def serve_manifest():
    return FileResponse(manifest_path)

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models (Deep‑Research spec)
# ──────────────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., description="Free‑text search string")


class Snippet(BaseModel):
    id: str
    title: str
    text: str   # ≈200‑char snippet
    url: str


class FetchRequest(BaseModel):
    id: str = Field(..., description="Identifier returned from search")


class Doc(BaseModel):
    id: str
    title: str
    text: str   # full content
    url: str
    metadata: Optional[Dict] = None

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

TODOIST_BASE = "https://api.todoist.com/rest/v2"


def get_token_and_headers() -> Tuple[str, Dict[str, str]]:
    token = os.getenv("TODOIST_TOKEN")
    if not token:
        raise RuntimeError(
            "TODOIST_TOKEN environment variable is missing. "
            "Set it via fly secrets or your shell."
        )
    return token, {"Authorization": f"Bearer {token}"}


async def http_get(
    client: httpx.AsyncClient, url: str, headers: Dict[str, str], **params
) -> dict:
    resp = await client.get(url, headers=headers, timeout=10, params=params)
    resp.raise_for_status()
    return resp.json()


def make_task_snippet(task: dict) -> Snippet:
    title = task.get("content", "")
    due_date = (task.get("due") or {}).get("date")
    priority = task.get("priority")
    snippet = title
    parts = []
    if due_date:
        parts.append(f"due: {due_date}")
    if priority:
        parts.append(f"priority: {priority}")
    if parts:
        snippet += " (" + ", ".join(parts) + ")"
    return Snippet(
        id=f"task:{task['id']}",
        title=title,
        text=snippet[:200],
        url=f"https://todoist.com/showTask?id={task['id']}",
    )


def make_project_snippet(project: dict) -> Snippet:
    name = project.get("name", "")
    return Snippet(
        id=f"project:{project['id']}",
        title=name,
        text=("Project • " + name)[:200],
        url=f"https://todoist.com/showProject?id={project['id']}",
    )

# ──────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────────────────────────

@app.tool(
    Tool(
        name="search",
        request=SearchRequest,
        response=List[Snippet],
        description="Search Todoist tasks and projects by free‑text query",
    )
)
async def search(req: SearchRequest) -> List[Snippet]:
    _, headers = get_token_and_headers()

    query = req.query.strip()
    if not query:
        return []

    results: List[Snippet] = []
    seen_ids: Set[str] = set()

    search_filter = f'search: "{query}"' if " " in query else f"search: {query}"

    async with httpx.AsyncClient() as client:
        tasks = await http_get(
            client,
            f"{TODOIST_BASE}/tasks",
            headers,
            filter=search_filter,
        )
        for task in tasks:
            if len(results) >= 10:
                break
            snippet = make_task_snippet(task)
            if snippet.id not in seen_ids:
                results.append(snippet)
                seen_ids.add(snippet.id)

        if len(results) < 10:
            projects = await http_get(client, f"{TODOIST_BASE}/projects", headers)
            for project in projects:
                if len(results) >= 10:
                    break
                if query.lower() in project.get("name", "").lower():
                    snippet = make_project_snippet(project)
                    if snippet.id not in seen_ids:
                        results.append(snippet)
                        seen_ids.add(snippet.id)

    return results


@app.tool(
    Tool(
        name="fetch",
        request=FetchRequest,
        response=Doc,
        description="Fetch full detail for a Todoist task or project by id",
    )
)
async def fetch(req: FetchRequest) -> Doc:
    _, headers = get_token_and_headers()

    try:
        kind, raw_id = req.id.split(":", 1)
    except ValueError:
        raise ValueError("id must be in the format 'task:<id>' or 'project:<id>'")

    async with httpx.AsyncClient() as client:
        if kind == "task":
            data = await http_get(client, f"{TODOIST_BASE}/tasks/{raw_id}", headers)
            doc = Doc(
                id=req.id,
                title=data.get("content", ""),
                text=data.get("content", ""),
                url=f"https://todoist.com/showTask?id={raw_id}",
                metadata={
                    "due": data.get("due"),
                    "priority": data.get("priority"),
                    "labels": data.get("labels"),
                    "project_id": data.get("project_id"),
                },
            )
        elif kind == "project":
            data = await http_get(client, f"{TODOIST_BASE}/projects/{raw_id}", headers)
            doc = Doc(
                id=req.id,
                title=data.get("name", ""),
                text=data.get("description") or data.get("name", ""),
                url=f"https://todoist.com/showProject?id={raw_id}",
                metadata={
                    "color": data.get("color"),
                    "comment_count": data.get("comment_count"),
                },
            )
        else:
            raise ValueError("Unknown resource type; id must start with 'task:' or 'project:'")

    return doc

# ──────────────────────────────────────────────────────────────────────────────
# Routes added AFTER tool registration
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/openapi.yaml", include_in_schema=False)
def serve_openapi():
    """Generate OpenAPI after tools are registered."""
    return PlainTextResponse(
        yaml.safe_dump(app.fastapi_app.openapi(), sort_keys=False),
        media_type="text/yaml"
    )

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}

# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, transport="sse")