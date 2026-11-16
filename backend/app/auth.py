"""사용자 토큰 검증. Supabase 가 발급한 JWT(ES256)를 JWKS 공개키로 검증한다.

익명 로그인 토큰도 role 은 authenticated 이고 is_anonymous 만 true 이다.
토큰 값과 SUPABASE_URL 값은 로그·에러 메시지에 남기지 않는다.
"""
import logging
import threading
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from . import config

log = logging.getLogger(__name__)

JWKS_TIMEOUT_S = 3          # 요청 경로에서 JWKS 를 받을 때 기다리는 최대 시간
JWKS_REFETCH_MIN_S = 60     # 알 수 없는 kid 가 와도 이 간격 안에서는 JWKS 를 다시 받지 않는다
JWKS_LIFESPAN_S = 600       # JWKS 캐시 유지 시간

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}
_client: PyJWKClient | None = None
_client_url = ""
_lock = threading.Lock()


@dataclass(frozen=True)
class CurrentUser:
    id: str
    is_anonymous: bool


def _unauthorized() -> HTTPException:
    return HTTPException(401, "인증이 필요합니다.", headers=_UNAUTHORIZED)


def _jwks_client(base_url: str) -> PyJWKClient:
    """주소가 같으면 같은 클라이언트(캐시 포함)를 재사용한다."""
    global _client, _client_url
    with _lock:
        if _client is None or _client_url != base_url:
            _client = PyJWKClient(
                f"{base_url}/auth/v1/.well-known/jwks.json",
                cache_keys=True, lifespan=JWKS_LIFESPAN_S,
                timeout=JWKS_TIMEOUT_S, cooldown_duration=JWKS_REFETCH_MIN_S)
            _client_url = base_url
        return _client


def verify_token(token: str) -> CurrentUser:
    base_url = config.supabase_url()
    if not base_url:
        raise HTTPException(503, "인증 설정이 없어 요청을 처리할 수 없습니다.")
    try:
        key = _jwks_client(base_url).get_signing_key_from_jwt(token)
    except jwt.PyJWKClientConnectionError:
        log.warning("JWKS 를 받지 못했습니다.")
        raise HTTPException(503, "인증 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    except jwt.PyJWTError:
        # 헤더가 깨졌거나 알 수 없는 kid
        raise _unauthorized()
    except (OSError, ValueError):
        log.warning("JWKS 응답을 처리하지 못했습니다.")
        raise HTTPException(503, "인증 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    try:
        claims = jwt.decode(
            token, key.key, algorithms=["ES256"], audience="authenticated",
            issuer=f"{base_url}/auth/v1", options={"require": ["exp", "sub", "aud", "iss"]})
    except jwt.PyJWTError:
        raise _unauthorized()
    if claims.get("role") != "authenticated":
        raise _unauthorized()
    try:
        user_id = str(uuid.UUID(str(claims["sub"])))
    except ValueError:
        raise _unauthorized()
    return CurrentUser(id=user_id, is_anonymous=claims.get("is_anonymous") is True)


def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Authorization: Bearer <토큰> 을 검증한다. 실패는 모두 같은 문구의 401."""
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return verify_token(token)
