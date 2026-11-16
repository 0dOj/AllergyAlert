from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import allowed_origin_regex, allowed_origins
from .db import get_engine
from .routers import history, members, ocr, products, profile

app = FastAPI(title="알레르기 체크 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),  # '*' 대신 실제 프론트 주소만 허용
    allow_origin_regex=allowed_origin_regex(),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(profile.router)
app.include_router(history.router)
app.include_router(members.router)
app.include_router(ocr.router)


@app.get("/health")
def health():
    """서버와 DB 연결 확인"""
    with get_engine().connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}
