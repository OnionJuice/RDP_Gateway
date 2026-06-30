from pathlib import Path

from rdp_gateway.config import load_config
from rdp_gateway.config_file import load_raw_config, save_raw_config


def test_save_raw_config_keeps_app_settings_and_server_loads(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    data = {
        "gateway": {
            "listen_host": "127.0.0.1",
            "listen_port": 9443,
            "username": "rdg",
            "password": "secret",
            "cert_file": "certs/localhost.pem",
            "key_file": "certs/localhost-key.pem",
            "read_timeout_seconds": 20,
        },
        "socks5": {
            "host": "127.0.0.1",
            "port": 1080,
            "connect_timeout_seconds": 20,
        },
        "logging": {"level": "DEBUG"},
        "app": {
            "start_gateway_on_launch": True,
            "launch_at_login": True,
            "keep_in_menu_bar": True,
            "language": "zh",
        },
    }

    save_raw_config(config_path, data)
    loaded_raw = load_raw_config(config_path)
    loaded_server = load_config(config_path)

    assert loaded_raw["app"]["start_gateway_on_launch"] is True
    assert loaded_raw["app"]["launch_at_login"] is True
    assert loaded_raw["app"]["keep_in_menu_bar"] is True
    assert loaded_raw["app"]["language"] == "zh"
    assert loaded_server.gateway.listen_port == 9443
    assert loaded_server.logging.level == "DEBUG"
