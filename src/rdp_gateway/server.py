from __future__ import annotations

import asyncio
import errno
import logging
import ssl
from dataclasses import dataclass
from urllib.parse import unquote

from .auth import GatewayAuth, redact_auth_headers
from .config import AppConfig
from .http import HttpRequest, read_http_request, write_response
from .rdg_ws import (
    PKT_TYPE_CHANNEL_CREATE,
    PKT_TYPE_CLOSE_CHANNEL,
    PKT_TYPE_CLOSE_CHANNEL_RESPONSE,
    PKT_TYPE_DATA,
    PKT_TYPE_HANDSHAKE_REQUEST,
    PKT_TYPE_KEEPALIVE,
    PKT_TYPE_TUNNEL_AUTH,
    PKT_TYPE_TUNNEL_CREATE,
    RdgPacket,
    RdgPacketBuffer,
    build_channel_response,
    build_data_packet,
    build_handshake_response,
    build_packet,
    build_tunnel_auth_response,
    build_tunnel_response,
    packet_type_name,
    parse_channel_create_request,
    parse_data_packet,
    parse_handshake_request,
)
from .relay import relay_bidirectional
from .socks5 import Socks5Endpoint, Socks5Error, open_connection_via_socks5
from .websocket import (
    accept_websocket,
    is_websocket_upgrade,
    payload_preview,
    read_frame,
    write_frame,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Target:
    host: str
    port: int


@dataclass(frozen=True)
class _RdgPacketResult:
    target_writer: asyncio.StreamWriter | None
    target_to_client_task: asyncio.Task[None] | None
    close_channel: bool = False


class _RdgChannelClosed(Exception):
    pass


class RdpGatewayServer:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._auth = GatewayAuth(config.gateway.username, config.gateway.password)

    async def serve_forever(self) -> None:
        if not self._config.gateway.cert_file.is_file():
            raise FileNotFoundError(
                errno.ENOENT,
                "TLS certificate file not found",
                str(self._config.gateway.cert_file),
            )
        if not self._config.gateway.key_file.is_file():
            raise FileNotFoundError(
                errno.ENOENT,
                "TLS private key file not found",
                str(self._config.gateway.key_file),
            )

        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(
            str(self._config.gateway.cert_file), str(self._config.gateway.key_file)
        )
        server = await asyncio.start_server(
            self._handle_client,
            self._config.gateway.listen_host,
            self._config.gateway.listen_port,
            ssl=ssl_context,
        )

        addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
        logger.info("RDP gateway shim listening on %s", addresses)
        async with server:
            await server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        try:
            request = await read_http_request(
                reader,
                timeout_seconds=self._config.gateway.read_timeout_seconds,
            )
            logger.info(
                "incoming gateway request peer=%s method=%s target=%s",
                peer,
                request.method,
                request.target,
            )
            await self._dispatch(request, reader, writer)
        except Exception as exc:
            logger.warning("gateway request failed peer=%s error=%s", peer, exc)
            if not writer.is_closing():
                await write_response(writer, 400, "Bad Request", body=b"bad request\n")
                writer.close()
                await writer.wait_closed()

    async def _dispatch(
        self,
        request: HttpRequest,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        auth_result = self._auth.check(request.headers)
        if not auth_result.ok:
            logger.warning(
                "authentication failed scheme=%s reason=%s headers=%s",
                auth_result.scheme,
                auth_result.reason,
                redact_auth_headers(request.headers),
            )
            await write_response(
                writer,
                407 if request.method == "CONNECT" else 401,
                "Proxy Authentication Required"
                if request.method == "CONNECT"
                else "Unauthorized",
                headers=self._auth.challenge_headers(),
                body=b"authentication required\n",
            )
            writer.close()
            await writer.wait_closed()
            return

        if request.method == "CONNECT":
            target = parse_target(request.target)
            await self._connect_tunnel(target, reader, writer)
            return

        if request.method in {"RDG_OUT_DATA", "RDG_IN_DATA"} and is_websocket_upgrade(request):
            await self._rdg_websocket_probe(request, reader, writer)
            return

        if request.method in {"RPC_IN_DATA", "RPC_OUT_DATA", "RDG_IN_DATA", "RDG_OUT_DATA"}:
            logger.error(
                "RD Gateway RPC method is not implemented yet: method=%s target=%s headers=%s",
                request.method,
                request.target,
                redact_auth_headers(request.headers),
            )
            await write_response(
                writer,
                501,
                "Not Implemented",
                body=(
                    b"RD Gateway RPC transport is not implemented in this experimental "
                    b"shim yet. Check logs for method and path.\n"
                ),
            )
            writer.close()
            await writer.wait_closed()
            return

        await write_response(
            writer,
            405,
            "Method Not Allowed",
            headers=[("Allow", "CONNECT")],
            body=b"only CONNECT is currently supported\n",
        )
        writer.close()
        await writer.wait_closed()

    async def _connect_tunnel(
        self,
        target: Target,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        socks = Socks5Endpoint(
            self._config.socks5.host,
            self._config.socks5.port,
        )
        target_endpoint = Socks5Endpoint(target.host, target.port)
        logger.info(
            "opening SOCKS5 tunnel socks=%s:%s target=%s:%s",
            socks.host,
            socks.port,
            target.host,
            target.port,
        )
        try:
            target_reader, target_writer = await open_connection_via_socks5(
                socks,
                target_endpoint,
                timeout_seconds=self._config.socks5.connect_timeout_seconds,
            )
        except Socks5Error as exc:
            logger.warning("SOCKS5 connection failed target=%s:%s error=%s", target.host, target.port, exc)
            await write_response(
                client_writer,
                502,
                "Bad Gateway",
                body=b"failed to open SOCKS5 tunnel\n",
            )
            client_writer.close()
            await client_writer.wait_closed()
            return

        await write_response(
            client_writer,
            200,
            "Connection Established",
            close=False,
        )
        logger.info("tunnel established target=%s:%s", target.host, target.port)
        await relay_bidirectional(client_reader, client_writer, target_reader, target_writer)
        logger.info("tunnel closed target=%s:%s", target.host, target.port)

    async def _rdg_websocket_probe(
        self,
        request: HttpRequest,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        logger.info(
            "accepting RD Gateway WebSocket probe method=%s connection_id=%s correlation_id=%s",
            request.method,
            _header(request, "RDG-Connection-Id"),
            _header(request, "RDG-Correlation-Id"),
        )
        await accept_websocket(writer, request, protocols=("binary",))
        binary_frames = 0
        target_reader: asyncio.StreamReader | None = None
        target_writer: asyncio.StreamWriter | None = None
        target_to_client_task: asyncio.Task[None] | None = None
        rdg_buffer = RdgPacketBuffer()
        websocket_write_lock = asyncio.Lock()
        try:
            while True:
                frame = await read_frame(
                    reader,
                    timeout_seconds=self._config.gateway.read_timeout_seconds,
                )
                if frame.opcode == 0x8:
                    logger.info("RD Gateway WebSocket close received payload_len=%s", len(frame.payload))
                    await write_frame(writer, 0x8, frame.payload)
                    break
                if frame.opcode == 0x9:
                    logger.debug("RD Gateway WebSocket ping received")
                    await write_frame(writer, 0xA, frame.payload)
                    continue
                if frame.opcode == 0xA:
                    logger.debug("RD Gateway WebSocket pong received")
                    continue
                if frame.opcode in {0x0, 0x2}:
                    binary_frames += 1
                    if frame.opcode == 0x2 and len(frame.payload) >= 8 and frame.payload[0] == PKT_TYPE_DATA:
                        logger.debug(
                            "RD Gateway WebSocket data frame #%s len=%s fin=%s buffered_before=%s",
                            binary_frames,
                            len(frame.payload),
                            frame.fin,
                            rdg_buffer.buffered_bytes,
                        )
                    else:
                        logger.info(
                            "RD Gateway WebSocket frame #%s opcode=%s fin=%s %s buffered_before=%s",
                            binary_frames,
                            frame.opcode,
                            frame.fin,
                            payload_preview(frame.payload),
                            rdg_buffer.buffered_bytes,
                        )
                    packets = rdg_buffer.feed(frame.payload)
                    if not packets:
                        logger.debug(
                            "RD Gateway buffered partial packet bytes=%s",
                            rdg_buffer.buffered_bytes,
                        )
                    for packet in packets:
                        packet_result = await self._handle_rdg_packet(
                            packet,
                            writer,
                            websocket_write_lock,
                            target_writer,
                            target_to_client_task,
                        )
                        target_writer = packet_result.target_writer
                        target_to_client_task = packet_result.target_to_client_task
                        if packet_result.close_channel:
                            raise _RdgChannelClosed()
                    continue
                logger.info(
                    "RD Gateway WebSocket frame opcode=%s fin=%s payload_len=%s",
                    frame.opcode,
                    frame.fin,
                    len(frame.payload),
                )
        except EOFError:
            logger.info("RD Gateway WebSocket closed by client")
        except _RdgChannelClosed:
            logger.info("RD Gateway channel closed")
        except Exception as exc:
            logger.warning(
                "RD Gateway WebSocket probe failed: %s: %s",
                exc.__class__.__name__,
                exc,
            )
        finally:
            if target_to_client_task is not None:
                target_to_client_task.cancel()
                await asyncio.gather(target_to_client_task, return_exceptions=True)
            if target_writer is not None:
                target_writer.close()
                await target_writer.wait_closed()
            writer.close()
            await writer.wait_closed()

    async def _handle_rdg_packet(
        self,
        packet: RdgPacket,
        writer: asyncio.StreamWriter,
        websocket_write_lock: asyncio.Lock,
        target_writer: asyncio.StreamWriter | None,
        target_to_client_task: asyncio.Task[None] | None,
    ) -> "_RdgPacketResult":
        if packet.packet_type != PKT_TYPE_DATA:
            logger.info(
                "RD Gateway packet %s length=%s reserved=%s",
                packet_type_name(packet.packet_type),
                packet.packet_length,
                packet.reserved,
            )
        else:
            logger.debug(
                "RD Gateway packet %s length=%s reserved=%s",
                packet_type_name(packet.packet_type),
                packet.packet_length,
                packet.reserved,
            )

        if packet.packet_type == PKT_TYPE_HANDSHAKE_REQUEST:
            handshake = parse_handshake_request(packet)
            response = build_handshake_response(extended_auth=handshake.extended_auth)
            async with websocket_write_lock:
                await write_frame(writer, 0x2, response)
            logger.info(
                "RD Gateway handshake response sent client_version=%s.%s extended_auth=%s %s",
                handshake.version_major,
                handshake.version_minor,
                handshake.extended_auth,
                payload_preview(response),
            )
            return _RdgPacketResult(target_writer, target_to_client_task)

        if packet.packet_type == PKT_TYPE_TUNNEL_CREATE:
            response = build_tunnel_response()
            async with websocket_write_lock:
                await write_frame(writer, 0x2, response)
            logger.info("RD Gateway tunnel response sent %s", payload_preview(response))
            return _RdgPacketResult(target_writer, target_to_client_task)

        if packet.packet_type == PKT_TYPE_TUNNEL_AUTH:
            response = build_tunnel_auth_response()
            async with websocket_write_lock:
                await write_frame(writer, 0x2, response)
            logger.info("RD Gateway tunnel auth response sent %s", payload_preview(response))
            return _RdgPacketResult(target_writer, target_to_client_task)

        if packet.packet_type == PKT_TYPE_CHANNEL_CREATE:
            channel = parse_channel_create_request(packet)
            logger.info(
                "RD Gateway channel create target=%s:%s protocol=%s resources=%s alt_resources=%s",
                channel.resource_name,
                channel.port,
                channel.protocol_number,
                channel.resource_count,
                channel.alternative_resource_count,
            )
            target_reader, new_target_writer = await self._open_socks_target(
                Target(channel.resource_name, channel.port)
            )
            async with websocket_write_lock:
                await write_frame(writer, 0x2, build_channel_response())
            logger.info(
                "RD Gateway channel open target=%s:%s",
                channel.resource_name,
                channel.port,
            )
            new_task = asyncio.create_task(
                self._target_to_rdg_websocket(
                    target_reader,
                    writer,
                    websocket_write_lock,
                )
            )
            return _RdgPacketResult(new_target_writer, new_task)

        if packet.packet_type == PKT_TYPE_DATA:
            if target_writer is None:
                raise ValueError("RDG DATA received before channel is open")
            data = parse_data_packet(packet)
            target_writer.write(data)
            await target_writer.drain()
            logger.debug("RD Gateway DATA client->target bytes=%s", len(data))
            return _RdgPacketResult(target_writer, target_to_client_task)

        if packet.packet_type == PKT_TYPE_KEEPALIVE:
            async with websocket_write_lock:
                await write_frame(writer, 0x2, build_packet(PKT_TYPE_KEEPALIVE))
            logger.debug("RD Gateway keepalive echoed")
            return _RdgPacketResult(target_writer, target_to_client_task)

        if packet.packet_type == PKT_TYPE_CLOSE_CHANNEL:
            async with websocket_write_lock:
                await write_frame(
                    writer,
                    0x2,
                    build_packet(PKT_TYPE_CLOSE_CHANNEL_RESPONSE, b"\x00\x00\x00\x00"),
                )
            logger.info("RD Gateway close channel response sent")
            return _RdgPacketResult(
                target_writer,
                target_to_client_task,
                close_channel=True,
            )

        raise ValueError(f"unsupported RDG packet type {packet_type_name(packet.packet_type)}")

    async def _open_socks_target(
        self,
        target: Target,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        socks = Socks5Endpoint(
            self._config.socks5.host,
            self._config.socks5.port,
        )
        logger.info(
            "opening RDG SOCKS5 tunnel socks=%s:%s target=%s:%s",
            socks.host,
            socks.port,
            target.host,
            target.port,
        )
        return await open_connection_via_socks5(
            socks,
            Socks5Endpoint(target.host, target.port),
            timeout_seconds=self._config.socks5.connect_timeout_seconds,
        )

    async def _target_to_rdg_websocket(
        self,
        target_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        websocket_write_lock: asyncio.Lock,
    ) -> None:
        while True:
            data = await target_reader.read(0xFFFF)
            if not data:
                logger.info("RD Gateway target closed")
                break
            async with websocket_write_lock:
                await write_frame(client_writer, 0x2, build_data_packet(data))
            logger.debug("RD Gateway DATA target->client bytes=%s", len(data))


def parse_target(value: str) -> Target:
    value = unquote(value)
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            raise ValueError("invalid IPv6 CONNECT target")
        host = value[1:end]
        rest = value[end + 1 :]
        if not rest.startswith(":"):
            raise ValueError("CONNECT target is missing port")
        port_text = rest[1:]
    else:
        host, sep, port_text = value.rpartition(":")
        if not sep:
            raise ValueError("CONNECT target is missing port")
    if not host:
        raise ValueError("CONNECT target host is empty")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("CONNECT target port is not an integer") from exc
    if port < 1 or port > 65535:
        raise ValueError("CONNECT target port out of range")
    return Target(host=host, port=port)


def _header(request: HttpRequest, name: str) -> str | None:
    lowered = {key.lower(): value for key, value in request.headers.items()}
    return lowered.get(name.lower())
