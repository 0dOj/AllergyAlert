# 휴대폰 시연 가이드

## 왜 터널이 필요한가
- 휴대폰 브라우저의 **카메라(바코드 스캔)는 HTTPS 페이지에서만** 켜진다 (localhost 예외).
  같은 Wi-Fi의 `http://192.168.x.x:5173` 로 접속하면 카메라가 막힌다.
- 호스팅 없이도 노트북에서 돌리는 앱에 **임시 HTTPS 주소**를 붙일 수 있다 (터널).

## 가장 간단한 구성: 터널 하나만 쓰기 (CORS 문제 없음)
프론트 개발 서버가 `/api` 요청을 백엔드로 넘겨주면(프록시) 주소가 하나라서 터널도 하나면 된다.

프론트(`vite.config.ts`):
```ts
export default defineConfig({
  server: {
    host: true,
    allowedHosts: true,          // 터널 주소(*.trycloudflare.com 등) 허용
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
```
프론트 코드는 API 주소를 **상대 경로 `/api/...`** 로 호출한다 (예: `fetch("/api/products/barcode/" + code)`).

## 실행 순서 (노트북 3개 창)
1. 백엔드: `cd backend` -> `uvicorn app.main:app --reload --reload-dir app`
2. 프론트: `npm run dev` (기본 포트 5173)
3. 터널:
   ```
   winget install --id Cloudflare.cloudflared      # 처음 한 번
   cloudflared tunnel --url http://localhost:5173
   ```
   출력되는 `https://xxxx.trycloudflare.com` 주소를 휴대폰에서 연다.

주의
- 주소는 터널을 켤 때마다 바뀌고, 노트북이 꺼지거나 창을 닫으면 끊긴다. 시연 직전에 켠다.
- 같은 방식으로 ngrok 도 쓸 수 있다 (계정 필요).
- 서비스 조건(무료 한도, 안정성)은 바뀔 수 있으니 시연 전에 공식 문서를 확인한다.
- 프론트와 백엔드를 **서로 다른 주소**로 띄우는 경우에는 백엔드 `.env` 에 `ALLOWED_ORIGINS`(고정 주소) 또는
  `ALLOWED_ORIGIN_REGEX`(터널 주소 패턴)를 설정해야 한다.

## 시연 전 체크리스트
- [ ] 휴대폰 카메라 권한 허용 (거부 시 수동 입력으로 전환되는지)
- [ ] `/health` 가 ok 인지 (Supabase 무료 프로젝트가 일시정지되지 않았는지)
- [ ] 프로필에 알레르겐을 저장했는지 (비어 있으면 판정 400)
- [ ] 시연용 바코드 몇 개로 위험/주의/안전이 각각 나오는지
- [ ] 실제 제품 포장의 바코드가 DB에 있는지 (데이터가 2018년 이후 갱신 중단)
