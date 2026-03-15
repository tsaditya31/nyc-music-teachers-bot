"""Serial execution queue for heartbeat tasks."""

import asyncio
import logging
from collections import deque
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)


class Lane:
    """Executes async tasks one at a time in FIFO order."""

    def __init__(self):
        self._queue: deque[tuple[str, Callable[[], Coroutine[Any, Any, Any]]]] = deque()
        self._running = False

    def enqueue(self, name: str, coro_fn: Callable[[], Coroutine[Any, Any, Any]]):
        """Add a task to the queue. coro_fn is a zero-arg async callable."""
        self._queue.append((name, coro_fn))
        logger.info(f"Lane: enqueued '{name}' (queue size: {len(self._queue)})")

    async def drain(self):
        """Execute all queued tasks serially."""
        self._running = True
        while self._queue:
            name, coro_fn = self._queue.popleft()
            logger.info(f"Lane: executing '{name}'")
            try:
                await coro_fn()
                logger.info(f"Lane: completed '{name}'")
            except Exception:
                logger.exception(f"Lane: failed '{name}'")
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def pending_count(self) -> int:
        return len(self._queue)
