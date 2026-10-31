# deploy 작업 규칙

루트 [AGENTS.md](../AGENTS.md)를 먼저 읽습니다. 담당: 유영민 `@maebsy` (보조 김건우 `@papawolf42`). 일반 서버 구성은 [general-server/README.md](general-server/README.md), 비동기 해석 worker는 [docs/async-llm.md](../docs/async-llm.md)에 있습니다.

## 지킬 것

- **에이전트가 실제 서버 상태를 바꾸는 명령을 혼자 실행하지 않습니다.** 설치 스크립트, `systemctl` 시작·중지, 터널 열기는 사람이 확인하고 실행합니다. 시연 중인 서버가 내려갈 수 있습니다.
- 비밀값은 `*.env.example`에 **이름만** 적습니다. 실제 값, 서버 주소·계정, SSH 키를 커밋하거나 PR 본문에 쓰지 않습니다.
- 공개 시연 주소의 접근 인증을 빼거나 우회하지 않습니다.
- 내려받는 실행 파일은 지금처럼 공식 체크섬을 고정해 확인합니다. 버전을 바꾸면 체크섬과 `docs/external-resources.md`를 같이 고칩니다.
- **서버는 기간이 지나면 데이터와 함께 지워집니다.** GPU 서버는 2026-11-02 19:00, 일반 서버는 2026-11-06 18:00에 종료됩니다. 남길 결과는 그 전에 백업합니다.

## 테스트

```bash
python -m pytest deploy/general-server/tests -q
```
