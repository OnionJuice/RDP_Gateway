from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    username: str | None = None
    scheme: str | None = None
    reason: str | None = None


class GatewayAuth:
    """Fixed-credential gateway authentication.

    Basic authentication is implemented because it is deterministic and easy to
    test. NTLM/SPNEGO is advertised only when implemented by a future adapter.
    """

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def check(self, headers: Mapping[str, str]) -> AuthResult:
        value = _first_header(headers, "authorization", "proxy-authorization")
        if value is None:
            rdg_user_id = _first_header(headers, "rdg-user-id")
            if rdg_user_id is not None:
                return self._check_rdg_user_id(rdg_user_id)
            return AuthResult(False, reason="missing credentials")

        scheme, _, payload = value.partition(" ")
        scheme_lower = scheme.lower()
        if scheme_lower == "basic":
            return self._check_basic(payload)
        if scheme_lower in {"ntlm", "negotiate"}:
            return AuthResult(False, scheme=scheme, reason="ntlm/spnego not implemented")
        return AuthResult(False, scheme=scheme, reason="unsupported auth scheme")

    def challenge_headers(self) -> list[tuple[str, str]]:
        challenge = 'Basic realm="RDP_Gateway"'
        return [
            ("WWW-Authenticate", challenge),
            ("Proxy-Authenticate", challenge),
        ]

    def _check_basic(self, payload: str) -> AuthResult:
        try:
            decoded = base64.b64decode(payload, validate=True).decode("utf-8")
        except Exception:
            return AuthResult(False, scheme="Basic", reason="invalid basic token")

        username, sep, password = decoded.partition(":")
        if not sep:
            return AuthResult(False, scheme="Basic", reason="invalid basic payload")

        user_ok = hmac.compare_digest(username, self._username)
        password_ok = hmac.compare_digest(password, self._password)
        if user_ok and password_ok:
            return AuthResult(True, username=username, scheme="Basic")
        return AuthResult(False, username=username, scheme="Basic", reason="bad credentials")

    def _check_rdg_user_id(self, payload: str) -> AuthResult:
        try:
            decoded_bytes = base64.b64decode(payload, validate=True)
            username = decoded_bytes.decode("utf-16-le").rstrip("\x00")
        except Exception:
            return AuthResult(False, scheme="RDG-User-Id", reason="invalid rdg user id")

        if hmac.compare_digest(username, self._username):
            return AuthResult(True, username=username, scheme="RDG-User-Id")
        return AuthResult(
            False,
            username=username,
            scheme="RDG-User-Id",
            reason="bad rdg user id",
        )


def redact_auth_headers(headers: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "proxy-authorization"}:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def _first_header(headers: Mapping[str, str], *names: str) -> str | None:
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return None
