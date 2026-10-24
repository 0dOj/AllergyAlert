# 어떤 호스팅(Render, Railway, Fly.io, Cloud Run ...)에서도 쓸 수 있는 컨테이너 설정.
# 빌드 컨텍스트는 backend/ 폴더다:  docker build -t allergy-api backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 호스팅이 PORT 환경변수를 주면 그 포트로, 없으면 8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
