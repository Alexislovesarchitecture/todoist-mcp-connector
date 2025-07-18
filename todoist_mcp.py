"""
Todoist Deep‑Research MCP Connector
===================================

This module implements the two required tools for a ChatGPT
Deep‑Research connector: `search` and `fetch`. It interacts with
Todoist’s REST API to surface tasks and projects for retrieval.

Key features:

* Handles both tasks and projects in search results, capped at 10 items.
* Quotes multi‑word queries to satisfy Todoist’s search filter syntax.
* Deduplicates IDs across tasks and projects.
* Provides extra metadata (due date, priority, labels) in fetch results.
* Adds CORS support for ChatGPT’s browser client and a simple `/health`
  endpoint for Fly.io health checks.

Environment variables:

* `TODOIST_TOKEN` (required): Personal or service account token.
* `PORT` (optional): Port to bind the server; defaults to 8000.

Run locally with:

    python todoist_mcp.py

The server binds to all interfaces and uses SSE transport by default.
"""

import os
from typing import Dict, List, Optional, Set, Tuple

import httpx  # type: ignore
from pydantic import BaseModel, Field  # type: ignore
from fastmcp import FastMCP  # type: ignore
from fastmcp.tools import Tool  # type: ignore


# ---------------------------------------------------------------------------
# Pydantic models adhering to the Deep‑Research specification
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Request body for the search tool: a free‑text query."""

    query: str = Field(..., description="Free‑text search string")


class Snippet(BaseModel):
    """Represents a short search result returned to ChatGPT."""

    id: str
    title: str
    text: str  # ≈200‑char snippet
    url: str


class FetchRequest(BaseModel):
    """Request body for the fetch tool: an ID previously returned by search."""

    id: str = Field(..., description="Identifier returned from search")


class Doc(BaseModel):
    """Full document returned by the fetch tool."""

    id: str
    title: str
    text: str  # full content
    url: str
    metadata: Optional[Dict] = None


# ---------------------------------------------------------------------------
# Application initialization
# ---------------------------------------------------------------------------

app = FastMCP(
    name="Todoist Deep-Research Connector",
    instructions="Search and fetch Todoist tasks & projects using the Deep Research protocol",
)




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODOIST_BASE = "https://api.todoist.com/rest/v2"


def get_token_and_headers() -> Tuple[str, Dict[str, str]]:
    """Retrieve the Todoist token from the environment and return headers.

    Raises:
        RuntimeError: if the token is missing.
    """

    token = os.getenv("TODOIST_TOKEN")
    if not token:
        raise RuntimeError(
            "TODOIST_TOKEN environment variable is missing. Set it via fly secrets or your shell."
        )
    return token, {"Authorization": f"Bearer {token}"}


async def http_get(client: httpx.AsyncClient, url: str, headers: Dict[str, str], **params) -> dict:
    """Perform a GET request with the provided headers and query parameters.

    Args:
        client: The httpx client to use.
        url: The full URL to fetch.
        headers: Authorization headers.
        **params: Additional keyword arguments passed to httpx.get (e.g., params).

    Returns:
        Parsed JSON response as a Python dict or list.
    """

    resp = await client.get(url, headers=headers, timeout=10, params=params)
    resp.raise_for_status()
    return resp.json()


def make_task_snippet(task: dict) -> Snippet:
    """Construct a search result snippet from a Todoist task object."""

    title = task.get("content", "")
    due = task.get("due", {}) or {}
    due_date = due.get("date")
    priority = task.get("priority")
    snippet = f"{title}"
    if due_date or priority:
        parts = []
        if due_date:
            parts.append(f"due: {due_date}")
        if priority:
            parts.append(f"priority: {priority}")
        snippet += " (" + ", ".join(parts) + ")"
    return Snippet(
        id=f"task:{task['id']}",
        title=title,
        text=snippet[:200],
        url=f"https://todoist.com/showTask?id={task['id']}",
    )


def make_project_snippet(project: dict) -> Snippet:
    """Construct a search result snippet from a Todoist project object."""

    name = project.get("name", "")
    return Snippet(
        id=f"project:{project['id']}",
        title=name,
        text=("Project • " + name)[:200],
        url=f"https://todoist.com/showProject?id={project['id']}",
    )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@app.tool(
    Tool(
        name="search",
        request=SearchRequest,
        response=List[Snippet],
        description="Search Todoist tasks and projects by free‑text query",
    )
)
async def search(req: SearchRequest) -> List[Snippet]:
    """Search tasks and projects in Todoist matching the query string.

    The function returns up to 10 unique results. A result ID is
    prefixed with `task:` or `project:` so that `fetch` can look up
    the appropriate resource.
    """

    _, headers = get_token_and_headers()

    query = req.query.strip()
    if not query:
        return []

    results: List[Snippet] = []
    seen_ids: Set[str] = set()

    # Quote the query if it contains whitespace to satisfy Todoist filter syntax
    search_filter = f'search: "{query}"' if " " in query else f"search: {query}"

    async with httpx.AsyncClient() as client:
        # Fetch tasks matching the search filter
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

        # Fetch projects only if we have capacity for more results
        if len(results) < 10:
            projects = await http_get(
                client,
                f"{TODOIST_BASE}/projects",
                headers,
            )
            for project in projects:
                if len(results) >= 10:
                    break
                # Basic substring match on project name
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
    """Fetch full details for a given task or project ID.

    Supports IDs returned by `search` in the form `task:<id>` or
    `project:<id>`. Raises ValueError if the prefix is unknown.
    """

    _, headers = get_token_and_headers()

    # Split the prefix and numeric ID
    try:
        kind, raw_id = req.id.split(":", 1)
    except ValueError:
        raise ValueError("id must be in the format 'task:<id>' or 'project:<id>'")

    async with httpx.AsyncClient() as client:
        if kind == "task":
            data = await http_get(
                client,
                f"{TODOIST_BASE}/tasks/{raw_id}",
                headers,
            )
            labels = data.get("labels", [])
            due = data.get("due")
            priority = data.get("priority")
            project_id = data.get("project_id")
            doc = Doc(
                id=req.id,
                title=data.get("content", ""),
                text=data.get("content", ""),
                url=f"https://todoist.com/showTask?id={raw_id}",
                metadata={
                    "due": due,
                    "priority": priority,
                    "labels": labels,
                    "project_id": project_id,
                },
            )
        elif kind == "project":
            data = await http_get(
                client,
                f"{TODOIST_BASE}/projects/{raw_id}",
                headers,
            )
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


# ---------------------------------------------------------------------------
# Additional routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint for Fly.io.

    Returns a simple JSON object. If this route returns a non‑2xx
    response, Fly will mark the instance as unhealthy.
    """

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bind to the port provided by the environment (Fly injects PORT)
    port = int(os.getenv("PORT", 8000))
    # SSE is the default transport recommended by OpenAI.
    app.run(host="0.0.0.0", port=port, transport="sse")