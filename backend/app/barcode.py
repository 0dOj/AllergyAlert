"""바코드 정규화. 저장할 때(prepare_data.py)와 조회할 때 같은 규칙을 쓴다.
1) 숫자 아닌 문자 제거  2) 12자리면 앞에 0 (UPC-A -> EAN-13)"""
import re

# 팀에서 하나로 정할 것: 기능 명세는 8~14, 데이터 모델은 8~13. 여기서만 바꾸면 된다.
MIN_LEN = 8
MAX_LEN = 14


def normalize_barcode(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return "0" + digits if len(digits) == 12 else digits


def is_valid_length(normalized: str) -> bool:
    return MIN_LEN <= len(normalized) <= MAX_LEN
