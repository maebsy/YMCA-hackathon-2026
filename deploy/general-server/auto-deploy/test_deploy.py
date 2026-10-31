import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import deploy
from deployment_entry import DeploymentGuard

REV = "a" * 40


def run(id=1, path=".github/workflows/ci.yml", **extra):
    return dict(id=id, path=path, head_sha=REV, head_branch="main", event="push",
                status="completed", conclusion="success", **extra)


class GateTests(unittest.TestCase):
    def test_exact_main_ci_is_required(self):
        self.assertFalse(deploy.ci_ready([], REV))
        self.assertTrue(deploy.ci_ready([run()], REV))
        for key, value in (("head_sha", "b"*40), ("event", "pull_request"),
                           ("head_branch", "feature"), ("conclusion", "failure"), ("status", "queued")):
            self.assertFalse(deploy.ci_ready([{**run(), key: value}], REV))

    def test_latest_rerun_and_other_workflows_gate(self):
        failed = {**run(), "conclusion": "failure"}
        self.assertTrue(deploy.ci_ready([failed, run(id=2)], REV))
        self.assertFalse(deploy.ci_ready([run(), {**run(id=2), "conclusion":"cancelled"}], REV))
        self.assertFalse(deploy.ci_ready([run(), {**run(path="docker.yml"), "status":"in_progress"}], REV))

    def test_build_environment_omits_application_secrets(self):
        with patch.dict("os.environ", {"DATABASE_URL":"secret", "LLM_API_KEY":"secret", "GITHUB_TOKEN":"secret"}):
            for key in ("DATABASE_URL", "LLM_API_KEY", "GITHUB_TOKEN"):
                self.assertNotIn(key, deploy.safe_env())

    def test_user_service_bus_environment_is_preserved(self):
        with patch.dict("os.environ", {"XDG_RUNTIME_DIR":"/run/user/123", "DBUS_SESSION_BUS_ADDRESS":"unix:path=/run/user/123/bus"}):
            env = deploy.safe_env()
            self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/123")
            self.assertEqual(env["DBUS_SESSION_BUS_ADDRESS"], "unix:path=/run/user/123/bus")


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.d = deploy.Deployer(self.root)
        self.d.revision = REV
        self.previous = {"current": self.root/"old", "frontend":self.root/"old-front"}
        self.targets = dict(self.previous)
        self.d.target = lambda link: self.targets[link.name]
        self.d.link = lambda name, target: self.targets.update({name:Path(target)})
        self.d.restart = Mock()
        self.d.run = Mock()
        self.d.health = Mock()
        (self.d.control/"drain").touch()

    def test_success_switches_both_and_records_revision(self):
        self.d.activate(self.root/"new", "https://public.example")
        self.assertEqual(self.targets, {"current":self.root/"new", "frontend":self.root/"new/frontend"})
        self.assertEqual(json.loads((self.d.control/"applied.json").read_text())["revision"], REV)
        self.assertFalse(self.d.transaction.exists())
        self.assertFalse((self.d.control/"drain").exists())

    def test_public_health_failure_restores_both(self):
        self.d.health.side_effect = [None, RuntimeError("public failure"), None]
        with self.assertRaises(RuntimeError):
            self.d.activate(self.root/"new", "https://public.example")
        self.assertEqual(self.targets, self.previous)
        self.assertEqual(self.d.restart.call_count, 2)
        self.assertFalse((self.d.control/"applied.json").exists())
        self.assertFalse(self.d.transaction.exists())

    def test_rollback_failure_preserves_recovery_journal(self):
        self.d.health.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            self.d.activate(self.root/"new")
        self.assertTrue(self.d.transaction.exists())
        self.assertTrue((self.d.control/"drain").exists())

    def test_snapshot_failure_does_not_switch(self):
        self.d.run.side_effect = RuntimeError("snapshot failed")
        with self.assertRaises(RuntimeError):
            self.d.activate(self.root/"new")
        self.assertEqual(self.targets, self.previous)
        self.d.restart.assert_not_called()

    def test_busy_jobs_defer_without_restart(self):
        (self.d.control/"control-token").write_text("test-token")
        with patch.object(deploy, "get_json", return_value={"busy":1,"draining":True}), patch.object(deploy.time,"sleep"):
            with self.assertRaises(deploy.Deferred):
                self.d.drain()
        self.d.restart.assert_not_called()

    def test_guard_error_requires_explicit_legacy_bootstrap(self):
        (self.d.control/"control-token").write_text("test-token")
        error = deploy.urllib.error.HTTPError("http://localhost", 404, "unavailable", {}, None)
        with patch.object(deploy, "get_json", side_effect=error):
            with self.assertRaises(deploy.Deferred):
                self.d.drain()
            self.d.drain(bootstrap=True)
            self.previous["current"].mkdir()
            (self.previous["current"]/"deployment.json").write_text("{}")
            with self.assertRaises(deploy.Deferred):
                self.d.drain(bootstrap=True)

    def test_unhealthy_guard_cannot_be_bypassed_by_bootstrap(self):
        (self.d.control/"control-token").write_text("test-token")
        error = deploy.urllib.error.HTTPError("http://localhost", 503, "unavailable", {}, None)
        with patch.object(deploy, "get_json", side_effect=error):
            with self.assertRaises(deploy.Deferred):
                self.d.drain(bootstrap=True)

    def test_schema_change_needs_exact_reviewed_revision(self):
        self.d.capture = Mock(side_effect=["b"*40, "docs/migrations/052-scan-persistence.sql"] * 3)
        with self.assertRaises(deploy.Deferred):
            self.d.check_schema(self.root/"new")
        with self.assertRaises(deploy.Deferred):
            self.d.check_schema(self.root/"new", "c"*40)
        self.d.check_schema(self.root/"new", REV)

    def test_schema_unchanged_can_deploy(self):
        self.d.capture = Mock(side_effect=["b"*40, "frontend/src/app/page.tsx"])
        self.d.check_schema(self.root/"new")

    def test_unchanged_revision_does_not_build(self):
        deploy.atomic(self.d.control/"applied.json", {"revision":REV})
        self.d.head = lambda: REV
        self.d.prepare = Mock()
        with patch.object(deploy,"locks", return_value=nullcontext()):
            self.d.execute(SimpleNamespace(retry=False))
        self.d.prepare.assert_not_called()

    def test_ci_failure_does_not_build(self):
        self.d.head = lambda: REV
        self.d.ready = lambda revision: False
        self.d.prepare = Mock()
        with patch.object(deploy,"locks", return_value=nullcontext()):
            with self.assertRaises(deploy.Deferred):
                self.d.execute(SimpleNamespace(retry=False))
        self.d.prepare.assert_not_called()

    def test_lock_contention_cannot_clear_other_deployment_drain(self):
        self.d.execute = Mock(side_effect=deploy.Deferred("busy"))
        with patch.object(deploy, "Deployer", return_value=self.d), patch("sys.argv", ["deploy.py"]):
            self.assertEqual(deploy.main(), 0)
        self.assertTrue((self.d.control/"drain").exists())


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/"control-token").write_text("local-secret")
        self.app = AsyncMock()
        self.guard = DeploymentGuard(self.app, self.root)
        self.guard.busy = AsyncMock(return_value=0)

    async def request(self, path, method="GET", headers=()):
        output = []
        async def send(value):
            output.append(value)
        await self.guard({"type":"http", "path":path,"method":method,"headers":headers}, AsyncMock(), send)
        return output

    async def test_control_requires_secret_even_on_loopback_proxy(self):
        response = await self.request("/api/_deployment/status")
        self.assertEqual(response[0]["status"], 404)
        self.guard.busy.assert_not_called()

    async def test_control_returns_counts_only(self):
        response = await self.request("/api/_deployment/status", headers=[(b"x-deployment-token",b"local-secret")])
        self.assertEqual(json.loads(response[1]["body"]), {"busy":0,"draining":False})

    async def test_drain_blocks_submission_but_allows_polling(self):
        (self.root/"drain").touch()
        response = await self.request("/api/scans", "POST")
        self.assertEqual(response[0]["status"], 503)
        self.app.assert_not_called()
        await self.request("/api/scans/existing-job")
        self.app.assert_awaited_once()
        self.assertEqual(self.guard.active, 0)

    async def test_failed_http_request_does_not_leak_active_counter(self):
        self.app.side_effect = RuntimeError("request failed")
        with self.assertRaises(RuntimeError):
            await self.request("/api/scans", "POST")
        self.assertEqual(self.guard.active, 0)


if __name__ == "__main__":
    unittest.main()
