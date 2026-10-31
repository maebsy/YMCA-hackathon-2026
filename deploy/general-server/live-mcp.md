# 실제 웹 검사 → 사용자 AI 수정 (#71)

기존 스캐너·GPU·백엔드·프론트를 변경하지 않고 같은 origin의 `/mcp/connect` 화면에서
`72hours:last-scan:v1`을 읽습니다. 사용자가 표시된 저장소·커밋·scan ID를 확인하고
전달 버튼을 누르면 수정 지시와 검증용 최소 메타데이터만 별도 MCP 프로세스로 보냅니다.
프론트 PR #66의 파일 다운로드와 함께 사용할 수 있습니다.

## 사용자 흐름

1. 웹에서 실제 검사를 실행하고 Red 통과 해석을 기다립니다.
2. 같은 브라우저에서 `/mcp/connect`를 열어 **이 검사로 AI 연결 만들기**를 누릅니다.
3. 생성된 **수정 요청 복사** 문장을 자기 AI 에이전트에게 전달합니다.
4. 에이전트는 전용 Streamable HTTP URL을 등록하고 `list_findings` → `get_fix_prompt`를 호출합니다.
5. 저장소/커밋과 현재 변경을 확인하고, 사용자 권한 범위에서 수정·기능 테스트·원래 탐지기 재검사를 합니다.

MCP는 에이전트의 로컬 편집기를 대신 실행하지 않습니다. 사용자 도구의 최초 연결 승인과
재접속이 필요할 수 있습니다. 다른 저장소·검사 커밋 불일치면 자동 수정하지 않습니다.

## 데이터 및 권한

- **브라우저 export**입니다. 서버 서명 원본으로 주장하지 않으며 `binding=browser_export_not_server_verified`를 반환합니다.
  새 신뢰 경계를 위해 기존 서버 API를 우회하거나 DB를 직접 조회하지 않습니다.
- 임의 코드·공격 시나리오·원본 오류는 저장하지 않습니다. 기존 Snapshot 검증/키 패턴 마스킹을 재사용합니다.
- 256비트 무작위 읽기 URL, 별도 폐기 비밀값. DB에는 두 값의 SHA-256만 저장합니다.
- 연결 소유자는 해당 결과를 읽을 수 있습니다. 링크를 공개하거나 Git에 저장하지 않습니다.
- 24시간 만료. 브라우저의 **이 연결 폐기**는 즉시 조회 권한과 저장된 결과를 제거합니다.
- 기본 256개 활성 연결 상한, 요청 최대 160 KiB, 결과 1~50건. 연결 전체 목록 API는 없습니다.
- 같은 origin의 JSON POST만 발급/폐기 허용. CORS 개방 없음. Origin/Host 보호, no-store/no-referrer/noindex 적용.
- Uvicorn access log 비활성화. 프록시에도 URL access log를 켜지 마세요. Cloudflare 등 전송 경로는 기존과 같습니다.
- SQLite는 MCP 전용 경로/600 권한. 서비스 Supabase/SQLite 스키마·GPU 키는 사용하지 않습니다.
- 결과는 발급 시점 스냅샷입니다. 뒤늦게 완료된 해석과 새 검사는 새 연결로 전달합니다.

## 분리 배포

선행 #70의 MCP 가상환경과 Caddy `/mcp/*` 라우팅을 사용합니다.

1. `integrations/mcp-handoff/`의 Python 코드와 `web/`을 `~/apps/72hours/mcp/live-<release>/`에 배치합니다.
2. `live_server.py --database <임시DB 절대경로> --public-origin https://<호스트> --port 8766`으로 후보를 확인합니다.
3. 검증 후 `live-current`를 해당 릴리스에 연결합니다. 전용 `private/`는 700 권한으로 생성합니다.
4. 현재 `72hours-mcp.service` 유닛을 백업하고 `72hours-mcp-live.service` 내용을 그 이름으로 설치합니다.
5. `systemctl --user daemon-reload; systemctl --user restart 72hours-mcp`로 **MCP만** 전환합니다.
6. `/mcp/health`의 `scope=user_selected_web_scan`, 실제 발급·MCP 조회·폐기를 확인합니다.
   기존 `/`·API health 및 백엔드/프론트/터널 PID도 확인합니다.

롤백은 이전 MCP 유닛 복원과 MCP만 재시작합니다. 전용 DB는 보존합니다. 기존 웹이나 GPU를 재시작하지 않습니다.
운영용 고정 도메인으로 바꿀 때는 PUBLIC_ORIGIN과 새 연결을 함께 갱신합니다.

## 검증

```bash
pip install -r integrations/mcp-handoff/requirements.txt
python -m unittest discover -s integrations/mcp-handoff/tests -v
```

두 검사 동시 조회 격리, 별도 폐기 권한, 만료, 프로세스 재생성 후 조회,
실제 MCP 초기화/도구 호출, 미존재 항목, CSRF·크기 제한, 원문/토큰 미저장,
형식/검사 fingerprint 불일치와 Red 미통과 차단을 검사합니다.
