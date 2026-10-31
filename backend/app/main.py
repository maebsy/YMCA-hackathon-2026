from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.db import engine, init_db
from app.explain_jobs.config import job_settings
from app.llm import create_explainer
from app.routers import items, llm, reports, scans, verify
from app.scan_store import ScanStore
from app.verify.jobs import VerifyJobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        if job_settings.llm_jobs_enabled:
            from app.explain_jobs.runtime import prepare
            await prepare(app, engine, job_settings, stack)
        else:
            init_db()
            if job_settings.scan_require_auth:  # 검사 API만 로그인 확인을 켠 경우
                from app.explain_jobs.runtime import prepare_auth
                await prepare_auth(app, job_settings, stack)
        app.state.scan_engine = engine
        # SQLite is a local demo; PostgreSQL scanners require an explicit migration.
        # Keep unrelated health/report endpoints available before that migration.
        app.state.scan_store = ScanStore(engine) if engine.dialect.name == "sqlite" else None
        # LLM 서버가 꺼져 있어도 API 서버는 뜹니다. 생성 작업은 별도 worker가 실행합니다.
        app.state.explainer = create_explainer()
        # LLM 연결과 위협 정보(KEV·EPSS) 연결을 함께 닫습니다
        stack.push_async_callback(app.state.explainer.aclose)
        if not job_settings.llm_jobs_enabled:
            from app.llm.preview_jobs import PreviewJobs
            from app.config import settings
            app.state.preview_jobs = PreviewJobs(running=settings.llm_preview_running, capacity=settings.llm_preview_capacity)
            stack.push_async_callback(app.state.preview_jobs.aclose)
        stack.push_async_callback(scans.drain_tasks)
        app.state.verify_jobs = VerifyJobs()
        stack.push_async_callback(app.state.verify_jobs.aclose)
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
api.include_router(reports.router)
api.include_router(scans.router)
api.include_router(verify.router)
app.include_router(api)
