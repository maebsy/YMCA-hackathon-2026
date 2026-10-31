# demo-vulnerable-site (실검증 과녁)

> **데모·테스트 전용입니다. 실제 서비스로 배포하지 마세요.**
> 72hours 보안엔진이 탐지하고, Red–Blue 실검증이 "수정 전 공격 성공 → 수정 후 차단"을 확인하기 위한
> 일부러 취약하게 만든 작은 사이트입니다. OWASP NodeGoat·Juice Shop 같은 교육용 취약 앱과 같은 성격입니다.
> 모든 키·데이터는 가짜이며, 네트워크·외부 DB가 필요 없습니다(`node:sqlite` 메모리 DB).

## 실행

```bash
npm ci        # 또는 npm install
npm start     # http://127.0.0.1:3100
npm test      # 기능 테스트 (수정 후에도 이게 통과해야 '기능 보존')
```

Node 22.5+ 필요 (`node:sqlite` 내장). 외부 의존성은 `express`, `jsonwebtoken`뿐입니다.

## 일부러 넣은 취약점 (보안엔진이 탐지하는 것)

| # | 위치 | 취약점 | 탐지 | 고치면 |
|---|---|---|---|---|
| 1 | `GET /api/orders?orderId=` | SQL 인젝션 (CWE-89) — 입력을 쿼리 문자열에 그대로 이어 붙임 | 정적 `vibe-coding/sql-string-concat` + 런타임 실검증 | 파라미터 바인딩(`?`) |
| 2 | `GET /search?q=` | 반사형 XSS (CWE-79) — 입력을 이스케이프 없이 HTML에 출력 | 런타임 실검증 (서버측 XSS 정적 규칙은 후속) | 출력 이스케이프 |
| 3 | `server.js` 상단 | 하드코딩 JWT 서명 키 (CWE-798) | 정적 `vibe-coding/jwt-hardcoded-secret` | 환경변수로 이동 |
| 4 | `package.json` | 오래된 라이브러리(알려진 CVE) | 정적 OSV-Scanner (네트워크 필요) | 버전 올리기 |

> 확인됨(10/31): 보안엔진이 1·3번을 탐지(각각 critical·high), 기능 테스트 3건 통과.
> 1·2번은 런타임 실검증에서 "수정 전 공격 성공 → 수정 후 차단 + 기능 보존"까지 확인.
> 2번(반사형 XSS)은 정적 규칙에 안 잡히지만 런타임 공격으로 잡혀, 실검증이 정적 분석을 보완함을 보여 줍니다.

정상 동작(수정 후에도 유지되어야 하는 것):
- `GET /api/orders?orderId=1` → id가 1인 주문 1건만 반환
- `GET /search?q=커피` → "커피" 검색 결과 페이지

## 실검증이 쓰는 파일

`verify/attacks.json` — 각 취약점의 공격 요청과 "성공 판정" 기준. Red가 내는 공격 요청의 예시이자,
실검증 모듈이 수정 전/후에 같은 요청을 보내 결과가 바뀌는지 확인하는 기준입니다.

`verify/fix/server.js` — **기준 수정본**(Blue가 내야 할 수정의 예시). 실검증이 after 사본에 덮어씁니다.
바뀐 곳은 세 군데입니다: 파라미터 바인딩(SQL 주입), 출력 이스케이프(XSS), 서명 키를 환경변수로(하드코딩 키).
이 수정본으로 실검증하면 `verified`가 나오고, 보안엔진으로 재검사하면 SQL 주입·하드코딩 키 탐지가 사라집니다.

## 화면과 API로 실행

- 현재 지원 범위·사용자 저장소 적용 조건·격리 실행 근거: [실검증 문서](../docs/verify.md).
- 화면: 웹의 `/verify`에서 "실검증 실행"을 누르면 판정, 공격별 수정 전/후, 기능 테스트, 격리 4항목, 수정 내용을 보여 줍니다.
- API: 검사 API와 같은 "접수 → 작업 번호 → 조회" 방식입니다 (`backend/app/routers/verify.py`).
  - `POST /api/verify` (본문 `{"target": "demo"}` 또는 비움) → 202 `{job_id, status: "queued"}`
  - `GET /api/verify/{job_id}` → `status`(queued·running·done·failed), 끝나면 `result`(`VerifyResult`), `attacks`(위 공격 정의), `patched_files`, `patch_diff`
- 서버는 이 폴더의 `verify/attacks.json`과 `verify/fix/`만 씁니다. 요청으로 경로·수정본·명령을 보내면 422로 거절합니다. 데모 과녁은 Docker가 없으면 서버에서 격리 없이 실행되기 때문입니다.
- 실행 환경: Docker가 있으면 Docker, 없으면 서버의 Node 22.5 이상과 npm을 씁니다. 둘 다 없으면 503입니다.
- 한 번에 1건만 실행하고(데모 앱이 고정 포트 3100을 씀), 기다리는 것까지 3건을 넘으면 429입니다. 결과는 서버 메모리에만 둡니다.
- 같은 데모의 최근 완료 결과(`error`·실행 실패 제외)는 `VERIFY_REUSE_SECONDS`초(임시 기본값 300초, `0`이면 끔) 동안 실행 환경 확인 없이 요청자 소유의 새 작업 번호로 재사용합니다. 이때 POST는 202 `{job_id, status: "done", reused: true}`, 조회 결과의 `finished_at`은 원래 실행의 UTC 완료 시각입니다.
