# YMCA-hackathon-2026
코디세이 AI 해커톤 2026 | 이노베이션아카데미 (2026.10.30 ~ 11.02)

## 개발 시작하기

```bash
git clone https://github.com/maebsy/YMCA-hackathon-2026.git
cd YMCA-hackathon-2026
bash scripts/setup-dev.sh
cp .env.example .env
```

## 구조

| 폴더 | 내용 |
|---|---|
| `backend/` | FastAPI API 서버. DB는 SQLModel, 모든 API는 `/api` 아래 |
| `frontend/` | Next.js (예정) |

DB는 `.env`의 `DATABASE_URL`로 정합니다. 비워 두면 로컬 SQLite 파일(`backend/app.db`)을, Supabase 연결 문자열을 넣으면 팀 공용 DB를 씁니다. 테이블은 `backend/app/models.py`에 정의하면 서버가 켜질 때 자동으로 만들어집니다.

## Docker로 실행 (권장)

[Docker Desktop](https://docs.docker.com/desktop/)만 있으면 Python·PostgreSQL을 따로 설치하지 않아도 됩니다.

```bash
cp .env.example .env              # 처음 한 번
docker compose up --build --watch
```

- API 서버와 로컬 PostgreSQL이 같이 뜹니다. http://localhost:8000/api/health 에서 `"db":"postgresql"`이 나오면 성공
- `backend/app` 코드를 저장하면 컨테이너에 바로 반영되고, `requirements.txt`를 바꾸면 이미지를 다시 만듭니다
- 끄기는 `Ctrl+C` 또는 `docker compose down`. DB 데이터는 남고, 지우려면 `docker compose down --volumes`
- `.env`의 `DATABASE_URL`이 비어 있으면 로컬 DB를, Supabase 주소가 있으면 그 DB를 씁니다
- DB만 Docker로 쓰고 서버는 직접 띄워도 됩니다: `docker compose up db` 후 `.env`에 `DATABASE_URL=postgresql://app:app@localhost:5432/app`. 이 값은 컨테이너 안에서 통하지 않으니 전체를 Docker로 띄울 때는 다시 비우세요

문제가 생기면:

| 증상 | 해결 |
|---|---|
| `port is already allocated` | `.env`에서 `BACKEND_PORT`나 `POSTGRES_PORT`를 다른 번호로 |
| 컨테이너에서 LLM 서버에 연결 안 됨 | 내 PC에 8001 SSH 터널이 열려 있는지 확인하세요(아래 "LLM 서버 연결"). 다른 주소를 쓰려면 `.env`의 `DOCKER_LLM_BASE_URL` |
| 나만 설정을 바꾸고 싶음 | `compose.override.yaml`을 만들면 자동으로 합쳐지고 커밋되지 않습니다 |

## 백엔드 실행 (Docker 없이)

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # macOS·Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- http://localhost:8000/api/health 에서 `{"status":"ok","db":"sqlite"}`가 나오면 성공 (Supabase면 `"postgresql"`)
- http://localhost:8000/docs 에서 API를 직접 눌러 볼 수 있습니다
- `Item`과 `/api/items`는 연결 확인용 예시입니다. 실제 테이블을 만들면 지우세요.

## LLM 서버 연결 (vLLM, 8001 포트)

GPU 서버의 vLLM은 **8001 포트**로 띄웁니다. 백엔드(8000)와 겹치지 않게 서버와 내 PC 모두 같은 번호를 씁니다.

```bash
# GPU 서버: 처음 한 번 setup-gpu.sh, 그다음 serve.sh. 127.0.0.1에만 열고 API 키를 요구합니다
bash scripts/llm/setup-gpu.sh
tmux new -d -s vllm 'bash scripts/llm/serve.sh'

# 내 PC: 서버의 8001을 내 PC의 8001로 가져옵니다 (SSH 터널 허용 여부는 운영진 확인 필요)
ssh -N -L 8001:127.0.0.1:8001 <GPU 서버>
```

- 백엔드를 직접 띄우면 `.env`의 `LLM_BASE_URL=http://localhost:8001/v1`을 그대로 씁니다
- Docker로 띄우면 compose가 `http://host.docker.internal:8001/v1`(내 PC의 8001)로 바꿔 연결합니다
- vLLM은 OpenAI 호환 API라, 개발 중에는 OpenAI·Ollama 주소로 바꿔도 코드는 그대로입니다
- 모델(Qwen3.8-27B), Red–Blue 흐름, API, 테스트 방법: [docs/llm.md](docs/llm.md)

## 리포트·신고서

- 비전공자용 점검 리포트(완료 리포트 포함)와 KISA 침해사고 신고(24시간)·개인정보 유출 신고(72시간) 초안: [docs/reports.md](docs/reports.md)
- `POST /api/reports/plain` · `/assess` · `/incident-24h` · `/privacy-72h`, `?format=json|markdown|html`

## 규칙

- 이슈·브랜치·커밋·PR 규칙: [CONTRIBUTING.md](CONTRIBUTING.md)
- 외부 자원 활용 내역: [docs/external-resources.md](docs/external-resources.md)
