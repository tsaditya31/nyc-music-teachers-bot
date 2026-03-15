"""Skill: Sources CRUD operations."""
from __future__ import annotations

import json
from brain.orchestrator import register_skill
from db.queries import sources


@register_skill({
    "name": "manage_sources",
    "description": "Manage crawl sources: add new sources, update status, list sources. Actions: 'add', 'update', 'list', 'get_stale', 'get_pending'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "update", "list", "get_stale", "get_pending"],
                "description": "The action to perform",
            },
            "url": {"type": "string", "description": "Source URL (for add)"},
            "name": {"type": "string", "description": "Source name (for add)"},
            "source_id": {"type": "integer", "description": "Source ID (for update)"},
            "status": {"type": "string", "description": "Source status (for add/update/list filter)"},
            "discovered_by": {"type": "string", "description": "seed or agent (for add)"},
            "category": {"type": "string", "description": "Activity category (for add)"},
            "notes": {"type": "string", "description": "Notes (for add/update)"},
            "reliability_score": {"type": "number", "description": "Score 0-1 (for update)"},
            "stale_hours": {"type": "integer", "description": "Hours threshold (for get_stale)"},
        },
        "required": ["action"],
    },
})
async def manage_sources_skill(
    action: str,
    url: str | None = None,
    name: str | None = None,
    source_id: int | None = None,
    status: str | None = None,
    discovered_by: str = "agent",
    category: str | None = None,
    notes: str | None = None,
    reliability_score: float | None = None,
    stale_hours: int = 24,
) -> str:
    if action == "add":
        if not url:
            return json.dumps({"error": "url is required for add action"})
        sid = await sources.insert_source(
            url=url,
            name=name,
            status=status or "pending",
            discovered_by=discovered_by,
            category=category,
            notes=notes,
        )
        return json.dumps({"source_id": sid, "action": "added"})

    elif action == "update":
        if not source_id:
            return json.dumps({"error": "source_id is required for update action"})
        kwargs = {}
        if status:
            kwargs["status"] = status
        if notes:
            kwargs["notes"] = notes
        if reliability_score is not None:
            kwargs["reliability_score"] = reliability_score
        if name:
            kwargs["name"] = name
        if category:
            kwargs["category"] = category
        await sources.update_source(source_id, **kwargs)
        return json.dumps({"source_id": source_id, "action": "updated"})

    elif action == "list":
        result = await sources.list_sources(status=status)
        return json.dumps({"sources": result, "count": len(result)}, default=str)

    elif action == "get_stale":
        result = await sources.get_stale_sources(stale_hours)
        return json.dumps({"sources": result, "count": len(result)}, default=str)

    elif action == "get_pending":
        result = await sources.get_pending_sources()
        return json.dumps({"sources": result, "count": len(result)}, default=str)

    else:
        return json.dumps({"error": f"Unknown action: {action}"})
