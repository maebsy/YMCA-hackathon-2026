"""Real HTTP protocol and capability isolation; synthetic inputs are never production fixtures."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from starlette.testclient import TestClient
from handoff import HandoffError
from live_server import create_live_app
from live_store import LinkStore, MAX_BODY, normalize
from test_handoff import batch

ORIGIN = "https://mcp.example.com"


def export(repo="demo/one", scan_id="1" * 32):
    return {"scan": {"repository": repo, "revision": "a" * 40, "scan_id": scan_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(), "fingerprints": ["demo-sql-001"]},
        "results": batch()["results"]}


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.time = [1000.0]
        self.store = LinkStore(Path(self.directory.name) / "links.sqlite3", ttl=60, clock=lambda: self.time[0])
        self.client = self.enterContext(TestClient(create_live_app(self.store, ORIGIN), base_url=ORIGIN))

    def issue(self, doc=None):
        response = self.client.post("/mcp/links", json=doc or export(), headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def rpc(self, link, method="tools/call", params=None):
        return self.client.post(link["endpoint"], headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": method,
                  "params": params or {"name": "list_findings", "arguments": {}}})

    def test_real_mcp_is_scoped_and_no_sample(self):
        one, two = self.issue(), self.issue(export("demo/two", "2" * 32))
        initialized = self.rpc(one, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "live-test", "version": "1"}})
        self.assertEqual(initialized.status_code, 200)
        self.assertNotIn("mcp-session-id", initialized.headers)
        self.assertEqual(self.client.get("/mcp").status_code, 401)
        self.assertEqual(self.client.get("/mcp/agent.txt").status_code, 401)
        def check(link):
            response = self.rpc(link)
            self.assertEqual(response.status_code, 200)
            source = json.loads(response.json()["result"]["content"][0]["text"])["source"]
            self.assertEqual(source["repository"], link["source"]["repository"])
            self.assertEqual(source["scan_id"], link["source"]["scan_id"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(check, [one, two] * 4))
        result = self.rpc(one, params={"name": "get_fix_prompt", "arguments": {"fingerprint": "demo-sql-001"}})
        self.assertFalse(result.json()["result"]["isError"])
        self.assertIn("demo/one", result.text)
        self.assertNotIn("demo/two", result.text)
        self.assertIn("browser_export_not_server_verified", result.text)
        denied = self.rpc(one, params={"name": "get_fix_prompt", "arguments": {"fingerprint": "other"}})
        self.assertTrue(denied.json()["result"]["isError"])

    def test_revocation_requires_separate_secret_and_is_immediate(self):
        one, two = self.issue(), self.issue()
        response = self.client.post("/mcp/links/revoke", json={"token": one["token"],
            "revoke_token": two["revoke_token"]}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.rpc(one).status_code, 200)
        response = self.client.post("/mcp/links/revoke", json={"token": one["token"],
            "revoke_token": one["revoke_token"]}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rpc(one).status_code, 404)
        self.assertEqual(self.client.get(one["guide_url"]).status_code, 404)
        self.assertEqual(self.rpc(two).status_code, 200)

    def test_expiration_and_durable_restart(self):
        link = self.issue()
        restarted = LinkStore(self.store.path, ttl=60, clock=lambda: self.time[0])
        self.assertEqual(restarted.get(link["token"]).provenance["scan_id"], "1" * 32)
        self.time[0] += 61
        self.assertEqual(self.rpc(link).status_code, 404)
        self.assertEqual(self.client.get(link["guide_url"]).status_code, 404)

    def test_request_boundaries(self):
        for origin in (None, "https://evil.example"):
            response = self.client.post("/mcp/links", json=export(), headers={"Origin": origin} if origin else {})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/mcp/links", content="x", headers={"Origin": ORIGIN}).status_code, 400)
        response = self.client.post("/mcp/links", content=b"x" * (MAX_BODY + 1),
            headers={"Origin": ORIGIN, "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)
        for body in ("[]", '{"scan":{},"scan":{}}'):
            self.assertEqual(self.client.post("/mcp/links", content=body,
                headers={"Origin": ORIGIN, "Content-Type": "application/json"}).status_code, 400)
        self.assertEqual(self.client.get("/mcp/links").status_code, 405)

    def test_minimal_storage_and_no_capability_in_database(self):
        doc = export()
        doc["raw"] = "NEVER_STORE_SOURCE"
        doc["results"][0]["explanation"]["attack_scenario"] = "NEVER_STORE_ATTACK"
        link = self.issue(doc)
        raw = self.store.path.read_bytes()
        for value in (link["token"], link["revoke_token"], "NEVER_STORE_SOURCE", "NEVER_STORE_ATTACK"):
            self.assertNotIn(value.encode(), raw)
        guide = self.client.get(link["guide_url"])
        self.assertEqual(guide.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(guide.headers["Cache-Control"], "no-store")
        self.assertNotIn(link["revoke_token"], guide.text)
        self.assertIn("demo/one", guide.text)

    def test_gate_identity_and_capacity(self):
        cases = []
        doc = export(); doc["scan"]["revision"] = "bad"; cases.append(doc)
        doc = export(); doc["scan"]["scan_id"] = "sample"; cases.append(doc)
        doc = export(); doc["scan"]["fingerprints"] = ["other"]; cases.append(doc)
        doc = export(); doc["results"][0]["covers"] = ["other"]; cases.append(doc)
        doc = export(); doc["results"][0]["explanation"]["needs_manual_review"] = True; cases.append(doc)
        doc = export(); doc["results"] = []; cases.append(doc)
        doc = export(); doc["results"].append(copy.deepcopy(doc["results"][0])); cases.append(doc)
        for doc in cases:
            with self.assertRaises(HandoffError):
                normalize(doc)
        self.store.limit = 1
        self.issue()
        self.assertEqual(self.client.post("/mcp/links", json=export(), headers={"Origin": ORIGIN}).status_code, 429)


class MultiOriginTests(unittest.TestCase):
    """고정 주소(대표) + 웹에 함께 쓰는 임시 주소를 모두 받되, 연결 주소는 항상 대표 주소로 만듭니다 (#136)."""
    FIXED = "https://fixed.example.dev"
    TEMP = "https://temp-words.trycloudflare.com"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = LinkStore(Path(self.directory.name) / "links.sqlite3", ttl=60)
        self.app = create_live_app(self.store, f"{self.FIXED}, {self.TEMP}")

    def test_link_created_from_second_origin_uses_fixed_origin(self):
        with TestClient(self.app, base_url=self.TEMP) as client:
            response = client.post("/mcp/links", json=export(), headers={"Origin": self.TEMP})
        self.assertEqual(response.status_code, 201, response.text)
        link = response.json()
        self.assertTrue(link["endpoint"].startswith(self.FIXED + "/mcp/h/"))
        self.assertTrue(link["guide_url"].startswith(self.FIXED + "/mcp/h/"))

    def test_mcp_answers_on_both_hosts_but_not_others(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_findings", "arguments": {}}}
        # MCP 세션 관리자는 앱마다 한 번만 띄울 수 있어 클라이언트는 하나로 두고 Host 만 바꿉니다
        with TestClient(self.app, base_url=self.FIXED) as client:
            link = client.post("/mcp/links", json=export(), headers={"Origin": self.FIXED}).json()
            path = link["endpoint"].removeprefix(self.FIXED)
            for host, ok in (("fixed.example.dev", True), ("temp-words.trycloudflare.com", True), ("evil.example", False)):
                response = client.post(path, json=body, headers={"Host": host, "Accept": "application/json, text/event-stream"})
                self.assertEqual(response.status_code == 200, ok, (host, response.status_code))

    def test_other_origins_are_still_rejected(self):
        with TestClient(self.app, base_url=self.FIXED) as client:
            response = client.post("/mcp/links", json=export(), headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)

    def test_every_listed_origin_is_validated(self):
        for bad in (f"{self.FIXED},http://plain.example", f"{self.FIXED},https://a.example/path", " , "):
            with self.assertRaises(ValueError):
                create_live_app(self.store, bad)

    def test_single_origin_still_works(self):
        app = create_live_app(self.store, self.FIXED)
        with TestClient(app, base_url=self.FIXED) as client:
            ok = client.post("/mcp/links", json=export(), headers={"Origin": self.FIXED})
            other = client.post("/mcp/links", json=export(), headers={"Origin": self.TEMP})
        self.assertEqual((ok.status_code, other.status_code), (201, 403))
