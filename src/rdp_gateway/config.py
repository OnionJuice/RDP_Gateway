from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10 path
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class GatewayConfig:
    listen_host: str
    listen_port: int
    username: str
    password: str
    cert_file: Path
    key_file: Path
    read_timeout_seconds: float = 20.0


@dataclass(frozen=True)
class Socks5Config:
    host: str
    port: int
    connect_timeout_seconds: float = 20.0


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class AppConfig:
    gateway: GatewayConfig
    socks5: Socks5Config
    logging: LoggingConfig
    base_dir: Path


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)

    base_dir = config_path.parent
    gateway_raw = _table(raw, "gateway")
    socks_raw = _table(raw, "socks5")
    logging_raw = raw.get("logging", {})
    if not isinstance(logging_raw, Mapping):
        raise ValueError("[logging] must be a TOML table")

    gateway = GatewayConfig(
        listen_host=_str(gateway_raw, "listen_host"),
        listen_port=_port(gateway_raw, "listen_port"),
        username=_str(gateway_raw, "username"),
        password=_str(gateway_raw, "password"),
        cert_file=_path(base_dir, _str(gateway_raw, "cert_file")),
        key_file=_path(base_dir, _str(gateway_raw, "key_file")),
        read_timeout_seconds=_positive_float(
            gateway_raw, "read_timeout_seconds", default=20.0
        ),
    )
    socks5 = Socks5Config(
        host=_str(socks_raw, "host"),
        port=_port(socks_raw, "port"),
        connect_timeout_seconds=_positive_float(
            socks_raw, "connect_timeout_seconds", default=20.0
        ),
    )
    logging_config = LoggingConfig(level=str(logging_raw.get("level", "INFO")))

    if not gateway.username:
        raise ValueError("gateway.username must not be empty")
    if not gateway.password:
        raise ValueError("gateway.password must not be empty")

    return AppConfig(
        gateway=gateway,
        socks5=socks5,
        logging=logging_config,
        base_dir=base_dir,
    )


def _table(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = raw.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"[{name}] must be present and must be a TOML table")
    return value


def _str(raw: Mapping[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _port(raw: Mapping[str, Any], name: str) -> int:
    value = raw.get(name)
    if not isinstance(value, int) or value < 1 or value > 65535:
        raise ValueError(f"{name} must be an integer port in the range 1..65535")
    return value


def _positive_float(raw: Mapping[str, Any], name: str, *, default: float) -> float:
    value = raw.get(name, default)
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
