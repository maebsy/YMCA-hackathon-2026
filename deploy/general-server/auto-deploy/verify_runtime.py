"""Isolated integration check: run with a candidate backend venv from backend/.

Uses a temporary SQLite DB, no real scan, no real GPU, no production configuration.
"""
import asyncio
import os
from pathlib import Path
import sys
import tempfile


async def verify(directory):
    import httpx
    from app.main import app
    from app.routers import scans
    from deployment_entry import DeploymentGuard

    root = Path(directory)
    (root/"control-token").write_text("isolated-test-token")
    guard = DeploymentGuard(app, root)
    async with app.router.lifespan_context(app):
        assert await guard.busy() == 0
        pending = asyncio.get_running_loop().create_future()
        for tasks in (app.state.preview_jobs.tasks, app.state.verify_jobs.tasks, scans._tasks):
            tasks.add(pending)
        assert await guard.busy() == 3
        for tasks in (app.state.preview_jobs.tasks, app.state.verify_jobs.tasks, scans._tasks):
            tasks.remove(pending)
        pending.cancel()
        app.state.scan_store.create("a"*32, "https://github.com/OWASP/www-project-top-ten")
        assert await guard.busy() == 1
        app.state.scan_store.fail("a"*32, {"code":"TEST_ONLY"})
        assert await guard.busy() == 0
        # Compatibility of the rollback target that predates app.state.scan_engine.
        engine = app.state.scan_engine
        del app.state.scan_engine
        assert await guard.busy() == 0
        app.state.scan_engine = engine
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guard), base_url="http://test") as client:
            assert (await client.get("/api/_deployment/status")).status_code == 404
            (root/"drain").touch()
            response = await client.get("/api/_deployment/status", headers={"X-Deployment-Token":"isolated-test-token"})
            assert response.json() == {"busy":0,"draining":True}
            assert (await client.post("/api/scans", json={})).status_code == 503
            assert (await client.get("/api/health")).status_code == 200
        engine.dispose()
    print("PASS: actual application lifecycle, memory/durable jobs, legacy engine, private guard, drain and health")


if __name__ == "__main__":
    sys.path.insert(0, str(Path.cwd()))
    with tempfile.TemporaryDirectory(prefix="72hours-deploy-test-") as directory:
        os.environ.update(DATABASE_URL=f"sqlite:///{Path(directory).as_posix()}/test.db",
                          LLM_JOBS_ENABLED="false", SCAN_REQUIRE_AUTH="false",
                          LLM_BASE_URL="http://127.0.0.1:9/v1", LLM_API_KEY="unused", LLM_THREAT_INTEL="false")
        asyncio.run(verify(directory))
