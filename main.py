"""Entry point: starts health server, DB pool, heartbeat, and Telegram bot."""

import asyncio
import logging
import os

from aiohttp import web

import config
from db.connection import get_pool, close_pool
from db.migrate import run_migrations
from db.queries.sources import insert_source
from gateway.telegram import build_application
from heartbeat.loop import HeartbeatLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Health check HTTP server ──────────────────────────────────────────

async def _health(request):
    return web.Response(text="ok")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.PORT)
    await site.start()
    logger.info(f"Health server listening on :{config.PORT}")
    return runner


# ── Seed sources ──────────────────────────────────────────────────────

SEED_SOURCES = [
    {
        "url": "https://mommypoppins.com/new-york-city-kids/classes",
        "name": "MommyPoppins NYC Classes",
        "status": "active",
        "discovered_by": "seed",
        "category": "general",
    },
    {
        "url": "https://www.macaronikid.com/manhattan",
        "name": "Macaroni Kid Manhattan",
        "status": "active",
        "discovered_by": "seed",
        "category": "general",
    },
]


async def seed_sources():
    for src in SEED_SOURCES:
        await insert_source(**src)
    logger.info(f"Seeded {len(SEED_SOURCES)} sources")


# ── Main ──────────────────────────────────────────────────────────────

async def main():
    # 1. Run migrations
    logger.info("Running migrations...")
    await run_migrations()

    # 2. Initialize connection pool
    await get_pool()
    logger.info("Database pool ready")

    # 3. Seed sources
    await seed_sources()

    # 4. Start health server
    health_runner = await start_health_server()

    # 5. Start heartbeat
    heartbeat = HeartbeatLoop()
    heartbeat.start()

    # 6. Start Telegram bot (blocking)
    logger.info("Starting Telegram bot...")
    app = build_application()
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running. Press Ctrl+C to stop.")

        # Keep running until interrupted
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            heartbeat.stop()
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            await health_runner.cleanup()
            await close_pool()
            logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
