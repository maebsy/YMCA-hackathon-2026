from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.db import engine, init_db
from app.llm import create_explainer
from app.routers import items, llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # LLM 서버가 꺼져 있어도 API 서버는 뜹니다. 연결은 요청할 때 확인합니다 (/api/llm/health)
    app.state.explainer = create_explainer()
    yield
    await app.state.explainer.client.aclose()


app = FastAPI(title="YMCA Hackathon 2026 API", lifespan=lifespan)

# 모든 API는 /api 아래에 둡니다. 프론트(Next.js)가 /api/* 를 이 서버로 프록시합니다.
api = APIRouter(prefix="/api")


@api.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": engine.dialect.name}


api.include_router(items.router)
api.include_router(llm.router)
app.include_router(api)
