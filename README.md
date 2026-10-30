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

## 백엔드 실행

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
