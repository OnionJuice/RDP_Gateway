from __future__ import annotations

import asyncio
import contextlib
import logging

logger = logging.getLogger(__name__)


async def relay_bidirectional(
    left_reader: asyncio.StreamReader,
    left_writer: asyncio.StreamWriter,
    right_reader: asyncio.StreamReader,
    right_writer: asyncio.StreamWriter,
) -> None:
    left_to_right = asyncio.create_task(_pipe(left_reader, right_writer, "client->target"))
    right_to_left = asyncio.create_task(_pipe(right_reader, left_writer, "target->client"))
    done, pending = await asyncio.wait(
        {left_to_right, right_to_left}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    for task in done:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await asyncio.gather(*pending, return_exceptions=True)
    await _close_writer(left_writer)
    await _close_writer(right_writer)


async def _pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    direction: str,
) -> None:
    while True:
        data = await reader.read(64 * 1024)
        if not data:
            logger.debug("relay closed: %s", direction)
            break
        writer.write(data)
        await writer.drain()


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
