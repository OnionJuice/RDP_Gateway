from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

MAX_HEADER_BYTES = 64 * 1024


@dataclass(frozen=True)
class HttpRequest:
    method: str
    target: str
    version: str
    headers: dict[str, str]
    raw_header_bytes: bytes


async def read_http_request(
    reader: asyncio.StreamReader, *, timeout_seconds: float
) -> HttpRequest:
    try:
        data = await asyncio.wait_for(
            reader.readuntil(b"\r\n\r\n"), timeout=timeout_seconds
        )
    except asyncio.LimitOverrunError as exc:
        raise ValueError("HTTP headers exceed parser limit") from exc
    except asyncio.IncompleteReadError as exc:
        raise ValueError("connection closed before complete HTTP headers") from exc
    except asyncio.TimeoutError as exc:
        raise ValueError("timed out waiting for HTTP headers") from exc

    if len(data) > MAX_HEADER_BYTES:
        raise ValueError("HTTP headers too large")

    try:
        text = data.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise ValueError("HTTP headers are not decodable") from exc

    lines = text.split("\r\n")
    request_line = lines[0]
    parts = request_line.split(" ")
    if len(parts) != 3:
        raise ValueError("invalid HTTP request line")

    method, target, version = parts
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"invalid HTTP header line: {line!r}")
        headers[name.strip()] = value.strip()

    return HttpRequest(
        method=method.upper(),
        target=target,
        version=version,
        headers=headers,
        raw_header_bytes=data,
    )


async def write_response(
    writer: asyncio.StreamWriter,
    status_code: int,
    reason: str,
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
    close: bool = True,
) -> None:
    extra_headers = list(headers)
    has_connection = any(name.lower() == "connection" for name, _value in extra_headers)
    response_headers = [
        ("Content-Length", str(len(body))),
        *([] if has_connection else [("Connection", "close" if close else "keep-alive")]),
        *extra_headers,
    ]
    header_text = "".join(f"{name}: {value}\r\n" for name, value in response_headers)
    writer.write(
        f"HTTP/1.1 {status_code} {reason}\r\n{header_text}\r\n".encode("ascii") + body
    )
    await writer.drain()
