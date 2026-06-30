from __future__ import annotations

import struct
from dataclasses import dataclass


PKT_TYPE_HANDSHAKE_REQUEST = 0x1
PKT_TYPE_HANDSHAKE_RESPONSE = 0x2
PKT_TYPE_TUNNEL_CREATE = 0x4
PKT_TYPE_TUNNEL_RESPONSE = 0x5
PKT_TYPE_TUNNEL_AUTH = 0x6
PKT_TYPE_TUNNEL_AUTH_RESPONSE = 0x7
PKT_TYPE_CHANNEL_CREATE = 0x8
PKT_TYPE_CHANNEL_RESPONSE = 0x9
PKT_TYPE_DATA = 0xA
PKT_TYPE_KEEPALIVE = 0xD
PKT_TYPE_CLOSE_CHANNEL = 0x10
PKT_TYPE_CLOSE_CHANNEL_RESPONSE = 0x11

S_OK = 0
RDG_HEADER_LEN = 8


@dataclass(frozen=True)
class RdgPacket:
    packet_type: int
    reserved: int
    packet_length: int
    payload: bytes


class RdgPacketBuffer:
    def __init__(self, *, max_packet_length: int = 16 * 1024 * 1024) -> None:
        self._buffer = bytearray()
        self._max_packet_length = max_packet_length

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, data: bytes) -> list[RdgPacket]:
        self._buffer.extend(data)
        packets: list[RdgPacket] = []

        while True:
            if len(self._buffer) < RDG_HEADER_LEN:
                break

            _packet_type, _reserved, packet_length = struct.unpack_from(
                "<HHI", self._buffer, 0
            )
            if packet_length < RDG_HEADER_LEN:
                raise ValueError(f"invalid RDG packet length: {packet_length}")
            if packet_length > self._max_packet_length:
                raise ValueError(f"RDG packet too large: {packet_length}")
            if len(self._buffer) < packet_length:
                break

            packet_bytes = bytes(self._buffer[:packet_length])
            del self._buffer[:packet_length]
            packets.append(parse_packet(packet_bytes))

        return packets


@dataclass(frozen=True)
class HandshakeRequest:
    version_major: int
    version_minor: int
    client_version: int
    extended_auth: int


@dataclass(frozen=True)
class ChannelCreateRequest:
    resource_count: int
    alternative_resource_count: int
    port: int
    protocol_number: int
    resource_name: str


def parse_packet(payload: bytes) -> RdgPacket:
    if len(payload) < RDG_HEADER_LEN:
        raise ValueError(f"RDG packet too short: {len(payload)} bytes")
    packet_type, reserved, packet_length = struct.unpack_from("<HHI", payload, 0)
    if packet_length != len(payload):
        raise ValueError(
            f"RDG packet length mismatch: header={packet_length} actual={len(payload)}"
        )
    return RdgPacket(
        packet_type=packet_type,
        reserved=reserved,
        packet_length=packet_length,
        payload=payload[RDG_HEADER_LEN:],
    )


def parse_handshake_request(packet: RdgPacket) -> HandshakeRequest:
    if packet.packet_type != PKT_TYPE_HANDSHAKE_REQUEST:
        raise ValueError("not an RDG handshake request")
    if len(packet.payload) != 6:
        raise ValueError(f"invalid RDG handshake payload length: {len(packet.payload)}")
    version_major, version_minor, client_version, extended_auth = struct.unpack(
        "<BBHH", packet.payload
    )
    return HandshakeRequest(
        version_major=version_major,
        version_minor=version_minor,
        client_version=client_version,
        extended_auth=extended_auth,
    )


def parse_channel_create_request(packet: RdgPacket) -> ChannelCreateRequest:
    if packet.packet_type != PKT_TYPE_CHANNEL_CREATE:
        raise ValueError("not an RDG channel create request")
    if len(packet.payload) < 8:
        raise ValueError(f"invalid RDG channel create payload length: {len(packet.payload)}")
    resource_count, alt_count, port, protocol_number, name_len = struct.unpack_from(
        "<BBHHH", packet.payload, 0
    )
    name_start = 8
    name_end = name_start + name_len
    if name_end > len(packet.payload):
        raise ValueError("RDG channel create resource name is truncated")
    raw_name = packet.payload[name_start:name_end]
    resource_name = raw_name.decode("utf-16-le", errors="strict").rstrip("\x00")
    return ChannelCreateRequest(
        resource_count=resource_count,
        alternative_resource_count=alt_count,
        port=port,
        protocol_number=protocol_number,
        resource_name=resource_name,
    )


def build_handshake_response(*, extended_auth: int = 0) -> bytes:
    payload = struct.pack(
        "<IBBHH",
        S_OK,
        1,
        0,
        0,
        extended_auth,
    )
    return build_packet(PKT_TYPE_HANDSHAKE_RESPONSE, payload)


def build_tunnel_response() -> bytes:
    payload = struct.pack(
        "<HIHH",
        0,  # serverVersion
        S_OK,
        0,  # fieldsPresent
        0,  # reserved
    )
    return build_packet(PKT_TYPE_TUNNEL_RESPONSE, payload)


def build_tunnel_auth_response() -> bytes:
    payload = struct.pack(
        "<IHH",
        S_OK,
        0,  # fieldsPresent
        0,  # reserved
    )
    return build_packet(PKT_TYPE_TUNNEL_AUTH_RESPONSE, payload)


def build_channel_response() -> bytes:
    payload = struct.pack(
        "<IHH",
        S_OK,
        0,  # fieldsPresent
        0,  # reserved
    )
    return build_packet(PKT_TYPE_CHANNEL_RESPONSE, payload)


def build_data_packet(data: bytes) -> bytes:
    if len(data) > 0xFFFF:
        raise ValueError("RDG data payload exceeds UINT16 data size")
    payload = struct.pack("<H", len(data)) + data
    return build_packet(PKT_TYPE_DATA, payload)


def parse_data_packet(packet: RdgPacket) -> bytes:
    if packet.packet_type != PKT_TYPE_DATA:
        raise ValueError("not an RDG data packet")
    if len(packet.payload) < 2:
        raise ValueError("RDG data packet is missing data size")
    data_size = struct.unpack_from("<H", packet.payload, 0)[0]
    data = packet.payload[2:]
    if len(data) != data_size:
        raise ValueError(f"RDG data size mismatch: header={data_size} actual={len(data)}")
    return data


def build_packet(packet_type: int, payload: bytes = b"") -> bytes:
    packet_length = RDG_HEADER_LEN + len(payload)
    return struct.pack("<HHI", packet_type, 0, packet_length) + payload


def packet_type_name(packet_type: int) -> str:
    names = {
        PKT_TYPE_HANDSHAKE_REQUEST: "PKT_TYPE_HANDSHAKE_REQUEST",
        PKT_TYPE_HANDSHAKE_RESPONSE: "PKT_TYPE_HANDSHAKE_RESPONSE",
        PKT_TYPE_TUNNEL_CREATE: "PKT_TYPE_TUNNEL_CREATE",
        PKT_TYPE_TUNNEL_RESPONSE: "PKT_TYPE_TUNNEL_RESPONSE",
        PKT_TYPE_TUNNEL_AUTH: "PKT_TYPE_TUNNEL_AUTH",
        PKT_TYPE_TUNNEL_AUTH_RESPONSE: "PKT_TYPE_TUNNEL_AUTH_RESPONSE",
        PKT_TYPE_CHANNEL_CREATE: "PKT_TYPE_CHANNEL_CREATE",
        PKT_TYPE_CHANNEL_RESPONSE: "PKT_TYPE_CHANNEL_RESPONSE",
        PKT_TYPE_DATA: "PKT_TYPE_DATA",
        PKT_TYPE_KEEPALIVE: "PKT_TYPE_KEEPALIVE",
        PKT_TYPE_CLOSE_CHANNEL: "PKT_TYPE_CLOSE_CHANNEL",
        PKT_TYPE_CLOSE_CHANNEL_RESPONSE: "PKT_TYPE_CLOSE_CHANNEL_RESPONSE",
    }
    return names.get(packet_type, f"PKT_TYPE_UNKNOWN_0x{packet_type:x}")
