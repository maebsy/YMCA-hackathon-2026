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
- 컨테이너 안에서는 `.env`의 `DATABASE_URL`을 무시하고 로컬 DB를 씁니다. Supabase를 쓰려면 아래 "백엔드 실행"처럼 직접 띄우세요
- DB만 Docker로 쓰고 서버는 직접 띄워도 됩니다: `docker compose up db` 후 `.env`에 `DATABASE_URL=postgresql://app:app@localhost:5432/app`

문제가 생기면:

| 증상 | 해결 |
|---|---|
| `port is already allocated` | `.env`에서 `BACKEND_PORT`나 `POSTGRES_PORT`를 다른 번호로 |
| 컨테이너에서 LLM 서버에 연결 안 됨 | 컨테이너 안의 `localhost`는 컨테이너 자신입니다. `LLM_BASE_URL`에 `host.docker.internal`을 쓰세요 |
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

## 규칙

- 이슈·브랜치·커밋·PR 규칙: [CONTRIBUTING.md](CONTRIBUTING.md)
- 외부 자원 활용 내역: [docs/external-resources.md](docs/external-resources.md)
