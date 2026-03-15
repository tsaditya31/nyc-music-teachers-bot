"""Activity CRUD and search queries."""
from __future__ import annotations

from db.connection import get_pool


async def search_activities(
    query: str | None = None,
    category: str | None = None,
    borough: str | None = None,
    neighborhood: str | None = None,
    zip_code: str | None = None,
    age: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """Search activities with optional filters. Uses trigram similarity for text search."""
    pool = await get_pool()
    conditions = ["a.status = 'active'"]
    params = []
    i = 1

    if query:
        conditions.append(
            f"(a.name ILIKE '%' || ${i} || '%' OR a.description ILIKE '%' || ${i} || '%' "
            f"OR a.category ILIKE '%' || ${i} || '%' OR a.tags::text ILIKE '%' || ${i} || '%')"
        )
        params.append(query)
        i += 1

    if category:
        conditions.append(f"a.category ILIKE '%' || ${i} || '%'")
        params.append(category)
        i += 1

    if borough:
        conditions.append(f"a.borough ILIKE ${i}")
        params.append(borough)
        i += 1

    if neighborhood:
        conditions.append(f"a.neighborhood ILIKE ${i}")
        params.append(neighborhood)
        i += 1

    if zip_code:
        conditions.append(f"a.zip_code = ${i}")
        params.append(zip_code)
        i += 1

    if age:
        conditions.append(f"a.age_range ILIKE '%' || ${i} || '%'")
        params.append(age)
        i += 1

    where = " AND ".join(conditions)
    params.append(limit)

    sql = f"""
        SELECT a.*, s.name as source_name
        FROM activities a
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE {where}
        ORDER BY a.last_seen_at DESC
        LIMIT ${i}
    """
    rows = await pool.fetch(sql, *params)
    return [dict(r) for r in rows]


async def upsert_activity(
    name: str,
    source_url: str | None = None,
    source_id: int | None = None,
    **kwargs,
) -> tuple[int, bool]:
    """Insert or update activity. Returns (id, is_new)."""
    pool = await get_pool()
    address = kwargs.get("address")

    # Try to find existing
    existing = None
    if name and address and source_url:
        existing = await pool.fetchrow(
            "SELECT id FROM activities WHERE name = $1 AND address = $2 AND source_url = $3",
            name, address, source_url,
        )
    elif name and source_url:
        existing = await pool.fetchrow(
            "SELECT id FROM activities WHERE name = $1 AND source_url = $2",
            name, source_url,
        )

    if existing:
        # Update existing
        sets = ["last_seen_at = NOW()", "updated_at = NOW()", "status = 'active'"]
        vals = []
        i = 1
        for key, val in kwargs.items():
            if val is not None:
                sets.append(f"{key} = ${i}")
                vals.append(val)
                i += 1
        vals.append(existing["id"])
        sql = f"UPDATE activities SET {', '.join(sets)} WHERE id = ${i}"
        await pool.execute(sql, *vals)
        return existing["id"], False

    # Insert new
    fields = ["name", "source_url", "source_id"]
    values = [name, source_url, source_id]
    for key, val in kwargs.items():
        if val is not None:
            fields.append(key)
            values.append(val)

    placeholders = ", ".join(f"${j+1}" for j in range(len(values)))
    sql = f"""
        INSERT INTO activities ({', '.join(fields)})
        VALUES ({placeholders})
        ON CONFLICT (name, address, source_url) DO UPDATE
        SET last_seen_at = NOW(), updated_at = NOW(), status = 'active'
        RETURNING id
    """
    try:
        row = await pool.fetchrow(sql, *values)
        return row["id"], True
    except Exception:
        # If unique constraint fails, try without address constraint
        sql_simple = f"""
            INSERT INTO activities ({', '.join(fields)})
            VALUES ({placeholders})
            RETURNING id
        """
        row = await pool.fetchrow(sql_simple, *values)
        return row["id"], True


async def expire_old_activities(days: int) -> int:
    """Mark activities not seen in `days` as expired. Returns count."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE activities SET status = 'expired', updated_at = NOW()
        WHERE status = 'active'
          AND last_seen_at < NOW() - INTERVAL '1 day' * $1
        """,
        days,
    )
    # result is like "UPDATE 5"
    return int(result.split()[-1]) if result else 0


async def count_activities(status: str = "active") -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM activities WHERE status = $1", status
    )
    return row["cnt"]


async def get_stats() -> dict:
    """Get summary statistics."""
    pool = await get_pool()
    activities = await pool.fetchrow(
        "SELECT COUNT(*) as total, COUNT(DISTINCT category) as categories, "
        "COUNT(DISTINCT borough) as boroughs FROM activities WHERE status = 'active'"
    )
    sources = await pool.fetchrow(
        "SELECT COUNT(*) as total, "
        "COUNT(*) FILTER (WHERE status = 'active') as active "
        "FROM sources"
    )
    return {
        "total_activities": activities["total"],
        "categories": activities["categories"],
        "boroughs": activities["boroughs"],
        "total_sources": sources["total"],
        "active_sources": sources["active"],
    }
