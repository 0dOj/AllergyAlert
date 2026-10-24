# 알레르기 체크 앱 — AllergyAlertDB

바코드를 스캔해 식약처 공공데이터에서 원재료를 조회하고, 등록한 알레르겐 포함 여부를 판정한다.
(기획: `명세서/`)

```
명세서/            기능 명세서, 데이터 모델, 프로젝트 개요
backend/
  app/             FastAPI 서버 (바코드 조회, 제품명 검색, 판정, 프로필, 이력)
  tests/           pytest
  DB/              Supabase 스키마·시드·적재 스크립트 (README.md 참고)
.github/workflows/ CI (push/PR 마다 pytest)
.devcontainer/     GitHub Codespaces 개발 환경
docs/              휴대폰 시연 가이드
```

## 시작하기 (로컬)
1. 팀에서 받은 `DATABASE_URL` 로 `.env` 만들기: `.env.example` 복사 -> `.env` (**git에 올리지 않는다**)
2. 백엔드
   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
   pip install -r requirements-dev.txt
   pytest -v
   uvicorn app.main:app --reload --reload-dir app
   ```
   http://127.0.0.1:8000/docs 에서 API 를 시험할 수 있다.

## 시작하기 (GitHub Codespaces, 설치 없이)
1. 저장소 > Code > Codespaces > Create codespace
2. 저장소 Settings > Secrets and variables > Codespaces 에 `DATABASE_URL` 등록 (개인 비밀로 등록)
3. 터미널에서 `cd backend && uvicorn app.main:app --reload --reload-dir app`
4. 포트 8000 의 공개 주소(HTTPS)로 접속. 휴대폰 시연에도 쓸 수 있다.
   (무료 사용량 한도가 있다. 한도와 조건은 GitHub 문서를 확인)

## 문서
- DB: `backend/DB/README.md`
- 백엔드 API: `backend/README.md`
- 휴대폰 시연: `docs/phone-demo.md`
- 배포: 호스팅 미확정. `backend/Dockerfile` 이 준비되어 있다.

## 기여 규칙
- `main` 에 직접 push 하지 않고 브랜치 -> Pull Request. CI(pytest)가 통과해야 합친다.
- 비밀번호·키는 절대 커밋하지 않는다 (`.env` 는 `.gitignore` 대상).
- DB 스키마 변경은 `backend/DB/sql/` 에 번호를 붙인 SQL 파일로 남긴다.
