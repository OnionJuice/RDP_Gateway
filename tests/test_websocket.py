import asyncio
import base64
import hashlib

from rdp_gateway.http import HttpRequest
from rdp_gateway.websocket import (
    WEBSOCKET_GUID,
    accept_websocket,
    is_websocket_upgrade,
    read_frame,
    write_frame,
)


def test_is_websocket_upgrade_for_rdg_request():
    request = HttpRequest(
        method="RDG_OUT_DATA",
        target="https://127.0.0.1:9443/remoteDesktopGateway/",
        version="HTTP/1.1",
        headers={
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Key": "QXiTHKQvbKe4Ktrt1B9Q0w==",
        },
        raw_header_bytes=b"",
    )

    assert is_websocket_upgrade(request)


def test_accept_websocket_response():
    asyncio.run(_run_accept_websocket_response_test())


async def _run_accept_websocket_response_test():
    async def handle_client(reader, writer):
        request = HttpRequest(
            method="RDG_OUT_DATA",
            target="https://127.0.0.1:9443/remoteDesktopGateway/",
            version="HTTP/1.1",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": "QXiTHKQvbKe4Ktrt1B9Q0w==",
                "Sec-WebSocket-Protocol": "binary",
            },
            raw_header_bytes=b"",
        )
        await accept_websocket(writer, request)
        writer.close()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        response = await reader.read()
        writer.close()
        await writer.wait_closed()

    expected_accept = base64.b64encode(
        hashlib.sha1(("QXiTHKQvbKe4Ktrt1B9Q0w==" + WEBSOCKET_GUID).encode("ascii")).digest()
    ).decode("ascii")
    assert b"HTTP/1.1 101 Switching Protocols" in response
    assert f"Sec-WebSocket-Accept: {expected_accept}".encode("ascii") in response
    assert b"Sec-WebSocket-Protocol: binary" in response


def test_websocket_frame_round_trip():
    asyncio.run(_run_frame_round_trip_test())


async def _run_frame_round_trip_test():
    async def handle_client(reader, writer):
        frame = await read_frame(reader, timeout_seconds=2)
        assert frame.opcode == 0x2
        assert frame.payload == b"hello"
        await write_frame(writer, 0x2, b"world")
        writer.close()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await write_frame(writer, 0x2, b"hello", mask=True)
        frame = await read_frame(reader, timeout_seconds=2)
        writer.close()
        await writer.wait_closed()

    assert frame.opcode == 0x2
    assert frame.payload == b"world"
