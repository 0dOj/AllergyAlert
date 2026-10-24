"""제품명 검색 (F-04). 부분 일치(LIKE), 최대 20건."""
import re

MIN_CHARS = 2        # 공백을 뺀 글자 수
MAX_LEN = 50
MAX_TOKENS = 5
LIMIT = 20


def parse_query(q: str) -> list[str]:
    """공백으로 나눈 단어 목록. 규칙에 어긋나면 ValueError(사용자에게 보여줄 메시지)."""
    tokens = re.sub(r"\s+", " ", (q or "").strip()).split(" ")
    tokens = [t for t in tokens if t]
    if sum(len(t) for t in tokens) < MIN_CHARS:
        raise ValueError(f"검색어는 {MIN_CHARS}글자 이상 입력하세요.")
    if len(" ".join(tokens)) > MAX_LEN or len(tokens) > MAX_TOKENS:
        raise ValueError(f"검색어가 너무 깁니다 (최대 {MAX_LEN}자, 단어 {MAX_TOKENS}개).")
    return tokens


def escape_like(s: str) -> str:
    """LIKE 의 특수문자 \\ % _ 를 글자 그대로 검색하도록 이스케이프한다."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_where(column: str, tokens: list[str]) -> tuple[str, dict]:
    """모든 단어가 포함된 행 (AND). 값은 항상 바인딩 파라미터로 넘긴다."""
    parts, params = [], {}
    for i, t in enumerate(tokens):
        parts.append(f"{column} like :t{i} escape '\\'")
        params[f"t{i}"] = f"%{escape_like(t)}%"
    return " and ".join(parts), params
