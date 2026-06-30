from pathlib import Path

import pytest

from rdp_gateway.config import load_config


def test_load_config(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[gateway]
listen_host = "127.0.0.1"
listen_port = 9443
username = "rdg"
password = "secret"
cert_file = "certs/localhost.pem"
key_file = "certs/localhost-key.pem"

[socks5]
host = "127.0.0.1"
port = 1080
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.gateway.listen_port == 9443
    assert config.gateway.cert_file == (tmp_path / "certs/localhost.pem").resolve()
    assert config.socks5.port == 1080


def test_invalid_port(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[gateway]
listen_host = "127.0.0.1"
listen_port = 99999
username = "rdg"
password = "secret"
cert_file = "certs/localhost.pem"
key_file = "certs/localhost-key.pem"

[socks5]
host = "127.0.0.1"
port = 1080
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="listen_port"):
        load_config(config_path)
