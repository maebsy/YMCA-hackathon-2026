# 실제 서비스 반복 검증

## 엔진의 설계 적합성: 성공 응답과 분리해 검사

`/validation/quality.html`은 배포된 엔진 자체를 정답이 있는 합성 사례로 검사한 비교표입니다. 각 행에 기대 결과, 실제 결과, 설계 근거를 나란히 제공합니다. 공개 저장소에 알려지지 않은 취약점이 더 있을 수 있으므로 서비스 실행 성공만으로 탐지 정확도를 계산하지 않습니다.

- 배포본 `security_engine/rules`의 `ruleid`/`ok` 사례를 실제 Opengrep으로 검사하고 파일·행·규칙별 TP/FN/TN/FP를 기록합니다. 팀 규칙 회귀 사례이며 독립 실세계 평가 데이터셋은 아닙니다.
- 별도로 만든 위험 SQL/매개변수 SQL, 합성 비밀키, `.env`·공개 백업 파일, 취약/수정 lodash 잠금 파일을 실제 검사합니다. 합성 소스는 실행하지 않습니다.
- OSV 기대값은 GHSA-35jh-r3h4-6jhm(CVE-2021-23337)의 lodash 4.17.21 수정 경계를 기준으로 합니다. 다른 신규 CVE가 없다고 가정하지 않습니다.
- 정규화의 분류·위험도·CWE·중복·집계, 원본 fingerprint→LLM 입력→패키지 covers→리포트 항목 보존을 확인합니다.
- SQL 수정, 줄 이동, 비밀키 삭제, 도구 미실행에 따른 재검사 상태 전이를 실제 비교합니다. 삭제한 키가 완전 해결로 표시되면 실패입니다.
- 이전 검사 없이 Git 이력에만 남은 키를 찾는지 확인해 설계 문구와 현재 구현 범위의 차이도 표시합니다. 관련 이슈 #87.

검증은 일반 서버에서 현재 배포본과 동일한 venv/스캐너로 별도 프로세스를 실행합니다. 서비스 DB와 사용자 저장소를 수정하지 않습니다. API 키를 읽거나 GPU LLM을 새로 호출하지 않습니다. `engine-quality.json`에 배포 커밋·규칙 SHA-256·스캐너 버전·정답 사례·변환 추적·리포트를 기록합니다. 이 검증의 리포트는 합성 사례이며 실제 사용자 사고 리포트가 아닙니다.

`campaign.py --server-ssh`는 매 회차 이 검증도 자동 실행합니다(별도 최대 5분). 공개 실행 폴더에 `quality.html`/`engine-quality.json`을 포함해 과거 실행의 비교 결과도 고정해서 볼 수 있습니다. 로컬 개발·Linux 재현은 `engine_quality.py --source <배포 소스> --output <결과 JSON>`입니다. 검사기 실행 파일 환경 변수는 엔진 README를 따릅니다.

## 지속 운영과 팀 공유

이 작업은 Codex의 현재 대화에 연결된 **30분 간격 반복 작업**으로 운영합니다. 운영자는 PC와 Codex 앱을 켜 두고, 서버 진단·게시가 필요하면 VPN을 유지해야 합니다. 반복 작업은 직접 결과를 비교하고 검증 도구를 보강합니다. 같은 실패로 중복 이슈를 만들지 않고, 새 실패·원인 확정·해결 확인·실행 차단처럼 필요한 변화만 알립니다. 예약은 OS 서비스/cron이 아니라 Codex에서 관리합니다.

- `/validation/`: 마지막 게시 실행, 실패 단계·작업 ID·확인된 원인·다음 조치.
- `/validation/history.html`: 최근 100개 게시 실행 및 동일 증상의 반복 횟수. 재게시한 동일 실행은 중복 집계하지 않습니다.
- `/validation/runs/<게시ID>/index.html`: 고정된 실행별 상세 화면. 해당 폴더의 `results.json`, `failures.json`, `handoff.md`를 개발자·AI 에이전트가 활용할 수 있습니다.
- `handoff.md`: 재현 요청, 실제 확인된 커밋(실패 전에 확인 못했으면 미확인), job ID, 진단 근거, 다음 수정 위치, 관련 이슈를 모은 인계문서입니다.

관리형 실행은 프로젝트 루트에서 다음 명령을 사용합니다. 통상적으로는 Codex 반복 작업이 직접 실행합니다.

```powershell
outputs/validation-runtime/.venv/Scripts/python.exe scripts/service-validation/campaign.py --base-url https://YOUR-SERVICE-ORIGIN --archive outputs/validation-history --server-ssh hk-server --gpu-ssh hk-gpu --discover --publish
```

회차마다 공개 저장소 최대 4개, LLM 2묶음/저장소, 실행 20분 상한입니다. LLM 표본과 공개 웹 소스 후보를 순환하고, 캠페인 프로세스 잠금으로 중복 실행을 막습니다. 본체 검사 실패 시에도 결과를 보관·게시합니다. 검색 실패는 `campaign.discovery`에 남기고 기존 후보만 검사합니다. 공개 저장소의 기본 브랜치가 바뀔 수 있으므로 실제 검사 결과의 커밋을 기준으로 비교하세요. GPU의 다른 작업이 계속 바쁘면 Codex가 새 검사 접수를 미룹니다.

로그 진단은 일반 서버의 `server_diagnose.py`가 요청한 **job ID가 일치하는 예외**만 대조합니다. #83은 `_package_finding`, `FindingInput.what`, `string_too_long`, 2000자 제한 표식까지 일치할 때만 확정합니다. 원문 로그·코드·입력값을 내려받아 공개하지 않습니다. SSH 실패, 로그 만료, 알 수 없는 예외는 원인 미확정으로 기록합니다. 단순히 비슷한 API 오류라는 이유로 기존 원인에 연결하지 않습니다. 서버를 수정하거나 장애가 재등장하지 않았다는 이유만으로 해결됐다고 자동 표시하지 않습니다.

서비스 코드를 import하거나 수정하지 않고 공개 웹/API로 검사합니다. 실제 엔진 결과, GPU Blue·Red 응답, 리포트 입력/출력, 재검사, 검사별 MCP 전달을 연결하고 `public/index.html`에 표시합니다. Playwright는 새 브라우저에서 주소 입력 → 검사 클릭 → 실제 리포트 표시까지 확인합니다. 영상은 녹화하지 않습니다.

## Windows 한 번 실행

Python 3.11+와 인터넷 연결이 필요합니다. 저장소 루트의 PowerShell에서:

```powershell
./scripts/service-validation/run.ps1 -BaseUrl https://YOUR-SERVICE-ORIGIN
```

첫 실행은 독립 venv와 Chromium을 `outputs/validation-runtime`에 설치합니다. 기본은 공개 저장소 3개, 저장소당 실제 Red/Blue 1묶음, 1회 실행입니다. 엔진 결과는 전체, GPU 해석은 표본이며 미분석 수를 명시합니다. 실제 검사와 LLM 호출로 서버 자원을 사용합니다. 로그인 정책이 적용된 환경은 운영자가 발급한 API 토큰을 `SERVICE_VALIDATION_API_TOKEN` 환경변수로 설정하세요. 브라우저는 독립 무로그인 사용자의 동작을 검사하므로 인증 화면이 나타나면 실패로 기록합니다.

```powershell
# 공개 웹 소스 후보를 GitHub에서 1개 추가하고 4개 저장소를 2회 순차 검증
./scripts/service-validation/run.ps1 -BaseUrl https://YOUR-SERVICE-ORIGIN -Discover 1 -MaxRepos 4 -Repeat 2

# VPN과 운영자 SSH 설정이 있는 PC에서만: 꺼진 기존 unit start, GPU 상태 수집, 공개 화면 갱신
./scripts/service-validation/run.ps1 -BaseUrl https://YOUR-SERVICE-ORIGIN -ServerSsh hk-server -GpuSsh hk-gpu -EnsureServices -PublishTo hk-server
```

일반 팀원은 공개 주소만 있으면 첫 명령을 실행할 수 있습니다. SSH/VPN은 선택적 운영 조회와 서버 배포에만 필요합니다. 다른 사람에게 운영자 키를 전달하지 않습니다. 서버 시작 옵션은 기존 unit에 `start`만 호출하며 활성 프로세스와 터널은 재시작하지 않습니다. GPU vLLM 설정도 변경하지 않습니다.

## 범위와 결과 읽기

- `통과`: 해당 실행에서 실제 응답의 식별자·계약·내용 연결을 확인했습니다.
- `검토 필요`: 분석 상한, 엔진 검사 대상 없음, Red 수동 검토, 추가 CVE 근거 확인 등입니다.
- `실패`: 엔진 오류, 모델 실패, 다른 저장소 리포트, 미해결 상태의 완료 표시, UI 실패 등입니다.
- `미실행`: 근거가 없는 단계를 성공으로 취급하지 않습니다. 로그인·결제·실제 공격 재현·소스 자동 수정은 실행하지 않습니다.
- Blue는 최종 설명/수정 제안, Red는 실제 응답의 라운드/시간/판정입니다. API가 제공하지 않는 내부 실시간 로그를 만들어 표시하지 않습니다.
- 모델명·토큰·지연은 실제 API 응답입니다. SSH 사용 시 NVIDIA 사용률도 수집하지만 같은 시간의 다른 GPU 작업과 분리된 측정은 아닙니다.
- 신고 초안은 명시적 가상 사고 입력입니다. 외부 기관에 제출하지 않습니다.
- 재검사는 같은 공개 기본 브랜치를 다시 검사합니다. 코드 수정 후 해결을 증명하는 테스트가 아닙니다.
- MCP는 전체 서비스 initialize/tools 목록과 실제 검사별 결과 전달·프롬프트 수신·연결 폐기를 확인합니다. 모든 서비스 MCP 도구나 모든 AI 제품의 호환성 검증은 아닙니다.
- 리포트 대상/검사 ID/커밋/탐지 범위/LLM 설명/완료 주장 등을 검사합니다. 취약점 진위와 수정 코드의 의미적 정확도는 전문가 리뷰가 필요합니다.
- UI 기본 대상은 작은 HTML 저장소 Spoon-Knife입니다. 여러 취약점 저장소는 API로 검사합니다. UI의 전체 버튼·모든 저장소 조합을 확인했다고 해석하지 마세요.

오류가 있으면 종료 코드 1, 통과 또는 검토 필요면 0입니다. CI에서 완전 통과가 필요하면 `results.json.status == "passed"`를 별도로 요구하세요. 범위 밖 기능을 표시하므로 기본 실행은 최소 `review_required`입니다.

## 상세 실행·재개

API 검사만은 외부 Python 의존성이 없습니다. 브라우저 검사에만 `requirements.txt`가 필요합니다.

```powershell
python scripts/service-validation/runner.py --base-url https://YOUR-SERVICE-ORIGIN --output outputs/my-validation --repo https://github.com/OWASP/NodeGoat --llm-per-repo 2 --rescan --mcp --incident-drafts
python -m unittest discover -s scripts/service-validation -p test_validation.py -v
```

`runner.py --help`로 전체 옵션을 확인하세요. 최대 저장소 20개, 반복 100회, LLM 5묶음/저장소, 기본 전체 시간 상한 1시간입니다. 기본 반복 간격은 60초입니다. 무한 루프·백그라운드 예약은 등록하지 않습니다.

중단한 실행은 **동일 인자와 동일 출력 폴더**에 `--resume`을 추가합니다. job ID가 있으면 기존 작업만 조회합니다. POST 직후 연결이 끊어져 접수 여부가 모호하면 중복 접수를 하지 않고 실패합니다. 운영자가 서버 작업을 확인한 뒤 새 실행 여부를 결정해야 합니다. 이미 접수된 작업은 클라이언트 종료 뒤에도 서버에서 계속될 수 있습니다. 실패한 서버 작업은 재개해도 동일한 실패를 확인합니다.

검색은 공개·비보관·비포크·10MB 미만 후보의 루트 웹 소스 표식/Pages 설정을 확인합니다. 한 검색에서 최대 10개이며 적합 후보가 적으면 실제 수집 수만 검사합니다. 공개 배포 사이트에 공격을 보내거나 저장소 앱을 설치·실행하지 않습니다. GitHub 제한 시 운영자 발급 토큰을 `SERVICE_VALIDATION_GITHUB_TOKEN`으로 설정하거나 `--repos-file`에 `[{"url":"https://github.com/owner/repo"}]` 목록을 지정하세요. 재현성이 필요하면 검색 대신 고정 목록을 사용하세요. 각 실제 검사 커밋은 결과에 기록됩니다.

## 읽기 전용 검증 화면 배포 (운영자 1회)

기존 관리형 Caddy 2.11+와 `72hours-*` user units를 사용하는 일반 서버용입니다. 서버에 Python 3.11+가 필요합니다. 먼저 해당 서버의 기존 배포 경로와 포트 8767 충돌 여부를 확인하세요.

```powershell
ssh hk-server 'mkdir -p apps/72hours/validation/code'
scp scripts/service-validation/serve.py scripts/service-validation/history.html scripts/service-validation/quality.html scripts/service-validation/engine_quality.py scripts/service-validation/evidence.py scripts/service-validation/diagnostics.py scripts/service-validation/server_diagnose.py scripts/service-validation/install_server.py scripts/service-validation/enable_route.py hk-server:apps/72hours/validation/code/
python scripts/service-validation/publish.py --ssh hk-server --output outputs/my-validation
ssh hk-server 'python3 apps/72hours/validation/code/install_server.py && python3 apps/72hours/validation/code/enable_route.py'
```

외부 주소는 `https://YOUR-SERVICE-ORIGIN/validation/`입니다. 최초 설치 후에는 `publish.py` 또는 `run.ps1 -PublishTo`로 결과만 갱신합니다. 공개 화면은 마지막 게시한 실행의 스냅샷입니다. 로컬 실행 중 진행률은 로컬 산출물에서 확인하고, 서버가 같은 출력 경로로 실행할 때만 실시간 갱신됩니다. 게시 과정은 public 파일만 새 release에 업로드한 뒤 current 심볼릭 링크를 원자적으로 바꿉니다. 이전 release는 롤백을 위해 남깁니다.

라우팅 추가는 잠금·사전 검증·백업 후 Caddy USR1 reload로 수행합니다. 웹/API/MCP 헬스와 기존 서비스 PID가 유지되는지 확인하며 실패하면 원래 Caddy 설정으로 복원합니다. 터널을 재시작하지 않습니다. 경로 형식이 예상과 다르면 자동 변경을 중단합니다. 검증 서버는 loopback에만 바인딩하며 GET 파일 조회만 제공합니다. 서버 코드 변경 시 검증 전용 unit만 재시작하세요.

`public/`에는 검사 근거·가림 처리한 수정 제안·리포트·기본 공개 저장소의 UI 캡처만 기록합니다. 공개 저장소라도 탐지 정보는 민감할 수 있으므로 비공개 저장소나 민감한 데이터를 이 공개 검증에 사용하지 마세요. 비밀값 가림은 알려진 패턴 기반이며 임의의 모든 비밀을 증명해서 제거하는 도구는 아닙니다. `private/state.json`은 재개용 작업 ID/설정이며 절대 게시하지 않습니다. 결과별 MCP URL·폐기 토큰은 메모리에서만 사용 후 폐기합니다.

로컬 조회: `python scripts/service-validation/serve.py --public C:/ABSOLUTE/OUTPUT/public` 후 `http://127.0.0.1:8767/validation/`.
