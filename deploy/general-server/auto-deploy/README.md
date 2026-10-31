# main 자동배포

일반 서버의 systemd 사용자 타이머가 2분 간격으로 공개 GitHub `main`을 확인한다. PC·VPN·GitHub에서 서버로 들어오는 SSH 연결은 필요 없다. 새 main의 **정확한 SHA에 대한 push CI**가 모두 성공해야 배포한다. 여러 머지가 몰리면 가장 최신 main만 적용하며, 빌드 시간과 진행 중 작업 때문에 실제 반영은 2분보다 늦어질 수 있다.

## 배포 범위와 순서

1. 기존 서비스와 별도로 `~/apps/72hours/auto-releases/<SHA>`에 프론트·백엔드를 빌드한다. 빌드 환경에는 운영 DB·LLM 키를 전달하지 않는다.
2. 별도 SQLite DB, 더미 LLM 주소와 루프백 18080/13000 포트로 후보를 기동한다. API, HTML, 커밋 표식을 검사한다. 실제 GPU 작업·취약점 검사를 접수하지 않는다.
3. main/CI를 다시 확인하고 DB 관련 코드 변경은 운영자 검토까지 보류한다. SQL 마이그레이션은 실행하지 않는다.
4. 새 요청은 막지 않고 진행 중인 검사·LLM·검증 작업이 0이 되는 순간을 기다린다(한 회차 최대 8분). 그 순간에만 새 쓰기 요청을 잠깐 503으로 막고(확인 최대 20초) 교체한다. 계속 바쁘면 다음 회차로 미룬다.
5. 기존 SQLite를 백업하고 이전 링크를 기록한 뒤 프론트·백엔드를 같은 SHA로 교체한다. 해당 두 서비스만 재시작한다.
6. 로컬 및 설정된 공개 URL에서 버전을 확인한다. 실패하면 이전 링크와 서비스를 복구한다. DB는 새 데이터를 덮어쓰지 않도록 자동 복원하지 않는다.
7. **MCP**(`72hours-mcp`: 검사별 연결 `/mcp/h/*`, 서비스 MCP `/mcp/service/rpc`): 마지막으로 올린 MCP 커밋 이후 `integrations/mcp-handoff/`가 바뀌었을 때만 `~/apps/72hours/mcp/releases/<SHA>`에 복사한다. 후보 포트 18765에서 `/mcp/health`와 서비스 MCP 도구 목록을 실제 공개 주소의 Host로 확인한 뒤 `live-current`를 바꾸고 `72hours-mcp`만 재시작한다. 다시 확인해 실패하면 이전 버전으로 되돌린다. 작업 공간·연결 DB(`mcp/private`)는 그대로다. `requirements.txt`가 바뀌면 공용 가상환경을 운영자가 먼저 갱신해야 하므로 보류한다. 실패한 SHA는 `--retry` 전까지 다시 시도하지 않고, MCP 실패는 끝난 앱 교체를 되돌리지 않는다.
8. **배포 스크립트 자기 갱신**: 같은 커밋의 `deploy.py`·`deployment_entry.py`·`snapshot.py`가 서버 사본과 다르면 문법 확인 후 교체한다. 하나라도 문법이 틀리면 아무것도 바꾸지 않는다. `install.sh`로 직접 설치한 사본(`runtime-pinned`)은 main이 같은 내용이 될 때까지 되돌리지 않는다. `deployment_entry.py`는 다음 백엔드 재시작부터 적용된다. systemd 유닛 변경은 `install.sh`를 다시 실행해야 한다.

앱이 이미 최신이어도 MCP·배포 스크립트가 남아 있으면 다음 타이머에 그것만 이어서 맞춘다.

VPN·GPU·모델·프록시·터널의 설정과 프로세스는 건드리지 않는다. 짧은 앱·MCP 재시작이 있어 무중단 배포는 아니다. 기존 데모 API의 **완료된 메모리 전용 LLM·verify 결과는 재시작 때 사라질 수 있다**. 실행 중 작업이 있으면 교체하지 않는다. MCP 재시작 순간 진행 중이던 MCP 호출은 끊길 수 있지만, 같은 `request_id`로 다시 부르면 새로 접수하지 않고 이어 본다. 영구 저장/다중 인스턴스는 별도 서비스 개선 범위다.

## 최초 설치 (운영자)

전제: 기존 일반 서버 설치와 `current`, `frontend` 심볼릭 링크, Python 3.12+, git, uv, Node/npm, systemd 사용자 서비스가 있어야 한다. 운영 SQLite는 릴리스 밖의 절대 경로를 사용해야 한다. 한 uvicorn worker를 전제로 한다.

검토한 이 디렉터리의 파일을 서버 전용 디렉터리에 복사하고 실행한다. 컨트롤러는 별도 사본으로 설치되고, 이후에는 앱 교체가 성공한 같은 커밋으로 스스로 갱신한다(#151). 이 기능이 없는 예전 사본에서는 `install.sh`를 한 번 다시 실행해야 한다.

```bash
bash install.sh                           # 앱 재시작·타이머 활성화 없음
python3 ~/apps/72hours/auto-deploy/runtime/deploy.py --check
python3 ~/apps/72hours/auto-deploy/runtime/deploy.py --prepare-only
```

공개 경로도 검사하려면 `~/.config/72hours/auto-deploy.env`(권한 600)에 현재 HTTPS 주소를 넣는다. 변경되는 임시 터널 주소는 운영자가 함께 갱신해야 한다.

```text
DEPLOYMENT_PUBLIC_URL=https://<현재-공개-호스트>
```

최초에는 이전 앱에 drain 래퍼가 없다. 접수 중인 작업·GPU 요청이 없음을 직접 확인한 운영자만 아래 명령을 한 번 사용한다. 이때 오래된 메모리 결과는 유지되지 않는다. DB 관련 변경을 검토했다면 `--reviewed-schema-revision <정확한-40자리-SHA>`를 한 번 추가할 수 있다. 이 옵션은 DB 마이그레이션을 실행하거나 검증을 대신하지 않는다.

```bash
python3 ~/apps/72hours/auto-deploy/runtime/deploy.py --bootstrap --public-url https://<현재-공개-호스트>
# status.json의 deployed 및 공개 페이지 확인 후:
systemctl --user enable --now 72hours-auto-deploy.timer
```

## 멈춤·재개·상태 (테스트·시연 중)

```bash
D=~/apps/72hours/auto-deploy/runtime
python3 $D/deploy.py --pause "시연 중"   # 자동 배포 멈춤. 기다리던 새 작업 차단도 바로 풂
python3 $D/deploy.py --status            # 멈춤·대기 경과·진행 중 작업 수·적용 버전 (읽기만)
python3 $D/deploy.py --resume            # 다시 켜기. 다음 타이머(최대 2분)에 이어서 진행
python3 $D/deploy.py --now               # 운영자 전용: 작업이 빌 때까지 기다리지 않고 바로 교체 (진행 중 해석은 끊김)
```

- 멈춘 동안 타이머는 계속 돌지만 main 조회·빌드·교체를 하지 않고 `status.json`에 `paused`만 남긴다.
- 교체를 기다리는 도중에 멈추면 2초 안에 대기를 그만둔다. 이미 링크를 바꾸는 중(`transaction.json`)이면 그 교체를 끝낸 뒤 풀린다.
- 타이머 자체를 끄는 `systemctl --user disable --now 72hours-auto-deploy.timer`보다 위 명령을 먼저 쓴다(설정은 그대로, 다시 켜기 쉬움).

### 교체 대기(drain) 동작 (#151)
- 예전에는 교체 전에 새 작업을 막고 진행 중 작업이 끝나기를 기다렸다(최대 20분). 해석이 계속 들어오는 동안에는 그만큼 사이트가 막혔다(2026-11-01 운영에서 실제 발생).
- 이제는 **새 작업을 막지 않고** 진행 중 작업이 0이 되는 순간을 기다린다. 그 순간에만 새 쓰기 요청을 막고, 막은 직후 들어온 요청이 끝나기를 최대 20초 기다린 뒤 교체한다. 그 안에 0이 안 되면 바로 풀고 다시 기다린다.
- 한 회차에서 8분 안에 빈 순간이 없으면 다음 회차로 미룬다. 실행 사이에 차단을 남기지 않는다.
- 계속 바빠서 꼭 지금 바꿔야 하면 운영자가 `--now`로 바로 교체한다(진행 중 해석은 끊김). 시연 중에는 `--pause`로 멈춰 둔다.
- 백엔드 가드는 10분이 지난 대기 표시를 무시한다. 배포가 교체 도중 죽어도 이용자가 계속 막히지 않는다.

## 상태 확인·중지·재시도

```bash
systemctl --user list-timers 72hours-auto-deploy.timer
cat ~/apps/72hours/auto-deploy/status.json
journalctl --user -u 72hours-auto-deploy.service -n 20
systemctl --user disable --now 72hours-auto-deploy.timer  # 앞으로의 배포 중지; 앱은 계속 실행
```

상태는 `eligible`(검사만 통과), `prepared`(빌드 완료), `deferred`(CI/작업/스키마 대기), `deployed`(반영 완료, MCP·배포 스크립트를 함께 맞췄으면 `mcp`·`runtime` 표시), `failed`다. MCP 실패 사유는 `mcp-failed.json`과 `--status`의 `mcp_failed`에 남는다. 같은 실패 SHA는 자동 재시도하지 않는다. 원인은 서버 전용 `auto-deploy/logs/<SHA>.log`에서 확인하고 수정한 뒤 `deploy.py --retry --public-url ...`로 다시 실행한다. 로그·백업·토큰은 외부에 게시하지 않는다. GitHub 비인증 API 한도/네트워크 오류는 보류 후 재확인한다.

중단된 교체는 `transaction.json`을 보고 다음 실행에서 이전 버전으로 복구한다. 복구도 실패하면 파일과 drain을 보존하므로 운영자가 서비스 로그를 확인해야 한다. 단순히 파일을 지워 성공으로 처리하지 않는다. 이전 릴리스/백업은 자동 삭제하지 않으므로 디스크를 관찰하고, 실행 중·복구 대상 경로는 보존하여 수동 정리한다.

공개 `/deployment.json`은 프론트 SHA, `/api/health`의 `X-72hours-Release`는 백엔드 SHA다. `/api/_deployment/status`는 서버 전용 무작위 토큰 없이는 404이며, 인증돼도 작업 수만 반환한다. 이 기동 검사는 보안 엔진 정확도나 전체 사용자 흐름 검증을 대체하지 않는다.

## 검증

```bash
python3 -m unittest discover -s deploy/general-server/auto-deploy -p 'test_*.py' -v
bash -n deploy/general-server/auto-deploy/install.sh
cd backend
python ../deploy/general-server/auto-deploy/verify_runtime.py  # 백엔드 의존성이 있는 가상환경
```

CI 정확한 SHA 판별, 실패/재실행, 두 링크 교체와 복구, 복구 실패 시 저널 보존, DB 변경 차단, 작업 중 보류, 중복 실행 잠금, 비밀값 없는 빌드 환경, 제어 API 인증과 쓰기 차단을 검사한다. 통합 검사는 실제 앱 lifespan에서 메모리 작업 3종·DB 작업 집계·구버전 DB 호환과 차단/조회 동작을 격리 DB로 확인한다. 설치 후 실제 후보 기동·공개 SHA·타이머 무변경 실행을 별도로 확인한다.
