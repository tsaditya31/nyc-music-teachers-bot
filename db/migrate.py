"""Run database migrations: create schema and seed neighborhoods."""

import asyncio
import json
import os
import sys

# Allow running as standalone script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
import config


async def run_migrations():
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        # Read and execute schema
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path) as f:
            schema_sql = f.read()
        await conn.execute(schema_sql)
        print("Schema created/verified.")

        # Seed neighborhoods
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "nyc_neighborhoods.json"
        )
        with open(data_path) as f:
            neighborhoods = json.load(f)

        count = 0
        for entry in neighborhoods:
            await conn.execute(
                """
                INSERT INTO neighborhoods (zip_code, neighborhood, borough)
                VALUES ($1, $2, $3)
                ON CONFLICT (zip_code) DO UPDATE
                SET neighborhood = EXCLUDED.neighborhood,
                    borough = EXCLUDED.borough
                """,
                entry["zip_code"],
                entry["neighborhood"],
                entry["borough"],
            )
            count += 1
        print(f"Seeded {count} neighborhoods.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
