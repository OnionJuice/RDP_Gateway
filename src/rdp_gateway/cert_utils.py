from __future__ import annotations

import errno
import shlex
import subprocess
from pathlib import Path


OPENSSL_CONFIG = """[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = 127.0.0.1

[v3_req]
subjectAltName = @alt_names
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
"""


class CertificateTrustError(RuntimeError):
    pass


def generate_localhost_cert(cert_file: Path, key_file: Path) -> None:
    cert_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    openssl_cnf = cert_file.parent / "localhost.cnf"
    openssl_cnf.write_text(OPENSSL_CONFIG, encoding="utf-8")
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-days",
            "825",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_file),
            "-out",
            str(cert_file),
            "-config",
            str(openssl_cnf),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    key_file.chmod(0o600)


def trust_cert_macos(cert_file: Path) -> None:
    if not cert_file.is_file():
        raise FileNotFoundError(
            errno.ENOENT,
            "certificate file not found",
            str(cert_file),
        )

    command = build_trust_cert_command(cert_file)
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CertificateTrustError(
            _format_trust_error(cert_file, command, result)
        )


def build_trust_cert_command(cert_file: Path) -> list[str]:
    return [
        "security",
        "add-trusted-cert",
        "-r",
        "trustRoot",
        "-p",
        "ssl",
        "-k",
        str(user_login_keychain()),
        str(cert_file),
    ]


def user_login_keychain() -> Path:
    candidates = [
        Path.home() / "Library" / "Keychains" / "login.keychain-db",
        Path.home() / "Library" / "Keychains" / "login.keychain",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _format_trust_error(
    cert_file: Path,
    command: list[str],
    result: subprocess.CompletedProcess[str],
) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    if not detail:
        detail = "macOS did not return a detailed error message"
    command_text = shlex.join(command)
    return (
        "failed to trust certificate with macOS security command\n"
        f"certificate: {cert_file}\n"
        f"keychain: {user_login_keychain()}\n"
        f"exit status: {result.returncode}\n"
        f"reason: {detail}\n"
        f"command: {command_text}"
    )
