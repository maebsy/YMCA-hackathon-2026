"""Private deployment control around the unchanged application (one uvicorn worker)."""
import asyncio
import hmac
import json
import os
from pathlib import Path
import time

# deploy.py 의 DRAIN_MAX_SECONDS(20분)보다 길게. 타이머가 대기 도중 죽어도 이용자를 영원히 막지 않습니다
STALE_DRAIN_SECONDS = 25 * 60


class DeploymentGuard:
    def __init__(self, application, root):
        self.application = application
        self.root = Path(root)
        self.active = 0

    def draining(self):
        marker = self.root / "drain"
        try:
            since = json.loads(marker.read_text()).get("since")
        except FileNotFoundError:
            return False
        except (OSError, ValueError, AttributeError):
            return True  # 예전 형식(빈 파일)은 그대로 대기로 봅니다
        return not (since and time.time() - float(since) > STALE_DRAIN_SECONDS)

    async def reply(self, send, status, value):
        body = json.dumps(value).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})

    async def busy(self):
        from sqlalchemy import inspect, text
        from app.routers import scans
        state = self.application.state
        memory = sum(sum(not task.done() for task in getattr(getattr(state, name, None), "tasks", ()))
                     for name in ("preview_jobs", "verify_jobs"))
        memory += sum(not task.done() for task in scans._tasks)
        engine = getattr(state, "scan_engine", None)
        if engine is None:
            # The earlier demo predates scan_engine but uses the same app.db engine.
            from app.db import engine
        if engine is None:
            raise RuntimeError("Job storage unavailable")

        def count():
            tables = set(inspect(engine).get_table_names())
            total = 0
            with engine.connect() as conn:
                for table in ("scan_job", "llm_job"):
                    if table in tables:
                        total += conn.scalar(text(f"SELECT count(*) FROM {table} WHERE status IN ('queued','running')"))
                if getattr(state, "job_store", None) is not None:
                    total += conn.scalar(text("SELECT count(*) FROM finding f JOIN scan s ON s.id=f.scan_id "
                                              "WHERE s.status='explaining' AND f.explain_status IN ('none','pending')"))
            return total
        return self.active + memory + await asyncio.to_thread(count)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.application(scope, receive, send)
        if scope["path"].startswith("/api/_deployment"):
            expected = (self.root / "control-token").read_text().strip()
            supplied = dict(scope.get("headers", [])).get(b"x-deployment-token", b"").decode("ascii", errors="ignore")
            if not expected or not hmac.compare_digest(expected, supplied):
                return await self.reply(send, 404, {"detail": "Not found"})
            if scope["path"] != "/api/_deployment/status" or scope["method"] != "GET":
                return await self.reply(send, 404, {"detail": "Not found"})
            try:
                count = await self.busy()
                return await self.reply(send, 200, {"busy": count, "draining": self.draining()})
            except Exception:
                return await self.reply(send, 503, {"detail": "Cannot verify idle state"})
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and self.draining():
            return await self.reply(send, 503, {"detail": {"code": "DEPLOYMENT_DRAINING",
                "message": "새 버전을 적용 중입니다. 잠시 후 다시 시도해 주세요."}})
        self.active += 1
        async def versioned_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []),
                    (b"x-72hours-release", os.environ.get("DEPLOYMENT_REVISION", "unknown").encode())]}
            await send(message)
        try:
            await self.application(scope, receive, versioned_send)
        finally:
            self.active -= 1


def create_app():
    from app.main import app
    marker = Path.cwd().parent / "deployment.json"
    if marker.exists():
        os.environ["DEPLOYMENT_REVISION"] = json.loads(marker.read_text())["revision"]
    return DeploymentGuard(app, os.environ.get("DEPLOYMENT_CONTROL_DIR", str(Path.home() / "apps/72hours/auto-deploy")))
