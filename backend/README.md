# 백엔드 (FastAPI)

## 실행 (Windows PowerShell, CapstoneProject\backend 폴더에서)
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --reload-dir app
```
브라우저에서 http://127.0.0.1:8000/docs (API 시험 화면), http://127.0.0.1:8000/health

`Activate.ps1` 이 막히면: `Set-ExecutionPolicy -Scope Process Bypass` 후 다시 실행.

## API
| 기능 | 엔드포인트 |
|---|---|
| F-03 바코드 조회 | `GET /products/barcode/{barcode}` |
| F-04 제품명 검색 | `GET /products/search?q=&scope=reports\|barcodes&sort=fast\|relevance` |
| F-05~07 판정 (저장된 프로필 기준) | `GET /products/{report_no}/judge?barcode=` |
| F-08 알레르겐 목록 / 프로필 | `GET /allergens`, `GET/PUT /profile` |
| F-10 이력 (로그인 토큰 필요) | `POST /history`, `GET /history`, `GET /history/{id}`, `DELETE /history/{id}` |
| 점검 | `GET /health` |

- 제품명 검색: 2글자 이상(공백 제외), 단어는 공백 구분(모두 포함), 최대 20건, 0건도 200 + `[]`. 인덱스가 없어 드문 검색어는 전체를 훑으므로 3초(`SEARCH_TIMEOUT_MS`)가 지나면 `503`으로 중단한다. `scope=barcodes`는 원재료가 없는 포장육·수입식품도 찾는다.
- 프로필이 비어 있으면 판정·이력 저장은 `400` + `{"action": "set_profile"}`.
- `POST /history` 는 판정을 서버에서 다시 계산해 스냅샷으로 저장한다. `GET /history/{id}` 는 그 스냅샷을 그대로 돌려준다.
- 이력 4개 엔드포인트는 `Authorization: Bearer <Supabase 토큰>` 이 필요하다(익명 로그인 토큰 포함). 토큰은 `SUPABASE_URL` 의 JWKS(ES256)로 검증하고, 실패는 `401`, 서버에 `SUPABASE_URL` 이 없거나 JWKS 를 못 받으면 `503`. 이력은 토큰의 사용자(`owner_id`) 것만 조회·삭제되며 남의 id 는 `404` 이다. `SUPABASE_URL` 이 없어도 다른 엔드포인트는 동작한다.
- `user_profile.allergen_ids` 에는 알레르겐 **코드**(MILK 등)를 저장한다.
- 알레르겐 사전은 서버 시작 후 처음 필요할 때 읽어 메모리에 둔다. 시드를 고치면 서버를 재시작한다.

## 테스트
```
pytest -v
```
DB 에 쓰기를 하는 흐름 테스트(`test_flow_api.py`)는 기본으로 건너뛴다. 이력 관련 3개는 토큰 방식으로 교체할 때까지 항상 건너뛴다. 실행하려면:
```
$env:ALLOW_DB_WRITE_TESTS = "1"
pytest -v
```
(실행 전 프로필을 저장했다가 복원하고, 만든 이력은 삭제한다.)
설정은 저장소 루트의 `.env` (`DATABASE_URL`)를 읽는다. `.env.example` 참고.

## 폴더 구조
```
CapstoneProject/
  .env, .env.example, .gitignore   # 설정 (.env 는 git 제외)
  명세서/
  backend/
    app/        # FastAPI 서버
    tests/
    DB/         # sql/, scripts/, seed.json, csv/, csvgz/, README.md
```
`.env` 는 `backend/.env` 또는 `CapstoneProject/.env` 에 둘 수 있다(앞이 우선).

## 배포 (호스팅 미확정)
- `Dockerfile` 이 준비되어 있다 (빌드 컨텍스트: `backend/`). 호스팅이 주는 `PORT` 환경변수를 사용한다.
- 호스팅 환경변수에 `DATABASE_URL`(app_backend), `SUPABASE_URL`(토큰 검증), `ALLOWED_ORIGINS`(프론트 주소)를 설정한다. 휴대폰 시연은 `../docs/phone-demo.md`.
- 시작 명령(컨테이너를 쓰지 않는 호스팅): `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- 운영 의존성은 `requirements.txt`, 개발·테스트용은 `requirements-dev.txt`.
