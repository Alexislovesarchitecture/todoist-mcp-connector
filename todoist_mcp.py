import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP, Tool
from pydantic import BaseModel, Field

# ---------- Config ----------
TODOIST_TOKEN = os.getenv("TODOIST_TOKEN")
if not TODOIST_TOKEN:
    # Fail fast in cloud so health checks surface a clear reason
    raise RuntimeError("Missing TODOIST_TOKEN environment variable")

BASE_URL = "https://api.todoist.com/rest/v2"
HEADERS = {"Authorization": f"Bearer {TODOIST_TOKEN}"}

# ---------- Models required by Deep Research ----------
class SearchInput(BaseModel):
    query: str = Field(..., description="Free-text query to match tasks/projects")

class SearchHit(BaseModel):
    id: str
    title: str
    text: str
    url: str

class SearchOutput(BaseModel):
    __root__: List[SearchHit]

class FetchInput(BaseModel):
    id: str = Field(..., description="Use 'task:<id>' or 'project:<id>'")

class FetchOutput(BaseModel):
    id: str
    title: str
    text: str
    url: str
    metadata: Optional[Dict[str, Any]] = None

# ---------- Helpers ----------
def _safe(s: Optional[str]) -> str:
    return s or ""

def _task_url(task_id: str) -> str:
    return f"https://todoist.com/showTask?id={task_id}"

def _project_url(project_id: str) -> str:
    return f"https://app.todoist.com/app/project/{project_id}"

# ---------- Tool handlers ----------
async def handle_search(data: SearchInput) -> List[SearchHit]:
    """
    Returns up to 10 mixed results across open tasks and projects.
    - Tasks: /tasks?filter=<query> (Todoist filter syntax)
    - Projects: client-side name contains query
    """
    q = data.query.strip()
    # Quote multi-word queries to align with Todoist filter parsing
    flt = q if " " not in q else f'"{q}"'

    hits: Dict[str, SearchHit] = {}

    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
        # Tasks (open)
        r1 = await client.get(f"{BASE_URL}/tasks", params={"filter": flt})
        r1.raise_for_status()
        for t in r1.json():
            tid = str(t["id"])
            content = _safe(t.get("content"))
            due = t.get("due", {}) or {}
            pdue = due.get("date")
            prio = t.get("priority")
            labels = t.get("labels") or []
            bits = []
            if pdue:
                bits.append(f"due {pdue}")
            if prio:
                bits.append(f"p{prio}")
            if labels:
                bits.append("labels:" + ",".join(labels))
            text = content + (f"  ({'; '.join(bits)})" if bits else "")
            hits[f"task:{tid}"] = SearchHit(
                id=f"task:{tid}",
                title=content or f"Task {tid}",
                text=text,
                url=_task_url(tid),
            )

        # Projects (name contains query)
        r2 = await client.get(f"{BASE_URL}/projects")
        r2.raise_for_status()
        for p in r2.json():
            pid = str(p["id"])
            name = _safe(p.get("name"))
            if q.lower() in name.lower():
                hits[f"project:{pid}"] = SearchHit(
                    id=f"project:{pid}",
                    title=name or f"Project {pid}",
                    text=name,
                    url=_project_url(pid),
                )

    # Return at most 10 for snappy DR UX
    return list(hits.values())[:10]

async def handle_fetch(data: FetchInput) -> FetchOutput:
    """
    Fetch a single task or project by prefixed id.
    """
    if data.id.startswith("task:"):
        tid = data.id.split(":", 1)[1]
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
            r = await client.get(f"{BASE_URL}/tasks/{tid}")
            r.raise_for_status()
            t = r.json()
        title = _safe(t.get("content"))
        meta = {
            "due": t.get("due"),
            "priority": t.get("priority"),
            "labels": t.get("labels"),
            "project_id": t.get("project_id"),
            "section_id": t.get("section_id"),
            "completed": t.get("is_completed"),
            "created_at": t.get("created_at"),
            "url": _task_url(tid),
        }
        return FetchOutput(
            id=f"task:{tid}",
            title=title or f"Task {tid}",
            text=title,
            url=_task_url(tid),
            metadata=meta,
        )

    if data.id.startswith("project:"):
        pid = data.id.split(":", 1)[1]
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
            r = await client.get(f"{BASE_URL}/projects/{pid}")
            r.raise_for_status()
            p = r.json()
        name = _safe(p.get("name"))
        meta = {
            "color": p.get("color"),
            "is_favorite": p.get("is_favorite"),
            "view_style": p.get("view_style"),
            "url": _project_url(pid),
        }
        return FetchOutput(
            id=f"project:{pid}",
            title=name or f"Project {pid}",
            text=name,
            url=_project_url(pid),
            metadata=meta,
        )

    raise ValueError("id must start with 'task:' or 'project:'")

# ---------- FastMCP app (SSE tools only) ----------
app = FastMCP(
    "todoist-mcp",
    tools=[
        Tool(
            name="search",
            description="Search Todoist tasks and projects by free-text query",
            input_model=SearchInput,
            output_model=SearchOutput,
            handler=handle_search,
            transport="sse",
        ),
        Tool(
            name="fetch",
            description="Fetch full details for a Todoist task or project",
            input_model=FetchInput,
            output_model=FetchOutput,
            handler=handle_fetch,
            transport="sse",
        ),
    ],
).app  # FastAPI app

# CORS for ChatGPT browser client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health route for Fly checks
fastapi_app: FastAPI = app  # type: ignore
@fastapi_app.get("/health")
async def health():
    return {"ok": True}

# Uvicorn entrypoint for local dev is intentionally omitted (cloud-only)