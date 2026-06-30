import asyncio

from rdp_gateway.socks5 import Socks5Endpoint, open_connection_via_socks5


def test_open_connection_via_socks5_domain_connect():
    asyncio.run(_run_socks5_domain_connect_test())


async def _run_socks5_domain_connect_test():
    seen = {}

    async def handle_client(reader, writer):
        greeting = await reader.readexactly(3)
        assert greeting == b"\x05\x01\x00"
        writer.write(b"\x05\x00")
        await writer.drain()

        request = await reader.readexactly(4)
        assert request == b"\x05\x01\x00\x03"
        host_len = (await reader.readexactly(1))[0]
        host = (await reader.readexactly(host_len)).decode("ascii")
        port = int.from_bytes(await reader.readexactly(2), "big")
        seen["target"] = (host, port)
        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()
        await reader.read(1)
        writer.close()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        reader, writer = await open_connection_via_socks5(
            Socks5Endpoint("127.0.0.1", port),
            Socks5Endpoint("rdp.internal", 3389),
            timeout_seconds=2,
        )
        writer.close()
        await writer.wait_closed()

    assert seen["target"] == ("rdp.internal", 3389)
