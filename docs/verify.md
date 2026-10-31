# 실검증: 지금 범위와 격리 근거

## 지금 범위

- 화면 `/verify`와 `POST /api/verify`는 **데모 사이트만** 받습니다. `target`은 `demo`만 허용하고 `repo_dir`·`patch`·실행 명령 등 추가 필드는 422로 거절합니다([`routers/verify.py`](../backend/app/routers/verify.py)의 `VerifyStart`). 사용자 저장소 실검증은 꺼져 있습니다.
- [PR #111](https://github.com/maebsy/YMCA-hackathon-2026/pull/111)부터 요청의 `mode`로 실행 방식을 고릅니다. `reference`(기본)는 사람이 쓴 공격 정의와 기준 수정본을 서버의 데모 파일에서 읽습니다. `ai`는 데모의 SQL 인젝션·반사형 XSS 탐지 결과를 Red·Blue에 보내 공격과 수정본을 생성합니다([`routers/verify.py`](../backend/app/routers/verify.py)의 `VerifyStart`, `_demo_inputs`, `_demo_findings`, `_ai_work`).
- AI 모드도 대상은 데모뿐입니다. 형식·경로·수정 검사를 통과하지 못한 항목은 이유와 함께 건너뛰며, 수정본이 없는 파일의 공격은 실행에서 뺍니다. 실행할 공격 또는 수정본이 없으면 실행하지 않고 `result.status=error`를 돌려줍니다([`llm_bridge.py`](../backend/app/verify/llm_bridge.py)의 `plan_verification`, [`routers/verify.py`](../backend/app/routers/verify.py)의 `_ai_work`). 이 결과는 생성돼 실제 실행한 공격·수정에 대한 판정이며 전체 취약점 해결을 보장하지 않습니다.
- AI 새 실행은 Docker가 없거나 LLM 연결이 설정되지 않았거나 연결 확인이 실패(`LLMUnavailable`)하면 HTTP 503(`VERIFY_UNAVAILABLE`)으로 거절합니다. 최근 완료 결과를 재사용하는 경우에는 환경 확인을 건너뜁니다([`routers/verify.py`](../backend/app/routers/verify.py)의 `_start_ai`, [`test_verify_api.py`](../backend/tests/test_verify_api.py)의 `test_ai_mode_requires_docker`, `test_ai_mode_requires_llm`).

## 사용자 저장소를 켜는 조건

1. **GitHub 로그인: 아직 없음.** 현재 API의 작업 접근 제한과 GitHub 로그인 구현은 별개입니다.
2. **소유권 확인:** 로그인한 계정이 저장소 주인 또는 권한자인지 확인해야 합니다. 방향은 [roadmap](roadmap.md)의 GitHub App(읽기 전용)이며, 구체 방식은 **결정 필요**입니다.
3. **격리: 이미 코드에 있음.** 사용자 저장소는 `trusted=False`로 Docker만 사용하고, Docker를 쓸 수 없으면 거절합니다([`sandbox.py`](../backend/app/verify/sandbox.py)의 `pick_sandbox`, [`verifier.py`](../backend/app/verify/verifier.py)의 `verify`).

현재 검사(`/api/scans`)의 허용 소유자 목록(#69)은 운영자가 정하는 URL 소유자 제한입니다. 비어 있으면 제한이 없고 지정 관리자는 예외입니다. 로그인한 GitHub 계정의 저장소 권한을 확인하는 기능이 아닙니다([`scans.py`](../backend/app/routers/scans.py)의 `_target_allowed`).

## 격리 근거

아래 네 값은 probe가 샌드박스 안에서 읽은 상태입니다. 수정 전·후 **각각 모두 `true`**여야 `isolation_confirmed=true`입니다([`schemas.py`](../backend/app/verify/schemas.py)의 `Isolation.confirmed`, [`verifier.py`](../backend/app/verify/verifier.py)의 `_merge_isolation`).

| 항목 | 어떻게 막나·무엇을 재나 | 코드 위치 | 테스트 |
|---|---|---|---|
| `network_isolated` | `--network none`; Node의 네트워크 인터페이스 중 비내부 주소가 없음을 확인. 외부 접속 시험은 아님 | [`sandbox.py`](../backend/app/verify/sandbox.py)의 `DockerSandbox.run`, [`probe.mjs`](../backend/app/verify/probe.mjs)의 `isolationCheck` | [`test_verify.py`](../backend/tests/test_verify.py)의 `test_user_repo_without_confirmed_isolation_is_error`; 아래 Docker 실측 |
| `non_root` | 이미지의 `USER runner`; `process.getuid()`가 0이 아님을 확인 | [`sandbox.py`](../backend/app/verify/sandbox.py)의 `_DOCKERFILE`, [`probe.mjs`](../backend/app/verify/probe.mjs)의 `isolationCheck` | [`test_verify.py`](../backend/tests/test_verify.py)의 `test_user_repo_with_confirmed_isolation_is_judged`; 아래 Docker 실측 |
| `caps_dropped` | `--cap-drop ALL`; `/proc/self/status`의 `CapEff`가 0인지 확인 | [`sandbox.py`](../backend/app/verify/sandbox.py)의 `DockerSandbox.run`, [`probe.mjs`](../backend/app/verify/probe.mjs)의 `isolationCheck` | [`test_verify.py`](../backend/tests/test_verify.py)의 `test_isolation_must_hold_in_both_runs`; 아래 Docker 실측 |
| `no_new_privs` | `--security-opt no-new-privileges`; 같은 상태 파일의 `NoNewPrivs`가 1인지 확인 | [`sandbox.py`](../backend/app/verify/sandbox.py)의 `DockerSandbox.run`, [`probe.mjs`](../backend/app/verify/probe.mjs)의 `isolationCheck` | [`test_verify.py`](../backend/tests/test_verify.py)의 `test_user_repo_with_confirmed_isolation_is_judged`; 아래 Docker 실측 |

표의 단위 테스트는 샌드박스 출력을 주입해 판정 조건을 확인하며, 아래 Docker 실측과 구분합니다.

- 실행 옵션은 `--rm -i --network none --memory 512m --cpus 1 --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges`입니다([`sandbox.py`](../backend/app/verify/sandbox.py)의 `DockerSandbox.__init__`, `DockerSandbox.run`). 메모리·CPU·프로세스 상한은 네 가지 실측값과 별개이며, 상한에 도달하는 부하 시험은 하지 않았습니다.
- 이미지 빌드는 네트워크를 사용하고 의존성 설치에 `--ignore-scripts`를 적용합니다. 위 실행 제한을 빌드 단계까지 확인했다는 뜻은 아닙니다([`sandbox.py`](../backend/app/verify/sandbox.py)의 `_DOCKERFILE`).
- 사용자 저장소에서 한 항목이라도 `false` 또는 미확인이면 공격 판정 전에 `error`를 반환합니다([`verifier.py`](../backend/app/verify/verifier.py)의 `verify`). [`verify-panel.tsx`](../frontend/src/components/verify-panel.tsx)의 `Result` 격리 안내와 구현이 일치합니다.
- AI 모드도 `trusted=False`여서 Docker 필수·격리 네 항목 게이트가 적용됩니다([`routers/verify.py`](../backend/app/routers/verify.py)의 `_ai_work`, [`test_verify_api.py`](../backend/tests/test_verify_api.py)의 `test_ai_mode_runs_model_attacks_and_patch_in_docker_only`).
- **기준 수정본 모드**만 `trusted=True`여서 Docker가 없으면 격리 없는 LocalSandbox로 실행할 수 있고, 네 항목 미확인 거절 조건도 적용되지 않습니다([`routers/verify.py`](../backend/app/routers/verify.py)의 `start_verify`, [`sandbox.py`](../backend/app/verify/sandbox.py)의 `pick_sandbox`).

## 실제 실행 결과: 기준 수정본 모드

- 날짜: **2026-10-31**, 이 PC의 **Docker Desktop 4.78.0 (229452), Engine 29.5.3, linux/amd64**.
- 실측 당시 main 커밋: `3678dab4a42381290728ec14a9e17b25cab68eea`(#111 반영 전). 화면 문구만 바꾼 worktree 커밋 `e74e76c`의 기준 수정본 동작으로 실행했습니다. 현재 문서·테스트에는 #111이 머지된 `0f825b1`을 반영했습니다.
- 새 Python 프로세스에서 실제 라우터를 TestClient에 연결해 `POST /api/verify` → `GET` 폴링했습니다. DB·LLM 초기화는 생략하고 `VERIFY_REUSE_SECONDS=0`, `reused=false`로 새 실행임을 확인했습니다.
- 잘못된 `target`, `repo_dir`, `patch`, `start_cmd` 요청은 실제 API 응답에서 각각 422였습니다.

| 확인 항목 | 이번 실행 결과 |
|---|---|
| 실행 환경·최종 판정 | `sandbox=docker`, `status=verified` |
| SQL 인젝션(`sqli-orders`) | 수정 전 공격 성공 `true` → 수정 후 `false`; `verified` |
| 반사형 XSS(`xss-search`) | 수정 전 공격 성공 `true` → 수정 후 `false`; `verified` |
| 기능 테스트 | 수정 전 3건 통과·0건 실패, 수정 후 3건 통과·0건 실패 |
| `network_isolated` | `true` |
| `non_root` | `true` |
| `caps_dropped` | `true` |
| `no_new_privs` | `true` |
| 종합 격리 확인 | `isolation_confirmed=true`(전·후 모두 확인) |
| 엔진 소요 시간 | `duration_sec=65.61` |

**운영 서버에서 확인한 값은 아닙니다.** 이 결과는 로컬 Docker의 데모 기준 수정본 모드 1회 실행 근거입니다. AI 모드는 LLM이 필요하며 이 PC에서 실제 실행하지 않았습니다. 사용자 저장소 실행과 운영 서버 환경도 확인하지 않았습니다.
전체 JSON(`verify-docker-evidence-20261031.json`)과 일회성 실행 스크립트(`run-verify-docker-evidence-20261031.py`)는 이 PC 원래 저장소의 `docs_ignore/`에 보관하며 커밋하지 않습니다. 데모 응답·수정본의 비밀값 형태 문자열은 이 문서에 옮기지 않았습니다.

## 발표에 쓸 수 있는 문장

- “지금은 우리 데모 사이트에서 기준 수정본 모드와 AI(Red·Blue) 모드를 제공합니다. 내 저장소 실검증은 GitHub 로그인과 소유권 확인 뒤에 켭니다.”
- “모델이 만든 코드는 사용자 저장소와 같은 격리 조건에서만 실행합니다. Docker가 없거나 격리 네 항목을 모두 확인하지 못하면 판정하지 않습니다.”
- “2026년 10월 31일 이 PC의 Docker 기준 수정본 실행에서 격리 네 항목이 모두 확인됐고, 데모 공격 두 건은 수정 후 차단됐으며 기능 테스트는 전·후 각각 세 건 통과했습니다. AI 모드와 운영 서버의 실측 결과는 아닙니다.”
