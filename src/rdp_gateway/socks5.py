from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass


class Socks5Error(OSError):
    pass


@dataclass(frozen=True)
class Socks5Endpoint:
    host: str
    port: int


_REPLY_NAMES = {
    0x01: "general SOCKS server failure",
    0x02: "connection not allowed by ruleset",
    0x03: "network unreachable",
    0x04: "host unreachable",
    0x05: "connection refused",
    0x06: "TTL expired",
    0x07: "command not supported",
    0x08: "address type not supported",
}


async def open_connection_via_socks5(
    socks: Socks5Endpoint,
    target: Socks5Endpoint,
    *,
    timeout_seconds: float,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(socks.host, socks.port),
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise Socks5Error(f"failed to connect to SOCKS5 proxy {socks.host}:{socks.port}") from exc

    try:
        await _handshake(reader, writer, timeout_seconds=timeout_seconds)
        await _connect(reader, writer, target, timeout_seconds=timeout_seconds)
    except Exception:
        writer.close()
        await writer.wait_closed()
        raise

    return reader, writer


async def _handshake(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    timeout_seconds: float,
) -> None:
    writer.write(b"\x05\x01\x00")
    await writer.drain()
    response = await _read_exactly(reader, 2, timeout_seconds=timeout_seconds)
    if response != b"\x05\x00":
        raise Socks5Error(f"SOCKS5 proxy rejected no-auth handshake: {response!r}")


async def _connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    target: Socks5Endpoint,
    *,
    timeout_seconds: float,
) -> None:
    host_bytes = _encode_host(target.host)
    port_bytes = target.port.to_bytes(2, "big")
    writer.write(b"\x05\x01\x00" + host_bytes + port_bytes)
    await writer.drain()

    head = await _read_exactly(reader, 4, timeout_seconds=timeout_seconds)
    version, reply, _reserved, atyp = head
    if version != 0x05:
        raise Socks5Error(f"invalid SOCKS5 reply version: {version}")
    if reply != 0x00:
        detail = _REPLY_NAMES.get(reply, f"unknown reply 0x{reply:02x}")
        raise Socks5Error(f"SOCKS5 CONNECT failed: {detail}")

    if atyp == 0x01:
        await _read_exactly(reader, 4, timeout_seconds=timeout_seconds)
    elif atyp == 0x03:
        size = await _read_exactly(reader, 1, timeout_seconds=timeout_seconds)
        await _read_exactly(reader, size[0], timeout_seconds=timeout_seconds)
    elif atyp == 0x04:
        await _read_exactly(reader, 16, timeout_seconds=timeout_seconds)
    else:
        raise Socks5Error(f"invalid SOCKS5 bound address type: {atyp}")
    await _read_exactly(reader, 2, timeout_seconds=timeout_seconds)


def _encode_host(host: str) -> bytes:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        encoded = host.encode("idna")
        if len(encoded) > 255:
            raise Socks5Error("target hostname is too long for SOCKS5")
        return b"\x03" + bytes([len(encoded)]) + encoded

    if ip.version == 4:
        return b"\x01" + socket.inet_aton(host)
    return b"\x04" + ip.packed


async def _read_exactly(
    reader: asyncio.StreamReader, count: int, *, timeout_seconds: float
) -> bytes:
    try:
        return await asyncio.wait_for(reader.readexactly(count), timeout=timeout_seconds)
    except asyncio.IncompleteReadError as exc:
        raise Socks5Error("SOCKS5 proxy closed the connection early") from exc
    except asyncio.TimeoutError as exc:
        raise Socks5Error("timed out waiting for SOCKS5 proxy") from exc
