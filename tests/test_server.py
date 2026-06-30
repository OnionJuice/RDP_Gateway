import asyncio
from pathlib import Path

import pytest

from rdp_gateway.config import AppConfig, GatewayConfig, LoggingConfig, Socks5Config
from rdp_gateway.gui import format_gateway_exception
from rdp_gateway.server import RdpGatewayServer, parse_target


def test_parse_target_hostname():
    target = parse_target("example.com:3389")

    assert target.host == "example.com"
    assert target.port == 3389


def test_parse_target_ipv6():
    target = parse_target("[::1]:3389")

    assert target.host == "::1"
    assert target.port == 3389


def test_parse_target_rejects_missing_port():
    with pytest.raises(ValueError, match="missing port"):
        parse_target("example.com")


def test_server_reports_missing_certificate_path(tmp_path: Path):
    cert_file = tmp_path / "missing-cert.pem"
    key_file = tmp_path / "missing-key.pem"
    config = AppConfig(
        gateway=GatewayConfig(
            listen_host="127.0.0.1",
            listen_port=9443,
            username="rdg",
            password="secret",
            cert_file=cert_file,
            key_file=key_file,
        ),
        socks5=Socks5Config(host="127.0.0.1", port=1080),
        logging=LoggingConfig(),
        base_dir=tmp_path,
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        asyncio.run(RdpGatewayServer(config).serve_forever())

    assert exc_info.value.filename == str(cert_file)
    assert "TLS certificate file not found" in str(exc_info.value)


def test_gateway_file_not_found_message_includes_path(tmp_path: Path):
    cert_file = tmp_path / "missing-cert.pem"
    exc = FileNotFoundError(2, "TLS certificate file not found", str(cert_file))

    message = format_gateway_exception(exc)

    assert "FileNotFoundError: missing file:" in message
    assert str(cert_file) in message
    assert "TLS certificate file not found" in message
