"""Skill: Search activities database."""
from __future__ import annotations

import json
from brain.orchestrator import register_skill
from db.queries import activities


@register_skill({
    "name": "search_activities",
    "description": "Search the database for kids activities by keyword, category, borough, neighborhood, ZIP code, or age range. Returns up to 15 matching results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free text search (name, description, tags)",
            },
            "category": {
                "type": "string",
                "description": "Activity category (music, sports, art, STEM, dance, theater, coding, etc.)",
            },
            "borough": {
                "type": "string",
                "description": "NYC borough (Manhattan, Brooklyn, Queens, Bronx, Staten Island)",
            },
            "neighborhood": {
                "type": "string",
                "description": "NYC neighborhood name",
            },
            "zip_code": {
                "type": "string",
                "description": "NYC ZIP code",
            },
            "age": {
                "type": "string",
                "description": "Age or age range to filter by",
            },
        },
    },
})
async def search_activities_skill(
    query: str | None = None,
    category: str | None = None,
    borough: str | None = None,
    neighborhood: str | None = None,
    zip_code: str | None = None,
    age: str | None = None,
) -> str:
    results = await activities.search_activities(
        query=query,
        category=category,
        borough=borough,
        neighborhood=neighborhood,
        zip_code=zip_code,
        age=age,
    )
    if not results:
        return json.dumps({"results": [], "message": "No activities found matching your criteria."})

    # Slim down for Claude context
    slim = []
    for r in results:
        slim.append({
            "id": r["id"],
            "name": r["name"],
            "category": r.get("category"),
            "subcategory": r.get("subcategory"),
            "age_range": r.get("age_range"),
            "location": r.get("location_name"),
            "address": r.get("address"),
            "neighborhood": r.get("neighborhood"),
            "borough": r.get("borough"),
            "price": r.get("price"),
            "schedule": r.get("schedule"),
            "website": r.get("website"),
            "description": (r.get("description") or "")[:200],
        })
    return json.dumps({"results": slim, "count": len(slim)}, default=str)


@register_skill({
    "name": "get_stats",
    "description": "Get summary statistics about the activities database (total activities, categories, boroughs, sources).",
    "input_schema": {"type": "object", "properties": {}},
})
async def get_stats_skill() -> str:
    stats = await activities.get_stats()
    return json.dumps(stats, default=str)
