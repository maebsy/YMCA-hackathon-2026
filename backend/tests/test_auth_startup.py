import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.explain_jobs.auth import SupabaseAuth
from app.explain_jobs.config import job_settings
from app.main import lifespan


def test_scan_auth_initializes_without_llm_jobs_and_closes_client(monkeypatch):
    monkeypatch.setattr(job_settings, "llm_jobs_enabled", False)
    monkeypatch.setattr(job_settings, "scan_require_auth", True)
    monkeypatch.setattr(job_settings, "supabase_url", "https://auth.example.invalid")
    monkeypatch.setattr(job_settings, "supabase_publishable_key", "test-public")

    async def reject_request(*args, **kwargs):
        raise AssertionError("Startup must not make HTTP requests")

    monkeypatch.setattr(httpx.AsyncClient, "send", reject_request)
    app = FastAPI(lifespan=lifespan)

    with TestClient(app):
        auth = app.state.job_auth
        assert isinstance(auth, SupabaseAuth)
        assert auth.url == "https://auth.example.invalid/auth/v1/user"
        assert not auth.client.is_closed

    assert auth.client.is_closed
