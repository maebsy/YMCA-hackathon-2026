# 실검증: 지금 범위와 격리 근거

## 지금 범위

- 화면 `/verify`와 `POST /api/verify`는 **데모 사이트만** 받습니다. `target`은 `demo`만 허용하고 `repo_dir`·`patch`·실행 명령 등 추가 필드는 422로 거절합니다([verify.py:53](../backend/app/routers/verify.py#L53)).
- 공격 정의와 기준 수정본은 서버의 데모 파일에서 읽습니다([verify.py:75](../backend/app/routers/verify.py#L75), [실행:103](../backend/app/routers/verify.py#L103)). 사용자 저장소 실검증은 꺼져 있습니다.
- 현재 시연은 미리 정의한 공격과 기준 수정본을 비교합니다. 임의 저장소나 AI가 만든 수정 전체에 대한 보장을 뜻하지 않습니다.

## 사용자 저장소를 켜는 조건

1. **GitHub 로그인: 아직 없음.** 현재 API의 작업 접근 제한과 GitHub 로그인 구현은 별개입니다.
2. **소유권 확인:** 로그인한 계정이 저장소 주인 또는 권한자인지 확인해야 합니다. 방향은 [roadmap](roadmap.md)의 GitHub App(읽기 전용)이며, 구체 방식은 **결정 필요**입니다.
3. **격리: 이미 코드에 있음.** 사용자 저장소는 `trusted=False`로 Docker만 사용하고, Docker를 쓸 수 없으면 거절합니다([sandbox.py:118](../backend/app/verify/sandbox.py#L118), [오류 반환:67](../backend/app/verify/verifier.py#L67)).

현재 검사(`/api/scans`)의 허용 소유자 목록(#69, `_target_allowed`)은 운영자가 정하는 URL 소유자 제한입니다. 비어 있으면 제한이 없고 지정 관리자는 예외입니다. 로그인한 GitHub 계정의 저장소 권한을 확인하는 기능이 아닙니다([scans.py:244](../backend/app/routers/scans.py#L244)).

## 격리 근거

아래 네 값은 probe가 샌드박스 안에서 읽은 상태입니다. 수정 전·후 **각각 모두 `true`**여야 `isolation_confirmed=true`입니다([schemas.py:79](../backend/app/verify/schemas.py#L79), [합산:150](../backend/app/verify/verifier.py#L150)).

| 항목 | 어떻게 막나·무엇을 재나 | 코드 위치 | 테스트 |
|---|---|---|---|
| `network_isolated` | `--network none`; Node의 네트워크 인터페이스 중 비내부 주소가 없음을 확인. 외부 접속 시험은 아님 | [sandbox.py:85](../backend/app/verify/sandbox.py#L85), [probe.mjs:94](../backend/app/verify/probe.mjs#L94) | [미확인 거절:147](../backend/tests/test_verify.py#L147); 아래 Docker 실측 |
| `non_root` | 이미지의 `USER runner`; `process.getuid()`가 0이 아님을 확인 | [sandbox.py:103](../backend/app/verify/sandbox.py#L103), [probe.mjs:107](../backend/app/verify/probe.mjs#L107) | [네 항목 확인 게이트:158](../backend/tests/test_verify.py#L158); 아래 Docker 실측 |
| `caps_dropped` | `--cap-drop ALL`; `/proc/self/status`의 `CapEff`가 0인지 확인 | [sandbox.py:87](../backend/app/verify/sandbox.py#L87), [probe.mjs:99](../backend/app/verify/probe.mjs#L99) | [전·후 모두 확인:166](../backend/tests/test_verify.py#L166); 아래 Docker 실측 |
| `no_new_privs` | `--security-opt no-new-privileges`; 같은 상태 파일의 `NoNewPrivs`가 1인지 확인 | [sandbox.py:87](../backend/app/verify/sandbox.py#L87), [probe.mjs:101](../backend/app/verify/probe.mjs#L101) | [네 항목 확인 게이트:158](../backend/tests/test_verify.py#L158); 아래 Docker 실측 |

표의 기존 단위 테스트는 샌드박스 출력을 주입해 판정 조건을 확인합니다. 이번 문서 작업에서는 pytest를 재실행하지 않았습니다.

- 실행 옵션은 `--rm -i --network none --memory 512m --cpus 1 --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges`입니다([기본값:64](../backend/app/verify/sandbox.py#L64), [명령:84](../backend/app/verify/sandbox.py#L84)). 메모리·CPU·프로세스 상한은 네 가지 실측값과 별개이며, 상한에 도달하는 부하 시험은 하지 않았습니다.
- 이미지 빌드는 네트워크를 사용하고 의존성 설치에 `--ignore-scripts`를 적용합니다. 위 실행 제한을 빌드 단계까지 확인했다는 뜻은 아닙니다([sandbox.py:95](../backend/app/verify/sandbox.py#L95)).
- 사용자 저장소에서 한 항목이라도 `false` 또는 미확인이면 공격 판정 전에 `error`를 반환합니다([verifier.py:91](../backend/app/verify/verifier.py#L91)). [화면 안내:78](../frontend/src/components/verify-panel.tsx#L78)와 구현이 일치합니다.
- 데모는 `trusted=True`여서 Docker가 없으면 격리 없는 LocalSandbox로 실행할 수 있고, 네 항목 미확인 거절 조건도 적용되지 않습니다([verify.py:115](../backend/app/routers/verify.py#L115), [sandbox.py:118](../backend/app/verify/sandbox.py#L118)).

## 실제 실행 결과

- 날짜: **2026-10-31**, 이 PC의 **Docker Desktop 4.78.0 (229452), Engine 29.5.3, linux/amd64**.
- 기준 main 커밋: `3678dab4a42381290728ec14a9e17b25cab68eea`. 화면 문구만 바꾼 worktree 커밋 `e74e76c`에서 실행했습니다.
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

**운영 서버에서 확인한 값은 아닙니다.** 이 결과는 로컬 Docker의 데모 1회 실행 근거입니다. 사용자 저장소 실행과 운영 서버 환경은 확인하지 않았습니다.
전체 JSON(`verify-docker-evidence-20261031.json`)과 일회성 실행 스크립트(`run-verify-docker-evidence-20261031.py`)는 이 PC 원래 저장소의 `docs_ignore/`에 보관하며 커밋하지 않습니다. 데모 응답·수정본의 비밀값 형태 문자열은 이 문서에 옮기지 않았습니다.

## 발표에 쓸 수 있는 문장

- “지금은 우리 데모 사이트에서 정해진 공격과 기준 수정본을 실행해 비교합니다. 내 저장소 실검증은 GitHub 로그인과 소유권 확인 뒤에 켭니다.”
- “사용자 저장소용 엔진은 Docker가 없거나 격리 네 항목을 모두 확인하지 못하면 실검증 판정을 내지 않도록 구현돼 있습니다.”
- “2026년 10월 31일 이 PC의 Docker 실행에서 격리 네 항목이 모두 확인됐고, 데모 공격 두 건은 수정 후 차단됐으며 기능 테스트는 전·후 각각 세 건 통과했습니다. 운영 서버 확인 결과는 아닙니다.”
