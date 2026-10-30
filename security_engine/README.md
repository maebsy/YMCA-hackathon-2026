# 보안엔진 (security_engine)

검사할 코드 폴더를 받아 **Semgrep · OSV-Scanner · Gitleaks**를 동시에 돌리고, 결과를 하나의 JSON으로 묶습니다.
재검사 때는 지난 결과와 비교해서 **새로 생김 / 계속 있음 / 해결됨 / 확인 불가**와 **4가지 상태**를 정합니다.

```
코드 폴더 ─▶ 스캐너 3개(동시) ─▶ 정규화 ─▶ 지문 ─▶ 이전 결과와 비교 ─▶ 4가지 상태 ─▶ JSON
```

엔진은 **파이썬 표준 라이브러리만** 씁니다. 스캐너 3개는 따로 설치합니다.

## 1. 설치 (Windows 기준)

| 도구 | 설치 | 확인 |
|---|---|---|
| OSV-Scanner | `winget install -e --id Google.OSVScanner` | `osv-scanner --version` |
| Gitleaks | `winget install -e --id Gitleaks.Gitleaks` | `gitleaks version` |
| Semgrep | `pip install semgrep` | `semgrep --version` |

- winget이 안 되면 GitHub 릴리스에서 받아 PATH 폴더에 넣으세요.
  - https://github.com/google/osv-scanner/releases → `osv-scanner_windows_amd64.exe` (이름 그대로 둬도 엔진이 찾음)
  - https://github.com/gitleaks/gitleaks/releases → `gitleaks_<버전>_windows_x64.zip`
- PATH에 넣기 어렵다면 환경 변수로 위치를 알려줘도 됩니다:
  `SECURITY_ENGINE_OSV_BIN`, `SECURITY_ENGINE_SEMGREP_BIN`, `SECURITY_ENGINE_GITLEAKS_BIN`
- Semgrep은 최근 버전부터 Windows에서 바로 돕니다. 설치·실행이 안 되면 WSL(우분투)에서 돌리세요.
- 테스트용: `pip install pytest jsonschema`

설치 확인:

```powershell
python -m security_engine doctor
```

## 2. 실행

### 명령줄 (CLI)

```powershell
# 첫 검사
python -m security_engine scan C:\code\my-site -o outputs\scan1.json

# 고친 뒤 재검사 (지난 결과와 비교)
python -m security_engine scan C:\code\my-site --previous outputs\scan1.json -o outputs\scan2.json

# 저장소 주소로 바로 (clone → 검사 → 임시 폴더 삭제)
python -m security_engine scan --repo-url https://github.com/<id>/<id>.github.io -o outputs\blog.json

# 저장해둔 두 결과만 다시 비교
python -m security_engine compare outputs\scan1.json outputs\scan2.json -o outputs\diff.json

# 검사 결과 → LLM 입력 꾸러미 (JSON, 또는 --text로 프롬프트용 한국어 텍스트)
python -m security_engine llm-input outputs\scan2.json -o outputs\llm_input.json
python -m security_engine llm-input outputs\scan2.json --text
```

| 옵션 | 뜻 |
|---|---|
| `--tools osv,semgrep` | 일부 도구만 |
| `--no-registry` | Semgrep 레지스트리 룰셋(p/default) 없이 우리 규칙만 (상용 서비스·오프라인용) |
| `--with-registry 룰셋` | 레지스트리 룰셋을 바꿔 지정 (기본 `p/default`, 여러 번 가능) |
| `--semgrep-config 경로` | 규칙 파일/폴더 추가 |
| `--osv-offline` | 미리 받아둔 OSV DB만 사용 (인터넷 없을 때. 처음 한 번 `osv-scanner scan source --offline-vulnerabilities --download-offline-databases -r .`) |
| `--include-raw` | 스캐너 원본을 `finding.raw`에 포함 (비밀값은 가림) |
| `--fail-on high` | high 이상 열린 문제가 있으면 종료 코드 1 (CI용) |

결과 JSON은 `-o` 파일로, 사람이 읽는 요약은 화면(표준 오류)으로 나옵니다. `outputs/`는 `.gitignore`에 있어 커밋되지 않습니다.

### 파이썬 함수 (백엔드에서)

```python
from security_engine import scan, scan_repo, compare_results, ScanOptions, CloneError

result = scan("C:/code/my-site")                         # dict (JSON으로 바로 저장 가능)
result2 = scan("C:/code/my-site", previous=result)       # 재검사
result3 = scan_repo("https://github.com/<id>/<id>.github.io", previous=None)

opts = ScanOptions(tools=("semgrep", "gitleaks"), timeout_sec=300)  # 일부 도구만, 도구당 5분
result4 = scan("C:/code/my-site", options=opts)
```

- `scan`은 예외를 거의 던지지 않습니다. 도구가 없거나 실패하면 `coverage`에 이유를 적고 나머지는 계속합니다.
  폴더가 없으면 `NotADirectoryError`, clone 실패는 `CloneError`.
- 한 번 검사에 수 초~수 분 걸리므로 백엔드에서는 **작업자(worker)에서 호출**하세요.
- 고객 저장소 받기는 백엔드가 직접 해도 되고 `scan_repo` / `clone_repo`를 써도 됩니다
  (https 공개 저장소만, 최신 커밋 하나만, 심볼릭 링크는 일반 파일로 받음).

## 3. 출력 JSON (schema_version 1.0)

정확한 규격: [`schema/scan_result.schema.json`](schema/scan_result.schema.json) · 재검사 결과 예시: [`schema/example_rescan_result.json`](schema/example_rescan_result.json)

```jsonc
{
  "schema_version": "1.0",
  "engine": {"name": "security_engine", "version": "0.1.0"},
  "scan_id": "be06b7ea…",
  "scanned_at": "2026-10-30T14:20:49Z",
  "duration_sec": 5.3,
  "target": {"path": "…", "repo_url": null, "commit_sha": "a1b2c3…"},
  "status": "complete",                 // complete | partial(일부 도구 실패) | failed
  "coverage": {                          // 도구별로 실제로 검사했는지
    "osv":      {"status": "ok", "state": "checked", "category": "dependency", "message": "", "version": "2.7.0", "count": 2, "duration_sec": 0.2},
    "semgrep":  {"status": "ok", …},
    "gitleaks": {"status": "no_target" | "not_installed" | "error" | "skipped", "state": "out_of_scope", "message": "이유", …}
  },
  "suppressions": [                      // 저장소의 '검사 예외' 설정 (엔진은 무시하고 검사함)
    {"tool": "osv", "file": "osv-scanner.toml", "kind": "ignore_config", "detail": "GHSA-35jh-r3h4-6jhm"}
  ],
  "summary": {"open": 23, "by_severity": {"critical": 7, …}, "by_category": {…}, "by_status": {…}, "by_change": {…}, "flagged": 3},
  "comparison": null,                    // 재검사면 {"base_scan_id", "new", "persisting", "resolved", "unverifiable", …}
  "dependency_upgrades": [               // "lodash를 4.17.21로 올리면 2개 해결"
    {"ecosystem": "npm", "name": "lodash", "current_version": "4.17.15", "target_version": "4.17.21",
     "lockfile": "package-lock.json", "fixes": ["osv:…", "osv:…"], "unfixable": [], "max_severity": "high"}
  ],
  "findings": [ /* 아래 */ ]
}
```

finding 하나:

```jsonc
{
  "fingerprint": "semgrep:3f2a…",       // 같은 문제 식별자 (줄 번호와 무관)
  "tool": "semgrep",                     // osv | semgrep | gitleaks
  "category": "code",                    // dependency | code | secret
  "rule_id": "vibe-coding/js-eval-dynamic",
  "title": "eval()에 고정 문자열이 아닌 값을 넣고 있습니다.",
  "message": "… 전체 설명 …",
  "severity": "high",                    // critical | high | medium | low | unknown
  "status": "code_issue",                // 4가지 상태 (아래 표)
  "status_label": "코드에서 문제 확인",
  "change": "new",                       // new | persisting | resolved | unverifiable
  "first_seen": "2026-10-30T14:20:49Z",
  "location": {"file": "api/server.js", "start_line": 11, "end_line": 11},
  "package": null,                       // osv면 {"name", "version", "ecosystem", "fixed_versions"}
  "evidence": {
    "snippet": "const r = eval(req.query.expr);",
    "context": {"start_line": 8, "lines": ["…앞뒤 3줄…"]},
    "masked_secret": "sk_l********"      // gitleaks만
  },
  "cwe": ["CWE-95"], "aliases": [], "references": [], "published": null,
  "flags": ["suppressed_by_comment"],
  "remediation": {"kind": "code_change", "target_version": null, "autofix": null}
}
```

### 4가지 상태 (`status`)

| 값 | 화면 표시 | 언제 |
|---|---|---|
| `code_issue` | 코드에서 문제 확인 | 이번 검사에서 발견됨 |
| `code_resolved` | 코드에서 해결 확인 | 지난번엔 있었는데 도구가 정상 실행된 이번 검사에는 없음 |
| `runtime_check_needed` | 운영 환경 확인 필요 | 비밀값을 코드에서 지웠음 → **키 폐기·재발급**이 필요 (깃 기록·배포본에 남아 있음) |
| `out_of_scope` | 현재 검사 범위 밖 | 지난번 문제인데 이번엔 도구 미설치·실패·lockfile 없음으로 확인 불가 |

도구가 못 돈 것을 '해결'로 착각하지 않도록, 실패는 언제나 `out_of_scope`(+ `change: unverifiable`)입니다.

### 꼼수 표시 (`flags`)

| 값 | 뜻 |
|---|---|
| `suppressed_by_comment` | `nosemgrep`, `gitleaks:allow` 주석으로 숨기려 함 (엔진은 무시하고 찾아냄) |
| `ignored_by_config` | `osv-scanner.toml`의 IgnoredVulns로 무시하려 함 |
| `file_removed` | '해결'됐지만 파일 자체가 사라짐 → 기능을 지운 건지 확인 필요 |
| `lockfile_removed` | lockfile을 지워서 의존성 검사가 안 됨 |
| `rotate_secret` | 비밀값: 코드에서 지우는 것만으로는 부족, 키 재발급 필요 |
| `likely_public_key` | 원래 공개해도 되는 키로 보임 (검색 전용 키, reCAPTCHA siteKey, publishable key 등) → 숨기지 않고 low로 낮춤 |
| `third_party_code` | 외부 라이브러리 파일(`plugins/`, `vendor/`, `jquery*.js` 등) 안의 코드 문제 → 숨기지 않고 low로 낮춤, 업데이트 안내 |

### 같은 문제 판단 (`fingerprint`)

| 도구 | 지문 재료 |
|---|---|
| osv | 생태계 + 패키지 + 취약점 대표 ID(CVE 우선) + lockfile 경로 (버전은 안 넣음) |
| semgrep | 규칙 ID + 파일 + 걸린 코드(공백 정리) — 위에 줄을 추가해도 같은 문제 |
| gitleaks | 규칙 ID + 파일 + 비밀값 해시(HMAC) — 값 자체는 저장 안 함 |

운영에서는 `SECURITY_ENGINE_FP_SALT` 환경 변수로 해시용 값을 바꾸세요.

## 3-1. LLM에 넘기는 꾸러미 (`build_llm_input`)

LLM 담당은 원본 결과 대신 이걸 쓰면 됩니다. 예시: [`schema/example_llm_input.json`](schema/example_llm_input.json)

```python
from security_engine import scan, build_llm_input, render_llm_text
result = scan("C:/code/my-site", previous=last_result)
payload = build_llm_input(result, max_items=30)   # dict
prompt_context = render_llm_text(payload)          # 프롬프트에 붙일 한국어 텍스트
```

- 순서: 열린 문제 → 키 재발급 필요 → 확인 불가 → 해결됨, 같은 상태 안에서는 위험도 높은 순
- 문제마다: `title`, `what`(설명), `where`(파일:줄), `code`(앞뒤 줄 + 문제 줄 `>` 표시), `fix_hint`
  (의존성은 `npm install lodash@4.17.21` 같은 명령까지), `flags`(꼼수·주의 설명 문장)
- `not_checked`: 이번에 검사 못 한 영역. LLM이 이걸 보고 "그 부분은 안전합니다"라고 말하지 않게 해야 합니다.
- 비밀값은 결과 단계에서 이미 가렸고, 여기서 비밀값 모양을 한 번 더 지웁니다.
- `max_items`로 개수를 잘라 토큰을 아낍니다 (`truncated: true`면 잘린 것).

## 4. 보안 처리

- Gitleaks가 찾은 비밀값은 runner에서 즉시 가립니다. 원본이 든 임시 리포트 파일은 바로 지웁니다.
  같은 값이 다른 도구의 증거 코드에 섞여도 전부 가립니다.
- 검사 폴더 밖 파일(심볼릭 링크로 바깥을 가리키는 등)은 읽지 않습니다.
- 저장소 쪽 예외 설정(`osv-scanner.toml`, `.gitleaks.toml`, `.gitleaksignore`, `nosemgrep`, `gitleaks:allow`)은
  무시하고 검사하고, 있었다는 사실은 `suppressions`·`flags`로 알려줍니다.
- 남의 사이트는 **소스 코드만** 분석합니다. 운영 중인 사이트에 요청을 보내지 않습니다.

## 5. Semgrep 규칙 (우리 규칙 + Semgrep 레지스트리 `p/default`)

2026-10-31 팀 결정: 해커톤 기간에는 **우리 규칙과 Semgrep 레지스트리 규칙(`p/default`)을 함께** 씁니다.
레지스트리(semgrep.dev)에 접속하지 못하면 자동으로 우리 규칙만으로 다시 돌리고 `coverage.semgrep.message`에 남깁니다.
결과에서 `rule_id`가 `vibe-coding/`로 시작하면 우리 규칙, 그 외(예: `javascript.lang.security...`)는 레지스트리 규칙입니다.

| 구성 | 라이선스 | 유료 서비스(SaaS)에서 |
|---|---|---|
| Semgrep CE 엔진 | LGPL-2.1 | 사용 가능 |
| Semgrep 레지스트리 규칙 `p/default` | Semgrep Rules License v1.0 | **사용 불가** (내부 사용만) → 상용화 때는 `--no-registry` 또는 `ScanOptions(semgrep_registry=())` |
| `rules/*.yml` 우리 규칙 | 우리 팀 소유 | 사용 가능 |

- `rules/vibe-coding.yml` (19개): NEXT_PUBLIC_/VITE_ 비밀값, 브라우저 코드의 Supabase service_role,
  로그인 확인 없는 Next.js API 라우트 DB 변경, 서명 확인 없는 Stripe 웹훅, eval·new Function,
  명령·SQL 인젝션, innerHTML·document.write·dangerouslySetInnerHTML, CORS *, 하드코딩 JWT 키, localStorage 토큰,
  Flask debug, shell=True, TLS 검증 끄기
- `rules/vibe-coding-config.yml` (2개): Supabase RLS 해제(SQL), Firebase 규칙 `if true`
- 규칙을 쓸 때 Semgrep 레지스트리 규칙을 복사하거나 고쳐 쓰지 않습니다 (그 규칙도 같은 라이선스라서).
  OWASP·CWE 설명, 공식 문서(Supabase·Firebase·Next.js) 같은 공개 지식을 바탕으로 직접 씁니다.

### 규칙 추가하는 법

1. `rules/vibe-coding.yml`에 규칙을 추가합니다. `message`는 사용자·LLM에게 그대로 가므로 한국어로 "무엇이 왜 위험하고 어떻게 고치는지"를 씁니다.
   `metadata`에 `engine_severity`(critical~low), `cwe`, `category`를 넣습니다.
2. 같은 이름의 테스트 파일(`vibe-coding.js`, `.tsx`, `.py` / 설정 규칙은 `vibe-coding-config.sql`, `.rules`)에
   걸려야 하는 줄 위에 `// ruleid: 규칙ID`, 걸리면 안 되는 줄 위에 `// ok: 규칙ID`를 답니다.
3. 확인: `semgrep --test --metrics=off security_engine/rules` → `All tests passed`
4. 전체 테스트: `python -m pytest tests/security -q`

규칙 테스트 파일은 일부러 위험한 코드를 담고 있지만 실행되는 코드가 아닙니다.

## 6. 파일 구조

| 파일 | 하는 일 |
|---|---|
| `engine.py` | `scan`, `scan_repo`, `compare_results`, `doctor` |
| `runners/osv.py` `semgrep.py` `gitleaks.py` | 도구 실행 + 결과를 공통 형식으로 |
| `normalize.py` | 경로·위험도·비밀값 가리기·코드 읽기 |
| `fingerprint.py` | 같은 문제 지문 |
| `compare.py` | 이전 결과와 비교 → change, 4가지 상태 |
| `suppression.py` | 저장소의 예외 설정 파일 찾기 |
| `git.py` | 고객 저장소 clone |
| `llm_input.py` | 결과 → LLM 입력 꾸러미 (`build_llm_input`, `render_llm_text`) |
| `cli.py` | 명령줄 |
| `models.py` | 상태 이름·옵션 등 상수 |
| `rules/*.yml` + 같은 이름 테스트 파일 | 우리 Semgrep 규칙과 규칙 테스트 |
| `schema/scan_result.schema.json` | 출력 규격 |

테스트: `python -m pytest tests/security -q` (스캐너가 없으면 해당 테스트는 건너뜀)
