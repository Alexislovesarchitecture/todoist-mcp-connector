"""
Todoist MCP Connector – minimal, single‑user, read‑only.

Implements:
  • search(query:str)  -> {results: [...]}   (max 25 hits)
  • fetch(id:str)      -> {id, title, text, url, metadata}

For production (multi‑user & OAuth) see Section 9.
"""

# ---------- Imports & setup ----------
import os, re
from dotenv import load_dotenv
from fastmcp import FastMCP
from todoist_api_python.api import TodoistAPI

load_dotenv()
TOKEN = os.getenv("TODOIST_API_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "Define TODOIST_API_TOKEN in .env (see README).")

todoist = TodoistAPI(TOKEN)

# ---------- FastMCP boilerplate ----------
SERVER_INSTRUCTIONS = (
    "This connector lets ChatGPT search and fetch your Todoist tasks. "
    "Use search to find tasks by keyword, then fetch the ID for details."
)

def create_server() -> FastMCP:
    mcp = FastMCP(
        name="Todoist Deep‑Research Connector",
        instructions=SERVER_INSTRUCTIONS,
    )

    # ----- search -----
    @mcp.tool()
    async def search(query: str):
        """
        Return tasks whose content OR description contains `query`
        (case‑insensitive). Max 25 results.
        """
        if not query or not query.strip():
            return {"results": []}

        pattern = re.compile(re.escape(query), re.I)

        tasks = await todoist.get_tasks()
        hits = [
            {
                "id": task.id,
                "title": task.content,
                "text": (task.description or "")[:200],
                "url": f"https://todoist.com/showTask?id={task.id}",
            }
            for task in tasks
            if pattern.search(task.content) or pattern.search(task.description or "")
        ]

        return {"results": hits[:25]}

    # ----- fetch -----
    @mcp.tool()
    async def fetch(id: str):
        """
        Return full details for a task (or project fallback).
        """
        # Try task first
        try:
            t = await todoist.get_task(id)
            return {
                "id": t.id,
                "title": t.content,
                "text": t.description or "",
                "url": f"https://todoist.com/showTask?id={t.id}",
                "metadata": {
                    "due": t.due.date if t.due else None,
                    "project_id": t.project_id,
                    "labels": t.labels,
                    "priority": t.priority,
                },
            }
        except Exception:
            # Fallback: maybe it's a project ID
            try:
                p = await todoist.get_project(id)
                return {
                    "id": p.id,
                    "title": p.name,
                    "text": "",
                    "url": f"https://todoist.com/app/project/{p.id}",
                    "metadata": {"color": p.color, "shared": p.shared},
                }
            except Exception as e:
                from fastapi import HTTPException
                raise HTTPException(404, f"Todoist item {id} not found") from e

    return mcp

# ---------- entrypoint ----------
if __name__ == "__main__":
    create_server().run(
        transport="sse",
        host="0.0.0.0",
        port=8000,
    )