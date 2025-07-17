"""
Minimal Deep‑Research MCP connector for Todoist
----------------------------------------------

* Exposes exactly two tools:  search  and  fetch
* Uses Todoist REST API v2 (https://developer.todoist.com/rest/v2/)
* Looks at Tasks **and** Projects (per your scope)
* Requires a Fly.io secret called  TODOIST_TOKEN  (personal or service‑account)
"""

import os
import asyncio
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field
from fastmcp import FastMCP, Tool

# --------------------------------------------------------------------------- #
# Pydantic models that match the Deep‑Research spec
# --------------------------------------------------------------------------- #

class SearchRequest(BaseModel):
    query: str = Field(..., description="Free‑text search string")

class Snippet(BaseModel):
    id: str
    title: str
    text: str          # ≈200‑char snippet
    url: str

class FetchRequest(BaseModel):
    id: str = Field(..., description="Identifier returned from search")

class Doc(BaseModel):
    id: str
    title: str
    text: str          # full content
    url: str
    metadata: Optional[dict] = None


# --------------------------------------------------------------------------- #
# FastMCP application
# --------------------------------------------------------------------------- #

app = FastMCP(
    title="Todoist Deep‑Research Connector",
    version="0.1.0",
    description="Search and fetch Todoist tasks & projects using Deep Research",
)

TODOIST_BASE = "https://api.todoist.com/rest/v2"
TOKEN = os.getenv("TODOIST_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

# Helper -------------------------------------------------------------------- #

async def _get(client: httpx.AsyncClient, url: str, **kwargs):
    resp = await client.get(url, headers=HEADERS, timeout=10, **kwargs)
    resp.raise_for_status()
    return resp.json()

# Tool: search -------------------------------------------------------------- #

@app.tool(
    Tool(
        name="search",
        request=SearchRequest,
        response=List[Snippet],
        description="Search Todoist tasks and projects by text",
    )
)
async def search(req: SearchRequest) -> List[Snippet]:
    if not TOKEN:
        raise RuntimeError("TODOIST_TOKEN env var is missing")

    query = req.query.lower()
    snippets: List[Snippet] = []

    async with httpx.AsyncClient() as client:
        # -- Tasks -----------------------------------------------------------
        tasks = await _get(client, f"{TODOIST_BASE}/tasks", params={"filter": f"search: {req.query}"})
        for t in tasks:
            if len(snippets) >= 10:
                break
            title = t["content"]
            if query in title.lower():
                snippet_text = f"{title}  (due: {t.get('due', {}).get('date')}, priority: {t['priority']})"
                snippets.append(
                    Snippet(
                        id=f"task:{t['id']}",
                        title=title,
                        text=snippet_text[:200],
                        url=f"https://todoist.com/showTask?id={t['id']}",
                    )
                )

        # -- Projects --------------------------------------------------------
        if len(snippets) < 10:
            projects = await _get(client, f"{TODOIST_BASE}/projects")
            for p in projects:
                if len(snippets) >= 10:
                    break
                name = p["name"]
                if query in name.lower():
                    snippets.append(
                        Snippet(
                            id=f"project:{p['id']}",
                            title=name,
                            text=f"Project • {name}"[:200],
                            url=f"https://todoist.com/showProject?id={p['id']}",
                        )
                    )

    return snippets

# Tool: fetch --------------------------------------------------------------- #

@app.tool(
    Tool(
        name="fetch",
        request=FetchRequest,
        response=Doc,
        description="Fetch full detail for a Todoist task or project by id",
    )
)
async def fetch(req: FetchRequest) -> Doc:
    if not TOKEN:
        raise RuntimeError("TODOIST_TOKEN env var is missing")

    kind, raw_id = req.id.split(":", 1)
    async with httpx.AsyncClient() as client:
        if kind == "task":
            data = await _get(client, f"{TODOIST_BASE}/tasks/{raw_id}")
            labels = data.get("labels", [])
            doc = Doc(
                id=req.id,
                title=data["content"],
                text=data["content"],
                url=f"https://todoist.com/showTask?id={raw_id}",
                metadata={
                    "due": data.get("due"),
                    "priority": data["priority"],
                    "labels": labels,
                    "project_id": data["project_id"],
                },
            )
        elif kind == "project":
            data = await _get(client, f"{TODOIST_BASE}/projects/{raw_id}")
            doc = Doc(
                id=req.id,
                title=data["name"],
                text=data.get("description") or data["name"],
                url=f"https://todoist.com/showProject?id={raw_id}",
                metadata={
                    "color": data.get("color"),
                    "comment_count": data.get("comment_count"),
                },
            )
        else:
            raise ValueError("id must start with 'task:' or 'project:'")
    return doc

# --------------------------------------------------------------------------- #
# Entrypoint – default to SSE, which ChatGPT handles natively
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # FastMCP’s .run() wraps a Uvicorn server under the hood
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)), transport="sse")
