# security_engine 작업 규칙

루트 [AGENTS.md](../AGENTS.md)를 먼저 읽습니다. 담당: 장양환 `@surilog` (보조 유영민 `@maebsy`). 자세한 설명은 [README.md](README.md)에 있습니다.

## 지킬 것

- **엔진은 파이썬 표준 라이브러리만 씁니다.** 외부 패키지를 import하지 않습니다. 스캐너 3종(Opengrep·OSV-Scanner·Gitleaks)은 별도 실행 파일입니다.
- **출력 JSON이 계약입니다.** `schema/scan_result.schema.json`과 `models.py`를 바꾸면 `backend/app/llm/engine_adapter.py`와 `backend/app/routers/scans.py`가 깨질 수 있습니다. 필드 추가는 괜찮고, 이름 바꾸기·삭제는 백엔드 담당 승인 후 같은 PR에서 함께 고칩니다.
- 결과의 코드 검사기 도구 이름은 호환을 위해 `semgrep`으로 유지합니다(실제로는 Opengrep을 먼저 씀).
- **Semgrep Registry 규칙(`p/default`)은 내부 비교용입니다.** 라이선스상 서비스 결과에 쓰면 안 되므로 기본값을 켜지 않습니다.
- 사용자 코드는 읽기만 하고 실행하지 않습니다. 비밀값은 결과에 가린 형태로만 남깁니다.
- 규칙을 추가할 때는 README 5장 "규칙 추가하는 법"을 따르고, `rules/vibe-coding.*` 예제 파일에 걸리는 코드를 함께 넣어 테스트로 확인합니다.
- 현재 규칙 수: `rules/vibe-coding.yml` 19개, `rules/vibe-coding-config.yml` 2개(2026-10-31 기준). 발표·README에 숫자를 쓸 때는 이 파일에서 다시 셉니다.

## 실행과 테스트

```bash
python -m security_engine doctor                                  # 스캐너 설치 확인
python -m security_engine scan <코드 폴더> -o outputs/scan1.json   # 검사
python -m security_engine scan <코드 폴더> --previous outputs/scan1.json -o outputs/scan2.json   # 재검사

python -m pip install -r tests/security/requirements.txt
python -m pytest tests/security -q
```

스캐너가 없으면 일부 테스트는 건너뜁니다. CI(`security-engine.yml`)는 실제 스캐너로 돌고, 건너뛰면 실패로 봅니다.
