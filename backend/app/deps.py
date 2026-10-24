from functools import lru_cache

from .db import get_engine
from .services.matcher import Dictionary


@lru_cache
def get_dictionary() -> Dictionary:
    """알레르겐 사전은 서버 시작 후 처음 필요할 때 한 번만 DB 에서 읽어 메모리에 둔다.
    시드(allergen_keywords, term_rules)를 고친 뒤에는 서버를 재시작해야 반영된다."""
    with get_engine().connect() as conn:
        return Dictionary.from_db(conn)
