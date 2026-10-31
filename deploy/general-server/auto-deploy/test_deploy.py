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


class DrainPolicyTests(unittest.TestCase):
    """교체 대기 (#151): 진행 중 작업이 있으면 새 작업을 막지 않고, 빈 순간에만 잠깐 막고 교체합니다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.d = deploy.Deployer(self.root)
        self.d.revision = REV
        (self.d.control/"control-token").write_text("test-token")
        self.marker = self.d.control/"drain"
        self.blocked = []

    def answers(self, *values):
        values = iter(values)

        def status(*_):
            self.blocked.append(self.marker.exists())  # 상태를 물을 때마다 이용자가 막혀 있었는지 기록
            return next(values)
        return patch.object(deploy, "get_json", side_effect=status)

    def test_busy_server_is_never_blocked_and_deploy_waits_for_next_run(self):
        busy = patch.object(deploy, "get_json", return_value={"busy": 3, "draining": False})
        with busy as asked, patch.object(deploy.time, "sleep"):
            with self.assertRaisesRegex(deploy.Deferred, "without pausing"):
                self.d.drain()
        self.assertGreater(asked.call_count, 100)  # 회차 안에서 빈 순간을 계속 찾음
        self.assertFalse(self.marker.exists())

    def test_idle_moment_blocks_briefly_then_switches(self):
        with self.answers({"busy": 0, "draining": False}, {"busy": 0, "draining": True}), patch.object(deploy.time, "sleep"):
            self.d.drain()
        self.assertEqual(self.blocked, [False, True])
        self.assertTrue(self.marker.exists())  # 교체(activate)가 끝나며 풉니다

    def test_request_arriving_at_the_idle_moment_reopens_and_keeps_waiting(self):
        late = [{"busy": 1, "draining": True}] * int(deploy.DRAIN_CONFIRM_SECONDS / deploy.DRAIN_POLL_SECONDS)
        with self.answers({"busy": 0, "draining": False}, *late, {"busy": 2, "draining": False},
                          {"busy": 0, "draining": False}, {"busy": 0, "draining": True}), patch.object(deploy.time, "sleep"):
            self.d.drain()
        self.assertFalse(self.blocked[1 + len(late)])  # 20초 안에 안 끝나면 바로 풀었음
        self.assertTrue(self.marker.exists())

    def test_now_switches_without_waiting(self):
        with patch.object(deploy, "get_json") as asked:
            self.d.drain(now=True)
        asked.assert_not_called()
        self.assertTrue(self.marker.exists())

    def test_deferred_run_never_leaves_users_blocked(self):
        deploy.atomic(self.marker, {"revision": REV, "since": deploy.time.time()})
        self.d.execute = Mock(side_effect=deploy.Deferred("busy"))
        self.d.owns_lock = True
        with patch.object(deploy, "Deployer", return_value=self.d), patch("sys.argv", ["deploy.py"]):
            self.assertEqual(deploy.main(), 0)
        self.assertFalse(self.marker.exists())

    def test_execute_clears_any_leftover_drain(self):
        for leftover in ("", json.dumps({"revision": REV, "since": deploy.time.time()})):
            self.marker.write_text(leftover)
            self.d.head = lambda: REV
            self.d.ready = lambda revision: False
            with patch.object(deploy, "locks", return_value=nullcontext()):
                with self.assertRaises(deploy.Deferred):
                    self.d.execute(SimpleNamespace(retry=False))
            self.assertFalse(self.marker.exists())


class McpDeployTests(unittest.TestCase):
    """MCP도 같은 main 커밋으로: 바뀐 경우만, 후보 확인 → 교체 → 실패 시 이전 버전 (#151)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.d = deploy.Deployer(self.root)
        self.d.revision = REV
        self.d.run = Mock()
        self.d.mcp_env = lambda: {"MCP_PUBLIC_ORIGIN": "https://fixed.example,https://old.example"}
        self.mcp = self.root/"mcp"
        self.old = self.mcp/"releases/old"
        self.old.mkdir(parents=True)
        (self.old/"requirements.txt").write_text("mcp==1\n")
        (self.mcp/"live-current").symlink_to(self.old, target_is_directory=True)
        self.release = self.root/"auto-releases"/REV
        source = self.release/deploy.MCP_SOURCE
        (source/"tests").mkdir(parents=True)
        (source/"requirements.txt").write_text("mcp==1\n")
        (source/"live_server.py").write_text("# new\n")
        (source/"tests/test_x.py").write_text("")
        self.checks = []
        self.d.mcp_check = lambda port, host: self.checks.append((port, host)) or {"service_info", "start_scan"}

    def live(self):
        return (self.mcp/"live-current").resolve()

    def popen(self):
        return patch.object(deploy.subprocess, "Popen", return_value=Mock(poll=Mock(return_value=None)))

    def test_switches_after_candidate_and_live_checks(self):
        with self.popen() as started:
            self.assertEqual(self.d.update_mcp(self.release), "deployed")
        target = self.mcp/"releases"/REV
        self.assertEqual(self.live(), target)
        self.assertTrue((target/"live_server.py").exists())
        self.assertFalse((target/"tests").exists())
        self.assertIn("https://fixed.example,https://old.example", started.call_args[0][0])
        self.assertEqual(self.checks, [(deploy.MCP_CANDIDATE_PORT, "fixed.example"), (deploy.MCP_LIVE_PORT, "fixed.example")])
        self.d.run.assert_called_once_with(["systemctl", "--user", "restart", "72hours-mcp"], timeout=60)
        self.assertEqual(self.d.read_control("mcp-applied.json")["revision"], REV)

    def test_live_failure_restores_previous_and_is_not_retried(self):
        def check(port, host):
            if port == deploy.MCP_LIVE_PORT:
                raise RuntimeError("live failed")
        self.d.mcp_check = check
        with self.popen():
            self.assertEqual(self.d.update_mcp(self.release), "failed")
        self.assertEqual(self.live(), self.old)
        self.assertEqual(self.d.run.call_count, 2)  # 새 버전 재시작 → 이전 버전 재시작
        self.assertEqual(self.d.read_control("mcp-failed.json")["revision"], REV)
        self.assertFalse(self.d.mcp_pending(self.release))  # 같은 SHA는 --retry 전까지 다시 시도하지 않음
        self.d.retry = True
        self.assertTrue(self.d.mcp_pending(self.release))

    def test_candidate_failure_never_touches_live(self):
        self.d.mcp_check = Mock(side_effect=RuntimeError("candidate failed"))
        with self.popen():
            self.assertEqual(self.d.update_mcp(self.release), "failed")
        self.assertEqual(self.live(), self.old)
        self.d.run.assert_not_called()

    def test_dependency_change_is_left_to_operator(self):
        (self.release/deploy.MCP_SOURCE/"requirements.txt").write_text("mcp==2\n")
        self.assertEqual(self.d.update_mcp(self.release), "failed")
        self.assertIn("dependencies", self.d.read_control("mcp-failed.json")["reason"])
        self.assertEqual(self.live(), self.old)

    def test_line_endings_and_comments_are_not_dependency_changes(self):
        # 운영에서 실제로 막혔던 경우: 예전 수동 배포본이 CRLF
        (self.old/"requirements.txt").write_bytes(b"# pinned\r\nmcp==1\r\n\r\n")
        with self.popen():
            self.assertEqual(self.d.update_mcp(self.release), "deployed")

    def test_unchanged_mcp_is_marked_without_restart(self):
        deploy.atomic(self.d.control/"mcp-applied.json", {"revision": "b" * 40})
        self.d.capture = Mock(return_value="")
        self.assertIsNone(self.d.update_mcp(self.release))
        self.d.run.assert_not_called()
        self.assertEqual(self.d.read_control("mcp-applied.json")["revision"], REV)

    def test_servers_without_managed_mcp_are_left_alone(self):
        (self.mcp/"live-current").unlink()
        self.assertIsNone(self.d.update_mcp(self.release))

    def test_follow_up_runs_even_when_app_is_already_current(self):
        deploy.atomic(self.d.control/"applied.json", {"revision": REV})
        (self.release/".ready").touch()
        self.d.head = lambda: REV
        self.d.follow_up = Mock(return_value={"mcp": "deployed"})
        with patch.object(deploy, "locks", return_value=nullcontext()):
            self.d.execute(SimpleNamespace(retry=False))
        self.d.follow_up.assert_called_once_with(self.release)
        self.assertEqual(json.loads(self.d.state.read_text())["mcp"], "deployed")


class RuntimeSelfUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.d = deploy.Deployer(self.root)
        self.d.runtime = self.d.control/"runtime"
        self.d.runtime.mkdir()
        self.source = self.root/"release/deploy/general-server/auto-deploy"
        self.source.mkdir(parents=True)
        for name in deploy.RUNTIME_FILES:
            (self.d.runtime/name).write_text("OLD = 1\n")
            (self.source/name).write_text("OLD = 1\n")

    def test_changed_files_are_replaced(self):
        (self.source/"deploy.py").write_text("NEW = 2\n")
        self.assertEqual(self.d.update_runtime(self.root/"release"), ["deploy.py"])
        self.assertEqual((self.d.runtime/"deploy.py").read_text(), "NEW = 2\n")

    def test_any_syntax_error_changes_nothing(self):
        (self.source/"deploy.py").write_text("NEW = 2\n")
        (self.source/"snapshot.py").write_text("def broken(:\n")
        self.assertEqual(self.d.update_runtime(self.root/"release"), ["invalid"])
        self.assertEqual((self.d.runtime/"deploy.py").read_text(), "OLD = 1\n")

    def test_operator_install_is_kept_until_main_catches_up(self):
        (self.d.runtime/"deploy.py").write_text("OPERATOR = 3\n")
        (self.d.control/"runtime-pinned").touch()
        self.assertEqual(self.d.update_runtime(self.root/"release"), [])
        self.assertEqual((self.d.runtime/"deploy.py").read_text(), "OPERATOR = 3\n")  # 옛 main으로 되돌리지 않음
        (self.source/"deploy.py").write_text("OPERATOR = 3\n")  # 머지돼 main이 같아짐
        self.assertEqual(self.d.update_runtime(self.root/"release"), [])
        self.assertFalse((self.d.control/"runtime-pinned").exists())
        (self.source/"deploy.py").write_text("LATER = 4\n")  # 그 뒤로는 자동 갱신
        self.assertEqual(self.d.update_runtime(self.root/"release"), ["deploy.py"])

    def test_running_from_repository_never_self_updates(self):
        self.d.runtime = self.root/"elsewhere"
        self.assertEqual(self.d.update_runtime(self.root/"release"), [])


class OperatorControlTests(unittest.TestCase):
    """테스트·시연 중 자동 배포를 쉽게 멈추고 다시 켜기 (--pause / --resume / --status)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.control = self.root/"auto-deploy"
        self.control.mkdir()
        (self.control/"control-token").write_text("test-token")

    def run_main(self, *argv):
        with patch("sys.argv", ["deploy.py", "--root", str(self.root), *argv]):
            return deploy.main()

    def test_pause_reopens_jobs_and_stops_deploys_until_resume(self):
        deploy.atomic(self.control/"drain", {"revision": REV, "since": deploy.time.time()})
        self.assertEqual(self.run_main("--pause", "시연 중"), 0)
        self.assertFalse((self.control/"drain").exists())
        d = deploy.Deployer(self.root)
        d.head = Mock(return_value=REV)
        with patch.object(deploy, "locks", return_value=nullcontext()):
            d.execute(SimpleNamespace(retry=False))
        d.head.assert_not_called()  # 멈춘 동안은 main 조회·빌드·교체를 하지 않음
        self.assertEqual(json.loads((self.control/"status.json").read_text())["status"], "paused")
        self.assertEqual(self.run_main("--resume"), 0)
        self.assertIsNone(d.paused())

    def test_pause_during_wait_stops_waiting(self):
        d = deploy.Deployer(self.root)
        d.revision = REV
        answers = iter([{"busy": 1, "draining": True}])

        def status(*_):
            deploy.pause(self.root, "테스트")  # 기다리는 도중 운영자가 멈춤
            return next(answers)
        with patch.object(deploy, "get_json", side_effect=status), patch.object(deploy.time, "sleep"):
            with self.assertRaisesRegex(deploy.Deferred, "Paused"):
                d.drain()

    def test_pause_during_switch_leaves_drain_for_the_switch_to_finish(self):
        deploy.atomic(self.control/"drain", {"revision": REV, "since": deploy.time.time()})
        deploy.atomic(self.control/"transaction.json", {"backend": "a", "frontend": "b"})
        deploy.pause(self.root)
        self.assertTrue((self.control/"drain").exists())

    def test_status_is_read_only(self):
        with patch.object(deploy, "get_json", return_value={"busy": 2, "draining": False}), \
                patch("builtins.print") as printed:
            self.assertEqual(self.run_main("--status"), 0)
        shown = json.loads(printed.call_args[0][0])
        self.assertEqual(shown["backend"], {"busy": 2, "draining": False})
        self.assertFalse((self.control/"status.json").exists())


class StaleDrainGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_drain_marker_no_longer_blocks_users(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guard = DeploymentGuard(AsyncMock(), root)
            (root/"drain").write_text(json.dumps({"since": deploy.time.time()}))
            self.assertTrue(guard.draining())
            (root/"drain").write_text(json.dumps({"since": deploy.time.time() - 26 * 60}))
            self.assertFalse(guard.draining())  # 배포가 교체 도중 죽어도 이용자를 영원히 막지 않음 (10분)
            (root/"drain").touch()
            (root/"drain").write_text("")
            self.assertTrue(guard.draining())  # 예전 빈 파일은 그대로 대기
