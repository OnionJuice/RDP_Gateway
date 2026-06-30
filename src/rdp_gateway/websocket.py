from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import struct
from dataclasses import dataclass
from typing import Iterable

from .http import HttpRequest

logger = logging.getLogger(__name__)

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@dataclass(frozen=True)
class WebSocketFrame:
    fin: bool
    opcode: int
    payload: bytes


def is_websocket_upgrade(request: HttpRequest) -> bool:
    headers = _lower_headers(request.headers)
    connection_tokens = {
        token.strip().lower()
        for token in headers.get("connection", "").split(",")
        if token.strip()
    }
    return (
        headers.get("upgrade", "").lower() == "websocket"
        and "upgrade" in connection_tokens
        and "sec-websocket-key" in headers
    )


async def accept_websocket(
    writer: asyncio.StreamWriter,
    request: HttpRequest,
    *,
    protocols: Iterable[str] = ("binary",),
) -> None:
    headers = _lower_headers(request.headers)
    key = headers["sec-websocket-key"]
    accept = base64.b64encode(
        hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()
    ).decode("ascii")

    requested_protocols = [
        item.strip()
        for item in headers.get("sec-websocket-protocol", "").split(",")
        if item.strip()
    ]
    selected_protocol = next(
        (protocol for protocol in protocols if protocol in requested_protocols),
        None,
    )
    response_headers = [
        ("Upgrade", "websocket"),
        ("Connection", "Upgrade"),
        ("Sec-WebSocket-Accept", accept),
    ]
    if selected_protocol is not None:
        response_headers.append(("Sec-WebSocket-Protocol", selected_protocol))

    header_text = "".join(f"{name}: {value}\r\n" for name, value in response_headers)
    writer.write(f"HTTP/1.1 101 Switching Protocols\r\n{header_text}\r\n".encode("ascii"))
    await writer.drain()


async def read_frame(
    reader: asyncio.StreamReader,
    *,
    timeout_seconds: float,
    max_payload_bytes: int = 16 * 1024 * 1024,
) -> WebSocketFrame:
    first_two = await _read_exactly(reader, 2, timeout_seconds=timeout_seconds)
    byte1, byte2 = first_two
    fin = bool(byte1 & 0x80)
    opcode = byte1 & 0x0F
    masked = bool(byte2 & 0x80)
    length = byte2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", await _read_exactly(reader, 2, timeout_seconds=timeout_seconds))[0]
    elif length == 127:
        length = struct.unpack("!Q", await _read_exactly(reader, 8, timeout_seconds=timeout_seconds))[0]

    if length > max_payload_bytes:
        raise ValueError(f"WebSocket frame too large: {length} bytes")

    mask = b""
    if masked:
        mask = await _read_exactly(reader, 4, timeout_seconds=timeout_seconds)
    payload = await _read_exactly(reader, length, timeout_seconds=timeout_seconds)
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return WebSocketFrame(fin=fin, opcode=opcode, payload=payload)


async def write_frame(
    writer: asyncio.StreamWriter,
    opcode: int,
    payload: bytes = b"",
    *,
    mask: bool = False,
) -> None:
    first = 0x80 | (opcode & 0x0F)
    header = bytearray([first])
    length = len(payload)
    if length < 126:
        header.append((0x80 if mask else 0) | length)
    elif length <= 0xFFFF:
        header.append((0x80 if mask else 0) | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append((0x80 if mask else 0) | 127)
        header.extend(struct.pack("!Q", length))

    if mask:
        mask_key = os.urandom(4)
        header.extend(mask_key)
        payload = bytes(value ^ mask_key[index % 4] for index, value in enumerate(payload))
    writer.write(bytes(header) + payload)
    await writer.drain()


def payload_preview(payload: bytes, *, limit: int = 96) -> str:
    sample = payload[:limit]
    hex_part = sample.hex(" ")
    utf16 = _decode_preview(sample, "utf-16-le")
    latin1 = _decode_preview(sample, "latin-1")
    extras = []
    if utf16:
        extras.append(f"utf16le={utf16!r}")
    if latin1:
        extras.append(f"latin1={latin1!r}")
    suffix = " ".join(extras)
    return f"len={len(payload)} hex={hex_part}{' ' + suffix if suffix else ''}"


async def _read_exactly(
    reader: asyncio.StreamReader,
    count: int,
    *,
    timeout_seconds: float,
) -> bytes:
    try:
        return await asyncio.wait_for(reader.readexactly(count), timeout=timeout_seconds)
    except asyncio.IncompleteReadError as exc:
        raise EOFError("WebSocket connection closed") from exc
    except asyncio.TimeoutError as exc:
        raise TimeoutError("timed out waiting for WebSocket frame data") from exc


def _lower_headers(headers: dict[str, str]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


def _decode_preview(payload: bytes, encoding: str) -> str:
    try:
        text = payload.decode(encoding, errors="ignore")
    except Exception:
        return ""
    printable = "".join(ch if 32 <= ord(ch) < 127 else "." for ch in text)
    printable = " ".join(printable.split())
    return printable[:120]
