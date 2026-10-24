from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import database_url


@lru_cache
def get_engine() -> Engine:
    # 무료 Supabase 는 동시 접속 수가 제한되므로 풀을 작게 유지한다
    return create_engine(database_url(), pool_size=5, max_overflow=2, pool_pre_ping=True)
