from pathlib import Path

from rdp_gateway.launch_agent import LABEL, build_plist


def test_build_plist_uses_gui_autostart(tmp_path: Path):
    config_path = tmp_path / "config.toml"

    plist = build_plist(config_path, log_dir=tmp_path / "logs")

    assert plist["Label"] == LABEL
    args = plist["ProgramArguments"]
    assert "rdp-gateway-gui" in args
    assert "--autostart" in args
    assert "--config" in args
    assert str(config_path) in args
    assert plist["RunAtLoad"] is True
