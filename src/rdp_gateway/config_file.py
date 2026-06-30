from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w


DEFAULT_CONFIG: dict[str, Any] = {
    "gateway": {
        "listen_host": "127.0.0.1",
        "listen_port": 9443,
        "username": "rdg",
        "password": "change-me",
        "cert_file": "certs/localhost.pem",
        "key_file": "certs/localhost-key.pem",
        "read_timeout_seconds": 20,
    },
    "socks5": {
        "host": "127.0.0.1",
        "port": 1080,
        "connect_timeout_seconds": 20,
    },
    "logging": {
        "level": "INFO",
    },
    "app": {
        "start_gateway_on_launch": False,
        "launch_at_login": False,
        "keep_in_menu_bar": False,
        "language": "auto",
    },
}


def default_config_path(base_dir: Path | None = None) -> Path:
    if base_dir is None and getattr(sys, "frozen", False):
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "RDP_Gateway"
            / "config.toml"
        )
    root = base_dir if base_dir is not None else project_root()
    return root / "config.toml"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_config(path: Path) -> None:
    if path.exists():
        return

    example = path.parent / "config.example.toml"
    if example.exists():
        shutil.copyfile(example, path)
        data = load_raw_config(path)
        data.setdefault("app", DEFAULT_CONFIG["app"].copy())
        save_raw_config(path, data)
        return

    save_raw_config(path, DEFAULT_CONFIG)


def load_raw_config(path: Path) -> dict[str, Any]:
    ensure_config(path)
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return merge_defaults(data)


def save_raw_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)


def merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    merged = _deep_copy(DEFAULT_CONFIG)
    _merge_into(merged, data)
    return merged


def _merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_into(target[key], value)
        else:
            target[key] = value


def _deep_copy(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, child in value.items():
        if isinstance(child, dict):
            result[key] = _deep_copy(child)
        else:
            result[key] = child
    return result
