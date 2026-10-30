from uuid import UUID
import os
import subprocess
import sys

import httpx
import pytest
from fastapi import HTTPException

from app.explain_jobs.auth import SupabaseAuth
from app.explain_jobs.config import JobSettings

OWNER = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.anyio
@pytest.mark.parametrize("status,body,expected", [
    (200, {"id": str(OWNER), "is_anonymous": False}, None),
    (401, {"message": "expired token"}, 401),
    (403, {}, 401),
    (500, {}, 503),
    (302, {}, 503),
    (200, {"id": str(OWNER), "is_anonymous": True}, 403),
    (200, {"id": "not-a-uuid"}, 503),
    (200, [], 503),
])
async def test_auth_verifies_with_configured_project(status, body, expected):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)
    config = JobSettings(_env_file=None, supabase_url="https://auth.example.invalid", supabase_publishable_key="test-public")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        auth = SupabaseAuth(config, client)
        if expected:
            with pytest.raises(HTTPException) as exc:
                await auth.verify("untrusted-token")
            assert exc.value.status_code == expected
        else:
            assert await auth.verify("untrusted-token") == OWNER
    assert str(calls[0].url) == "https://auth.example.invalid/auth/v1/user"
    assert calls[0].headers["Authorization"] == "Bearer untrusted-token"
    assert calls[0].headers["apikey"] == "test-public"


@pytest.mark.anyio
async def test_auth_outage_is_fail_closed_and_redacted():
    def handler(request):
        raise httpx.ConnectError("private provider message", request=request)
    config = JobSettings(_env_file=None, supabase_url="https://auth.example.invalid", supabase_publishable_key="test-public")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as exc:
            await SupabaseAuth(config, client).verify("forged-token")
    assert exc.value.status_code == 503
    assert "private" not in exc.value.detail


@pytest.mark.parametrize("url", ["", "http://auth.test", "https://name:password@auth.test", "https://auth.test/path", "https://auth.test?q=1"])
def test_auth_config_rejects_unsafe_endpoints(url):
    with pytest.raises(RuntimeError):
        JobSettings(_env_file=None, supabase_url=url, supabase_publishable_key="test-public").validate_auth()


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_feature_mode_preserves_route_boundaries_and_reports(enabled):
    script = """import os
import warnings
from app.main import app
warnings.filterwarnings('error', message='Duplicate Operation ID')
paths = app.openapi()['paths']
enabled = os.environ['LLM_JOBS_ENABLED'] == 'true'
assert ('/api/llm/explain' in paths) is not enabled
assert ('/api/items' in paths) is not enabled
assert ('/api/scans/{scan_id}/explanations' in paths) is enabled
assert '/api/llm/health' in paths
for name in ('plain', 'assess', 'incident-24h', 'privacy-72h'):
    assert 'post' in paths[f'/api/reports/{name}']
"""
    subprocess.run([sys.executable, "-c", script], check=True,
                   env={**os.environ, "LLM_JOBS_ENABLED": enabled})
