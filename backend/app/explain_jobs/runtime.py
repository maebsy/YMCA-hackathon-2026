import httpx

from app.explain_jobs.auth import SupabaseAuth
from app.explain_jobs.store import JobStore


async def prepare_auth(app, settings, stack):
    settings.validate_auth()
    client = await stack.enter_async_context(httpx.AsyncClient())
    app.state.job_auth = SupabaseAuth(settings, client)


async def prepare(app, engine, settings, stack):
    settings.validate_auth()
    app.state.job_store = JobStore(engine)
    await prepare_auth(app, settings, stack)
