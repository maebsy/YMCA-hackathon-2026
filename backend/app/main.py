from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.db import engine, init_db
from app.explain_jobs.config import job_settings
from app.llm import create_explainer
from app.routers import items, llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        if job_settings.llm_jobs_enabled:
            from app.explain_jobs.runtime import prepare
            await prepare(app, engine, job_settings, stack)
        else:
            init_db()
        # LLM 서버가 꺼져 있어도 API 서버는 뜹니다. 생성 작업은 별도 worker가 실행합니다.
        app.state.explainer = create_explainer()
        stack.push_async_callback(app.state.explainer.client.aclose)
        yield


app = FastAPI(title="YMCA Hackathon 2026 API", lifespan=lifespan)

# 모든 API는 /api 아래에 둡니다. 프론트(Next.js)가 /api/* 를 이 서버로 프록시합니다.
api = APIRouter(prefix="/api")


@api.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": engine.dialect.name}


if job_settings.llm_jobs_enabled:
    from app.explain_jobs.api import router as jobs_router
    api.include_router(jobs_router)
    api.add_api_route("/llm/health", llm.health, methods=["GET"], tags=["llm"])
else:
    # Existing evaluation/development API stays unchanged when the feature is disabled.
    api.include_router(items.router)
    api.include_router(llm.router)
app.include_router(api)
