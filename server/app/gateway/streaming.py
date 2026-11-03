"""Prefetch without losing cancellation before SSE headers have been sent."""
import asyncio
from contextlib import suppress

from .service import usage_context


async def prepare_first_chunk(stream, is_disconnected, user_id):
    async def first():
        with usage_context(user_id, 'chat'):
            return await anext(stream)
    task = asyncio.create_task(first())
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.1)
            if task in done:
                return task.result()
            if await is_disconnected():
                raise asyncio.CancelledError()
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
