from pathlib import Path
import subprocess

import pytest

from rdp_gateway.cert_utils import (
    CertificateTrustError,
    build_trust_cert_command,
    trust_cert_macos,
)


def test_build_trust_cert_command_quotes_paths_with_spaces():
    cert_file = Path("/Users/jim/Library/Application Support/RDP_Gateway/certs/localhost.pem")

    command = build_trust_cert_command(cert_file)

    assert command[:2] == ["security", "add-trusted-cert"]
    assert "-p" in command
    assert "ssl" in command
    assert "-k" in command
    assert command[-1] == str(cert_file)


def test_trust_cert_macos_reports_security_error(monkeypatch, tmp_path: Path):
    cert_file = tmp_path / "localhost.pem"
    cert_file.write_text("not-a-real-cert", encoding="utf-8")

    def fake_run(*args, **kwargs):
        assert args[0][0:2] == ["security", "add-trusted-cert"]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="SecTrustSettingsSetTrustSettings: write failed",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CertificateTrustError) as exc_info:
        trust_cert_macos(cert_file)

    message = str(exc_info.value)
    assert str(cert_file) in message
    assert "keychain:" in message
    assert "exit status: 1" in message
    assert "write failed" in message
    assert "security add-trusted-cert" in message
