"""Background async heartbeat loop."""
from __future__ import annotations

import asyncio
import logging

import config
from heartbeat.lane import Lane
from heartbeat.tasks import (
    crawl_stale_sources,
    evaluate_pending_sources,
    discover_new_sources,
    expire_old_activities,
)

logger = logging.getLogger(__name__)


class HeartbeatLoop:
    def __init__(self):
        self.lane = Lane()
        self._cycle = 0
        self._task: asyncio.Task | None = None
        self._category_index = 0

    def start(self):
        """Start the heartbeat loop as a background task."""
        self._task = asyncio.create_task(self._run())
        logger.info("Heartbeat loop started")

    async def _run(self):
        # Initial delay to let the system start up
        await asyncio.sleep(30)

        while True:
            try:
                self._cycle += 1
                logger.info(f"Heartbeat cycle {self._cycle}")

                # Every cycle: crawl stale + evaluate pending
                self.lane.enqueue("crawl_stale", crawl_stale_sources)
                self.lane.enqueue("evaluate_pending", evaluate_pending_sources)

                # Every 6th cycle: discover new sources
                if self._cycle % config.DISCOVERY_INTERVAL_CYCLES == 0:
                    category = config.ACTIVITY_CATEGORIES[
                        self._category_index % len(config.ACTIVITY_CATEGORIES)
                    ]
                    self._category_index += 1
                    self.lane.enqueue(
                        f"discover_{category}",
                        lambda cat=category: discover_new_sources(cat),
                    )

                # Every 24th cycle: expire old activities
                if self._cycle % config.EXPIRE_INTERVAL_CYCLES == 0:
                    self.lane.enqueue("expire_old", expire_old_activities)

                # Drain the queue
                await self.lane.drain()

            except Exception:
                logger.exception(f"Heartbeat cycle {self._cycle} error")

            await asyncio.sleep(config.HEARTBEAT_INTERVAL_SECONDS)

    def stop(self):
        if self._task:
            self._task.cancel()
            logger.info("Heartbeat loop stopped")
