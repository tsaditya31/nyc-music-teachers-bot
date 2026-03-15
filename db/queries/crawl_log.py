"""Crawl log queries."""
from __future__ import annotations

from db.connection import get_pool


async def start_crawl(source_id: int) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO crawl_log (source_id) VALUES ($1) RETURNING id",
        source_id,
    )
    return row["id"]


async def finish_crawl(
    crawl_id: int,
    status: str = "success",
    pages_crawled: int = 0,
    activities_found: int = 0,
    activities_new: int = 0,
    activities_updated: int = 0,
    tokens_used: int = 0,
    error_message: str | None = None,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE crawl_log SET
            finished_at = NOW(),
            status = $2,
            pages_crawled = $3,
            activities_found = $4,
            activities_new = $5,
            activities_updated = $6,
            tokens_used = $7,
            error_message = $8
        WHERE id = $1
        """,
        crawl_id, status, pages_crawled, activities_found,
        activities_new, activities_updated, tokens_used, error_message,
    )


async def recent_crawls(limit: int = 10) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT cl.*, s.url as source_url, s.name as source_name
        FROM crawl_log cl
        JOIN sources s ON cl.source_id = s.id
        ORDER BY cl.started_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]
