"""환경설정. .env 를 찾아 읽는다 (이미 설정된 환경변수가 우선).

찾는 위치(앞이 우선): backend/.env -> CapstoneProject/.env
인코딩은 UTF-8, UTF-8(BOM), UTF-16 모두 처리한다. (메모장·PowerShell 로 만든 .env 는
BOM 이나 UTF-16 으로 저장되는 경우가 있어, 그대로 읽으면 첫 변수 이름이 깨진다.)
"""
import io
import os
from pathlib import Path

from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]   # CapstoneProject/backend
ROOT = BACKEND.parent                           # CapstoneProject
ENV_FILES = [BACKEND / ".env", ROOT / ".env"]


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _load_env() -> list[str]:
    """읽은 파일 경로 목록을 돌려준다. 이미 있는 환경변수는 덮어쓰지 않는다."""
    loaded = []
    for path in ENV_FILES:
        if not path.is_file():
            continue
        values = dotenv_values(stream=io.StringIO(_read_text(path)))
        for k, v in values.items():
            if v is not None and k not in os.environ:
                os.environ[k] = v
        loaded.append(str(path))
    return loaded


_LOADED = _load_env()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        names = []
        for p in _LOADED:
            names += list(dotenv_values(stream=io.StringIO(_read_text(Path(p)))).keys())
        raise RuntimeError(
            "DATABASE_URL 이 없습니다.\n"
            f"  찾아본 위치: {[str(p) for p in ENV_FILES]}\n"
            f"  읽은 파일: {_LOADED or '없음'}\n"
            f"  읽은 변수 이름: {names or '없음'}  (값은 표시하지 않음)"
        )
    # SQLAlchemy 가 psycopg3 드라이버를 쓰도록 스킴을 맞춘다
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    return url


def allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


def allowed_origin_regex() -> str | None:
    """매번 바뀌는 주소(예: 터널)를 허용할 때만 설정. 예) https://.*\\.trycloudflare\\.com"""
    return os.environ.get("ALLOWED_ORIGIN_REGEX", "").strip() or None


# ---------- 사용자 인증 (Supabase) ----------
def supabase_url() -> str:
    """값은 어디에도 출력하지 않는다. 없으면 빈 문자열. 끝의 / 는 떼어 낸다."""
    return os.environ.get("SUPABASE_URL", "").strip().strip("\"'").rstrip("/")


# ---------- OCR (OpenRouter) ----------
def openrouter_api_key() -> str:
    """키 값은 어디에도 출력하지 않는다. 없으면 빈 문자열."""
    return os.environ.get("OPENROUTER_API_KEY", "").strip().strip("\"'")


def openrouter_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", "").strip() or "google/gemini-3.8-flash"


def ocr_max_image_bytes() -> int:
    return int(os.environ.get("OCR_MAX_IMAGE_MB", "5")) * 1024 * 1024


def ocr_timeout_s() -> float:
    return float(os.environ.get("OCR_TIMEOUT_S", "30"))


def ocr_rate_limit_per_min() -> int:
    return int(os.environ.get("OCR_RATE_LIMIT_PER_MIN", "10"))
