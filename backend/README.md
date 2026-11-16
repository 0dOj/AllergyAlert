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
| F-05~07 판정 (기본은 공유 프로필, `member_id` 를 주면 그 구성원 기준) | `GET /products/{report_no}/judge?barcode=&member_id=` |
| F-08 알레르겐 목록 / 프로필 | `GET /allergens`, `GET/PUT /profile` |
| F-10 이력 (로그인 토큰 필요) | `POST /history`, `GET /history?member_id=`, `GET /history/{id}`, `DELETE /history/{id}` |
| 구성원 (로그인 토큰 필요) | `GET /members`, `POST /members`, `PUT /members/{id}`, `DELETE /members/{id}` |
| 점검 | `GET /health` |

- 제품명 검색: 2글자 이상(공백 제외), 단어는 공백 구분(모두 포함), 최대 20건, 0건도 200 + `[]`. 인덱스가 없어 드문 검색어는 전체를 훑으므로 3초(`SEARCH_TIMEOUT_MS`)가 지나면 `503`으로 중단한다. `scope=barcodes`는 원재료가 없는 포장육·수입식품도 찾는다.
- 프로필이 비어 있으면 판정·이력 저장은 `400` + `{"action": "set_profile"}`.
- `member_id` 는 선택이다. 없으면 지금처럼 공유 프로필로 판정하고 토큰도 필요 없다. 있으면 토큰이 필요하고(없으면 `401`) 내 구성원의 알레르겐으로 판정한다. 남의 구성원이거나 없으면 `404`, 구성원의 코드가 비어 있거나 사전에 있는 코드가 하나도 없으면 `400` + `{"action": "set_allergens"}` 이다. 형식이 틀린 id 는 `422`.
- `POST /history` 의 본문에도 `member_id` 를 줄 수 있다. 있으면 그 구성원의 코드로 판정하고 `scan_history.member_id` 에 저장하며, 없으면 `member_id` 는 NULL 이다.
- 판정 응답에 `"member": {"id", "name"}` 이 추가된다(구성원 없이 판정하면 `null`). `profile` 에는 실제 판정에 쓴 코드가 들어간다.
- `GET /history` 항목에는 `member_id`, `member_name` 이 붙고 구성원이 삭제됐으면 둘 다 `null` 이다. `?member_id=` 로 거를 수 있으며 남의 id 는 빈 목록이다. `GET /history/{id}` 는 저장된 스냅샷을 그대로 돌려준다.
- `POST /history` 는 판정을 서버에서 다시 계산해 스냅샷으로 저장한다. `GET /history/{id}` 는 그 스냅샷을 그대로 돌려준다.
- 이력 4개 엔드포인트는 `Authorization: Bearer <Supabase 토큰>` 이 필요하다(익명 로그인 토큰 포함). 토큰은 `SUPABASE_URL` 의 JWKS(ES256)로 검증하고, 실패는 `401`, 서버에 `SUPABASE_URL` 이 없거나 JWKS 를 못 받으면 `503`. 이력은 토큰의 사용자(`owner_id`) 것만 조회·삭제되며 남의 id 는 `404` 이다. `SUPABASE_URL` 이 없어도 다른 엔드포인트는 동작한다.
- 구성원은 사용자당 최대 10명이며 11번째 `POST /members` 는 `409`. `PUT` 은 이름·관계·알레르겐 코드·메모·아바타 색을 통째로 교체한다(빠진 선택 필드는 `null`). 선택 필드 `notes`(200자 이하)와 `avatar_color`(40자 이하)는 앞뒤 공백을 제거하고 빈 문자열이면 `null` 로 저장하며, 길이를 넘기면 `422` 이다. 코드는 사전에 있는 것만 허용하고(없으면 `422` 와 해당 코드), 중복은 입력 순서를 유지해 제거한다. 남의 구성원 id 는 `404`, 형식이 틀린 id 는 `422` 이다.
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
