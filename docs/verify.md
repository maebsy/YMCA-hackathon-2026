# 데모 실행 검증: 공격 재현과 패치 확인

실행 검증은 같은 데모 앱을 수정 전·후로 실행해 공격 성공 여부와 기능 테스트를 비교합니다. [LLM 해석의 Red 검토](llm.md)가 수정 지시를 평가하는 것과 달리 실제 프로세스를 실행합니다. **현재 웹 `/verify`와 공개 API가 받는 대상은 저장소에 포함된 데모 앱뿐입니다. 임의의 GitHub 저장소를 실행 검증하는 서비스는 제공하지 않습니다.**

## 두 가지 실행 모드

| 모드 | 공격·수정본 출처 | 실행 조건 |
|---|---|---|
| `reference` (기본) | [데모 공격 정의](../demo-vulnerable-site/verify/attacks.json)와 [기준 수정본](../demo-vulnerable-site/verify/fix) | Docker 우선. Docker가 없으면 신뢰된 데모에 한해 Node.js 22.5.0 이상·npm으로 로컬 실행 가능 |
| `ai` | 로컬 LLM의 Red가 HTTP 공격을, Blue가 코드 편집을 생성 | 새 실행에 Docker와 LLM 연결 필수. 비신뢰 코드로 취급해 격리 확인 후 판정 |

AI 모드의 입력은 데모 SQL 인젝션과 반사형 XSS 두 항목입니다. 경로·수정 범위·형식 검사를 통과하지 못한 항목은 이유와 함께 건너뜁니다. 수정본이 없는 파일의 공격은 실행에서 제외하며, 유효한 공격 또는 수정본이 하나도 없으면 `result.status=error`입니다. 실행 후 `fix_failed`이고 피드백을 만들 수 있으면 Blue에 재수정을 요청하며 최대 두 번 실행합니다. 출력에는 공격 정의, 패치 diff, 건너뛴 이유와 시도별 결과가 포함됩니다.

구현 기준은 [routers/verify.py](../backend/app/routers/verify.py)와 [llm_bridge.py](../backend/app/verify/llm_bridge.py)입니다. AI가 생성·선택한 공격만 실행하므로 통과해도 전체 취약점이나 모든 우회 경로가 해결됐다는 뜻은 아닙니다.

## API 사용

백엔드는 [프로젝트 실행 방법](../README.md)에 따라 실행합니다. 기준 수정본 모드에는 Docker 또는 Node.js 22.5.0 이상·npm이 필요하고, AI 모드에는 Docker와 [LLM 연결 설정](llm.md)이 필요합니다. 로컬 Node 버전 조건은 `node:sqlite`를 사용하는 [데모 package.json](../demo-vulnerable-site/package.json)을 따릅니다. 다음 예시는 Bash에서 실행합니다.

```bash
curl -X POST http://localhost:8000/api/verify \
  -H 'Content-Type: application/json' \
  -d '{"target":"demo","mode":"reference"}'
# HTTP 202 응답의 job_id로 조회
curl http://localhost:8000/api/verify/JOB_ID
```

AI 모드는 `mode`만 `ai`로 바꿉니다. `target`은 `demo`만 허용하고 `repo_dir`, `patch`, `start_cmd` 같은 추가 필드는 HTTP 422로 거절합니다. 인증을 켠 구성(`SCAN_REQUIRE_AUTH=true` 또는 `LLM_JOBS_ENABLED=true`)에서는 유효한 Bearer 토큰이 필요합니다. 기본 비인증 데모에서 작업 ID는 접근 제어 수단이 아니므로 민감한 대상 데이터를 넣지 않습니다.

작업 상태는 `queued` → `running` → `done` / `failed`입니다. **`done`은 실행 처리가 끝났다는 뜻이므로 반드시 `result.status`를 확인해야 합니다.**

| `result.status` | 의미 |
|---|---|
| `verified` | 실행한 공격이 수정 전 성공하고 수정 후 실패함. 기능 테스트의 세부 결과도 별도 확인 필요 |
| `fix_failed` | 수정 후에도 공격 성공, 앱 실행 실패 또는 새 기능 테스트 실패 |
| `not_reproduced` | 수정 전 공격이 성공하지 않아 수정 효과를 증명하지 못함 |
| `error` | 환경·격리·입출력 문제 등으로 판정할 수 없음 |

기능 테스트가 수정 전부터 실패한 경우 현재 판정기는 그 사실을 메시지로 남기면서 공격 차단 결과를 `verified`로 반환할 수 있습니다. 따라서 `before_tests`, `after_tests`, `message`, 개별 `attacks`를 함께 읽어야 합니다. 판정 기준은 [verifier.py](../backend/app/verify/verifier.py), 응답 규격은 [schemas.py](../backend/app/verify/schemas.py)를 따릅니다.

### 대기열과 결과 재사용

[VerifyJobs](../backend/app/verify/jobs.py)는 메모리에 최대 3건(실행 중 + 대기)을 접수하고 한 번에 1건을 실행합니다. 완료 결과는 기본 30분·최대 20개 보관하며 재시작하면 사라집니다. 큐가 차면 429 `VERIFY_QUEUE_FULL`, 만료·없는 ID 또는 인증된 다른 사용자의 작업 조회는 404입니다.

기본 `VERIFY_REUSE_SECONDS=300` 동안 같은 모드의 최근 완료 결과(`error` 제외)를 요청자 소유의 새 작업으로 복사할 수 있습니다. **`reused=true`이면 새 LLM 추론이나 새 Docker 실행의 증거가 아닙니다.** 실패 판정인 `fix_failed`·`not_reproduced`도 재사용될 수 있습니다. 재사용에서는 Docker·LLM 연결 확인을 건너뜁니다. 새 실행만 측정하려면 운영자가 별도 검증 환경에서 `VERIFY_REUSE_SECONDS=0`으로 구성하고 응답의 `reused=false`를 확인합니다.

## 격리 범위와 확인 방식

원본을 수정 전·후 임시 작업 디렉터리로 복사하고 수정본에만 패치를 적용합니다. Docker 실행은 `--network none`, 메모리 512MB, CPU 1개, 프로세스 256개 상한, 전체 capability 제거, `no-new-privileges`를 사용합니다. 구현은 [sandbox.py](../backend/app/verify/sandbox.py)입니다.

| 응답 값 | 설정과 관측 근거 |
|---|---|
| `network_isolated` | `--network none`; probe가 비내부 네트워크 주소가 없는지 확인. 외부 접속 침투 시험은 아님 |
| `non_root` | 이미지의 `USER runner`; UID가 0이 아닌지 확인 |
| `caps_dropped` | `--cap-drop ALL`; `/proc/self/status`의 `CapEff=0` 확인 |
| `no_new_privs` | `--security-opt no-new-privileges`; `NoNewPrivs=1` 확인 |

[probe.mjs](../backend/app/verify/probe.mjs)가 수정 전·후 각각 위 값을 읽습니다. 네 항목이 두 실행에서 모두 `true`여야 `isolation_confirmed=true`입니다. AI 모드의 `trusted=False`는 하나라도 `false` 또는 미확인이면 공격 판정 전에 `error`를 반환합니다.

기준 수정본 모드의 `trusted=True`는 Docker가 없어도 격리 없는 `LocalSandbox`를 허용합니다. 이 경우 실행 성공을 Docker 격리 성공으로 표시하면 안 됩니다. **실행 격리와 이미지 빌드 격리도 구분합니다.** 빌드는 네트워크를 사용해 npm 의존성을 설치하며 `--ignore-scripts`를 적용하지만, 위 런타임 격리 확인이 빌드 단계까지 보호를 증명하지 않습니다. 자원 상한에 도달하는 부하 시험이나 컨테이너 탈출 방어 평가도 이 네 값으로 대체할 수 없습니다.

판정·격리 조건을 주입된 샌드박스 결과로 확인하는 테스트는 [test_verify.py](../backend/tests/test_verify.py), API 입력 제한·모드·재사용 테스트는 [test_verify_api.py](../backend/tests/test_verify_api.py)에 있습니다. 이 단위 테스트 통과와 실제 Docker 실행 근거는 구분해야 합니다.

내부 모듈에 저장소 경로를 받는 `trusted=False` 함수가 있어도 공개 API의 사용자 저장소 지원을 의미하지 않습니다. 현재 검사 API의 허용 소유자 목록도 운영자가 정하는 URL 제한이며 GitHub 계정의 저장소 권한 증명이 아닙니다([scans.py](../backend/app/routers/scans.py)). 사용자 로그인·작업 소유권과 GitHub 저장소 권한 확인은 별개입니다.

## 실행 결과 보관

현재 검증 근거는 커밋·Node/Docker 버전·모드·재사용 여부와 함께 API 응답을 보관합니다. 새 실행을 확인하려면 `reused=false`를, Docker 격리를 확인하려면 `sandbox=docker`와 수정 전후의 격리 항목을 확인합니다. 공격별 전후 결과와 기능 테스트 결과도 함께 남깁니다. 두 데모 공격의 성공 사례만으로 서비스 전체의 탐지율·오탐률·패치 정확도를 산출할 수 없습니다.

## 운영 서버에서 실행한 결과: 기준 수정본 모드

- 날짜: **2026-11-01**. 운영 서버의 백엔드·Docker에 연결한 MCP `verify_demo(mode="reference")`로 실행했습니다([PR #141](https://github.com/maebsy/YMCA-hackathon-2026/pull/141)의 "운영 서버 실측", 머지 커밋 `e6faa7e`).
- 결과: 28.2초, `status=verified`, `sandbox=docker`, `isolation_confirmed=true`, SQL 인젝션·반사형 XSS 모두 `verified`.
- 대상은 위와 같은 데모 과녁이며, AI 모드와 사용자 저장소 실행 결과는 아닙니다.
