from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.db import engine, init_db
from app.routers import items


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="YMCA Hackathon 2026 API", lifespan=lifespan)

# 모든 API는 /api 아래에 둡니다. 프론트(Next.js)가 /api/* 를 이 서버로 프록시합니다.
api = APIRouter(prefix="/api")


@api.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": engine.dialect.name}


api.include_router(items.router)
app.include_router(api)
