"""Malware scan through clamd's INSTREAM command. Every upload is scanned before it is stored."""

from __future__ import annotations

import asyncio
import os
import struct

CLAMD_HOST = os.environ.get("CLAMD_HOST", "clamav")
CLAMD_PORT = int(os.environ.get("CLAMD_PORT", "3310"))
_CHUNK = 64 * 1024


class ScannerUnavailable(Exception):
    pass


async def scan(content: bytes, timeout: float = 30.0) -> str | None:
    """Returns the signature name if the content is infected, None if it is clean."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(CLAMD_HOST, CLAMD_PORT), timeout=5)
    except (OSError, asyncio.TimeoutError) as exc:
        raise ScannerUnavailable(f"cannot reach clamd at {CLAMD_HOST}:{CLAMD_PORT}") from exc
    try:
        writer.write(b"zINSTREAM\0")
        for start in range(0, len(content), _CHUNK):
            chunk = content[start:start + _CHUNK]
            writer.write(struct.pack("!L", len(chunk)) + chunk)
        writer.write(struct.pack("!L", 0))
        await writer.drain()
        reply = (await asyncio.wait_for(reader.readuntil(b"\0"), timeout=timeout)).rstrip(b"\0").decode()
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
        raise ScannerUnavailable("clamd did not answer") from exc
    finally:
        writer.close()

    # Replies: "stream: OK", "stream: <Signature> FOUND", or "<message> ERROR".
    if reply.endswith("OK"):
        return None
    if reply.endswith("FOUND"):
        return reply.removeprefix("stream:").removesuffix("FOUND").strip()
    raise ScannerUnavailable(f"clamd error: {reply}")
