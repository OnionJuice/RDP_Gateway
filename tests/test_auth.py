import base64

from rdp_gateway.auth import GatewayAuth, redact_auth_headers


def test_basic_auth_success():
    token = base64.b64encode(b"rdg:secret").decode("ascii")
    result = GatewayAuth("rdg", "secret").check({"Authorization": f"Basic {token}"})

    assert result.ok
    assert result.username == "rdg"
    assert result.scheme == "Basic"


def test_basic_auth_bad_password():
    token = base64.b64encode(b"rdg:wrong").decode("ascii")
    result = GatewayAuth("rdg", "secret").check({"Authorization": f"Basic {token}"})

    assert not result.ok
    assert result.reason == "bad credentials"


def test_redact_auth_headers():
    headers = redact_auth_headers({"Authorization": "Basic abc", "Host": "localhost"})

    assert headers["Authorization"] == "<redacted>"
    assert headers["Host"] == "localhost"


def test_rdg_user_id_auth_success():
    result = GatewayAuth("rdg", "secret").check({"RDG-User-Id": "cgBkAGcA"})

    assert result.ok
    assert result.username == "rdg"
    assert result.scheme == "RDG-User-Id"
