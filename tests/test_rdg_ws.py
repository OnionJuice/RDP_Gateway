from rdp_gateway.rdg_ws import (
    PKT_TYPE_CHANNEL_CREATE,
    PKT_TYPE_HANDSHAKE_REQUEST,
    build_channel_response,
    build_data_packet,
    build_handshake_response,
    build_tunnel_auth_response,
    build_tunnel_response,
    parse_channel_create_request,
    parse_data_packet,
    parse_handshake_request,
    parse_packet,
    RdgPacketBuffer,
)


def test_parse_logged_handshake_request():
    payload = bytes.fromhex("01 00 00 00 0e 00 00 00 01 00 00 00 00 00")

    packet = parse_packet(payload)
    handshake = parse_handshake_request(packet)

    assert packet.packet_type == PKT_TYPE_HANDSHAKE_REQUEST
    assert packet.packet_length == 14
    assert handshake.version_major == 1
    assert handshake.version_minor == 0
    assert handshake.client_version == 0
    assert handshake.extended_auth == 0


def test_build_handshake_response():
    assert build_handshake_response() == bytes.fromhex(
        "02 00 00 00 12 00 00 00 00 00 00 00 01 00 00 00 00 00"
    )


def test_build_minimal_control_responses():
    assert build_tunnel_response() == bytes.fromhex(
        "05 00 00 00 12 00 00 00 00 00 00 00 00 00 00 00 00 00"
    )
    assert build_tunnel_auth_response() == bytes.fromhex(
        "07 00 00 00 10 00 00 00 00 00 00 00 00 00 00 00"
    )
    assert build_channel_response() == bytes.fromhex(
        "09 00 00 00 10 00 00 00 00 00 00 00 00 00 00 00"
    )


def test_parse_channel_create_request():
    name = "rdp.internal".encode("utf-16-le") + b"\x00\x00"
    payload = (
        b"\x01"  # resource count
        b"\x00"  # alternative count
        + (3389).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + len(name).to_bytes(2, "little")
        + name
    )
    packet = parse_packet(
        (PKT_TYPE_CHANNEL_CREATE).to_bytes(2, "little")
        + b"\x00\x00"
        + (8 + len(payload)).to_bytes(4, "little")
        + payload
    )

    channel = parse_channel_create_request(packet)

    assert channel.resource_count == 1
    assert channel.alternative_resource_count == 0
    assert channel.port == 3389
    assert channel.protocol_number == 3
    assert channel.resource_name == "rdp.internal"


def test_data_packet_round_trip():
    packet = parse_packet(build_data_packet(b"rdp"))

    assert parse_data_packet(packet) == b"rdp"


def test_packet_buffer_reassembles_fragmented_rdg_packet():
    packet_bytes = build_data_packet(b"x" * 43)
    assert len(packet_bytes) == 53
    first = packet_bytes[:23]
    second = packet_bytes[23:]
    buffer = RdgPacketBuffer()

    assert buffer.feed(first) == []
    packets = buffer.feed(second)

    assert len(packets) == 1
    assert parse_data_packet(packets[0]) == b"x" * 43
    assert buffer.buffered_bytes == 0


def test_packet_buffer_reassembles_multiple_packets():
    first = build_data_packet(b"one")
    second = build_data_packet(b"two")
    buffer = RdgPacketBuffer()

    packets = buffer.feed(first + second)

    assert [parse_data_packet(packet) for packet in packets] == [b"one", b"two"]
