"""토큰 검증 테스트. 키는 테스트에서 만들고 JWKS 조회는 가짜로 바꿔 네트워크 없이 실행한다."""
import base64
import json
import logging
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app import auth
from app.main import app

BASE = "https://abcdefgh.supabase.co"
USER = str(uuid.uuid4())
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


class FakeJWKS:
    def __init__(self, key=KEY, error=None):
        self.key, self.error = key, error

    def get_signing_key_from_jwt(self, token):
        if self.error:
            raise self.error
        jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key()))
        return jwt.PyJWK.from_dict({**jwk, "kid": "k1", "alg": "ES256"})


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", BASE)
    monkeypatch.setattr(auth, "_jwks_client", lambda url: FakeJWKS())


def make(key=KEY, alg="ES256", **over):
    now = int(time.time())
    claims = {"sub": USER, "aud": "authenticated", "iss": f"{BASE}/auth/v1", "role": "authenticated",
              "iat": now, "exp": now + 3600, "is_anonymous": True}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": "k1"})


def reject(token, status=401):
    with pytest.raises(auth.HTTPException) as e:
        auth.verify_token(token)
    assert e.value.status_code == status
    return e.value


def test_valid_token():
    assert auth.verify_token(make()) == auth.CurrentUser(id=USER, is_anonymous=True)
    assert auth.verify_token(make(is_anonymous=False)).is_anonymous is False
    assert auth.verify_token(make(is_anonymous=None)).is_anonymous is False


def test_expired():
    reject(make(exp=int(time.time()) - 10))


def test_exp_required():
    reject(make(exp=None))


def test_wrong_aud():
    reject(make(aud="anon"))


def test_wrong_iss():
    reject(make(iss="https://evil.example/auth/v1"))


def test_wrong_role():
    reject(make(role="anon"))
    reject(make(role=None))


def test_sub_not_uuid():
    reject(make(sub="not-a-uuid"))
    reject(make(sub=None))


def test_hs256_forgery_rejected():
    reject(make(key="x" * 32, alg="HS256"))


def test_alg_none_rejected():
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    now = int(time.time())
    token = (b64({"alg": "none", "typ": "JWT", "kid": "k1"}) + "." +
             b64({"sub": USER, "aud": "authenticated", "iss": f"{BASE}/auth/v1",
                  "role": "authenticated", "exp": now + 3600}) + ".")
    reject(token)


def test_tampered_signature():
    head, _, sig = make().split(".")
    other_payload = make(sub=str(uuid.uuid4())).split(".")[1]
    reject(f"{head}.{other_payload}.{sig}")
    reject(make(key=OTHER_KEY))


def test_garbage_token():
    reject("abc.def.ghi")


def test_header_missing_or_not_bearer():
    for h in (None, "", "Basic abc", "Bearer", "Bearer ", make()):
        with pytest.raises(auth.HTTPException) as e:
            auth.current_user(h)
        assert e.value.status_code == 401 and e.value.headers["WWW-Authenticate"] == "Bearer"
    assert auth.current_user("bearer " + make()).id == USER


def test_supabase_url_missing_gives_503(monkeypatch):
    monkeypatch.setattr("app.config.supabase_url", lambda: "")
    reject(make(), status=503)


def test_jwks_failure_gives_503(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client",
                        lambda url: FakeJWKS(error=jwt.PyJWKClientConnectionError("down")))
    reject(make(), status=503)


def test_unknown_kid_gives_401(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client",
                        lambda url: FakeJWKS(error=jwt.PyJWKClientError("no key")))
    reject(make())


def test_jwks_client_has_timeout_and_cooldown(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(auth, "_client", None)
    c = auth._jwks_client(BASE)
    assert c.timeout == auth.JWKS_TIMEOUT_S and c.cooldown_duration == auth.JWKS_REFETCH_MIN_S
    assert c.uri == f"{BASE}/auth/v1/.well-known/jwks.json"
    assert auth._jwks_client(BASE) is c


def test_no_token_or_url_in_response_and_logs(caplog, monkeypatch):
    client = TestClient(app)
    token = make(exp=int(time.time()) - 10)
    with caplog.at_level(logging.DEBUG):
        r = client.get("/history", headers={"Authorization": f"Bearer {token}"})
        monkeypatch.setattr(auth, "_jwks_client", lambda url: FakeJWKS(
            error=jwt.PyJWKClientConnectionError(f"{BASE} {token}")))
        r2 = client.get("/history", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and r2.status_code == 503
    for text in (r.text, r2.text, caplog.text, str(r.headers), str(r2.headers)):
        assert token not in text and "abcdefgh" not in text


def test_endpoints_require_token():
    client = TestClient(app)
    assert client.get("/history").status_code == 401
    assert client.get("/history/1").status_code == 401
    assert client.delete("/history/1").status_code == 401
    assert client.post("/history", json={"report_no": "1"}).status_code == 401
    assert client.get("/history").headers["WWW-Authenticate"] == "Bearer"
