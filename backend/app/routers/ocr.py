import time
from collections import defaultdict, deque

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from .. import config
from ..deps import get_dictionary
from ..services import ocr
from ..services.check import DISCLAIMER

router = APIRouter(tags=["ocr"])

_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(key: str) -> None:
    """비용 보호용 간단한 제한(프로세스 메모리, 분당 N회). 터널 뒤에서는 모든 요청이 한 주소로 보여 전체 한도로 동작한다."""
    limit, now = config.ocr_rate_limit_per_min(), time.monotonic()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    q.append(now)


@router.post("/ocr/allergens")
def ocr_allergens(request: Request, image: UploadFile = File(...)):
    """성분표 사진 1장 -> 알레르기 유발 추정 물질. (참고용: 사진 인식과 AI 추정에는 오류가 있을 수 있다)"""
    _rate_limit(request.client.host if request.client else "unknown")
    limit = config.ocr_max_image_bytes()
    data = image.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"이미지가 너무 큽니다 (최대 {limit // 1024 // 1024}MB). 해상도를 줄여 다시 보내주세요.")
    mime = ocr.detect_image_type(data)
    if mime is None:
        raise HTTPException(415, "JPEG, PNG, WEBP 이미지만 지원합니다.")

    d = get_dictionary()
    try:
        llm = ocr.call_llm(data, mime, d.names)
    except ocr.OcrError as e:
        raise HTTPException(e.status, e.message)
    result = ocr.combine(llm, d)
    if not result["is_ingredient_label"] and not result["ingredients_text"]:
        raise HTTPException(422, "성분표(원재료명)를 찾지 못했습니다. 글자가 선명하게 나오도록 다시 촬영해 주세요.")
    return {**result, "model": config.openrouter_model(), "disclaimer": DISCLAIMER}
