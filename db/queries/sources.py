"""Source CRUD queries."""
from __future__ import annotations

from db.connection import get_pool


async def get_source(source_id: int) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM sources WHERE id = $1", source_id)
    return dict(row) if row else None


async def get_source_by_url(url: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM sources WHERE url = $1", url)
    return dict(row) if row else None


async def list_sources(status: str | None = None) -> list[dict]:
    pool = await get_pool()
    if status:
        rows = await pool.fetch(
            "SELECT * FROM sources WHERE status = $1 ORDER BY created_at", status
        )
    else:
        rows = await pool.fetch("SELECT * FROM sources ORDER BY created_at")
    return [dict(r) for r in rows]


async def insert_source(
    url: str,
    name: str | None = None,
    status: str = "pending",
    discovered_by: str = "seed",
    category: str | None = None,
    notes: str | None = None,
) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO sources (url, name, status, discovered_by, category, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (url) DO NOTHING
        RETURNING id
        """,
        url, name, status, discovered_by, category, notes,
    )
    if row:
        return row["id"]
    # Already exists
    existing = await get_source_by_url(url)
    return existing["id"] if existing else -1


async def update_source(source_id: int, **kwargs) -> None:
    pool = await get_pool()
    sets = []
    vals = []
    i = 1
    for key, val in kwargs.items():
        sets.append(f"{key} = ${i}")
        vals.append(val)
        i += 1
    sets.append(f"updated_at = NOW()")
    vals.append(source_id)
    sql = f"UPDATE sources SET {', '.join(sets)} WHERE id = ${i}"
    await pool.execute(sql, *vals)


async def get_stale_sources(hours: int) -> list[dict]:
    """Get active sources that haven't been crawled in `hours` hours."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM sources
        WHERE status = 'active'
          AND (last_crawled_at IS NULL OR last_crawled_at < NOW() - INTERVAL '1 hour' * $1)
        ORDER BY last_crawled_at ASC NULLS FIRST
        """,
        hours,
    )
    return [dict(r) for r in rows]


async def get_pending_sources() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM sources WHERE status = 'pending' ORDER BY created_at LIMIT 5"
    )
    return [dict(r) for r in rows]
