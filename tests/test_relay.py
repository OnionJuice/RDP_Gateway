import asyncio

from rdp_gateway.relay import relay_bidirectional


def test_relay_bidirectional_moves_bytes():
    asyncio.run(_run_relay_test())


async def _run_relay_test():
    received = {}

    async def handle_target(reader, writer):
        data = await reader.readexactly(4)
        received["target"] = data
        writer.write(b"pong")
        await writer.drain()
        writer.close()

    target_server = await asyncio.start_server(handle_target, "127.0.0.1", 0)
    target_port = target_server.sockets[0].getsockname()[1]

    async def handle_gateway(client_reader, client_writer):
        target_reader, target_writer = await asyncio.open_connection(
            "127.0.0.1", target_port
        )
        await relay_bidirectional(client_reader, client_writer, target_reader, target_writer)

    gateway_server = await asyncio.start_server(handle_gateway, "127.0.0.1", 0)
    gateway_port = gateway_server.sockets[0].getsockname()[1]

    async with target_server, gateway_server:
        reader, writer = await asyncio.open_connection("127.0.0.1", gateway_port)
        writer.write(b"ping")
        await writer.drain()
        assert await reader.readexactly(4) == b"pong"
        writer.close()
        await writer.wait_closed()

    assert received["target"] == b"ping"
