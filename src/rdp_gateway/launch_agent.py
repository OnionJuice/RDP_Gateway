from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path


LABEL = "local.rdp-gateway.app"


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def default_program_arguments(config_path: Path, *, autostart: bool = True) -> list[str]:
    if is_frozen_app():
        args = [sys.executable]
    else:
        args = [
            shutil_which_uv(),
            "run",
            "rdp-gateway-gui",
        ]

    if autostart:
        args.append("--autostart")
    args.extend(["--config", str(config_path)])
    return args


def build_plist(config_path: Path, log_dir: Path | None = None) -> dict[str, object]:
    if is_frozen_app():
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parents[2]
    log_root = log_dir or (Path.home() / "Library" / "Logs" / "RDP_Gateway")
    return {
        "Label": LABEL,
        "ProgramArguments": default_program_arguments(config_path),
        "RunAtLoad": True,
        "KeepAlive": False,
        "WorkingDirectory": str(root),
        "StandardOutPath": str(log_root / "launchd.out.log"),
        "StandardErrorPath": str(log_root / "launchd.err.log"),
        "EnvironmentVariables": {
            "PATH": os.environ.get(
                "PATH",
                "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            )
        },
    }


def install(config_path: Path) -> Path:
    path = launch_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path.home() / "Library" / "Logs" / "RDP_Gateway"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist = build_plist(config_path, log_dir=log_dir)
    with path.open("wb") as fh:
        plistlib.dump(plist, fh)
    _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
    return path


def uninstall() -> None:
    path = launch_agent_path()
    if path.exists():
        _launchctl("bootout", f"gui/{os.getuid()}", str(path), check=False)
        path.unlink()


def is_installed() -> bool:
    return launch_agent_path().exists()


def shutil_which_uv() -> str:
    from shutil import which

    return which("uv") or "uv"


def _launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        check=check,
        capture_output=True,
        text=True,
    )
