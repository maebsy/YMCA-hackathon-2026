"""Exercise HTTP protocol, stateless reconnects and public transport boundaries."""
import json
from pathlib import Path
import tempfile
import unittest

from starlette.testclient import TestClient
from handoff import Snapshot
from http_server import create_http_server, public_origin
from test_handoff import batch


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / "result.json"
        data = batch()
        blocked = batch()["results"][0]
        blocked["fingerprint"] = "blocked"
        blocked["explanation"]["fingerprint"] = "blocked"
        blocked["explanation"]["needs_manual_review"] = True
        data["results"].append(blocked)
        path.write_text(json.dumps(data), encoding="utf-8")
        self.server = create_http_server(Snapshot(path, "demo/example", "a" * 40),
                                         "https://mcp.example.com")
        self.client = self.enterContext(TestClient(self.server.streamable_http_app(),
            base_url="https://mcp.example.com", headers={"Accept": "application/json, text/event-stream"}))

    def rpc(self, method, params=None, **kwargs):
        return self.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
            "method": method, "params": params or {}}, **kwargs)

    def test_json_protocol_and_stateless_tools(self):
        response = self.rpc("initialize", {"protocolVersion": "2025-06-18",
            "capabilities": {}, "clientInfo": {"name": "http-test", "version": "1"}})
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.headers["content-type"])
        self.assertNotIn("mcp-session-id", response.headers)
        tools = self.rpc("tools/list").json()["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"list_findings", "get_fix_prompt"})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
        listing = self.rpc("tools/call", {"name": "list_findings", "arguments": {}})
        self.assertIn("demo/example", listing.text)
        result = self.rpc("tools/call", {"name": "get_fix_prompt", "arguments": {"fingerprint": "demo-sql-001"}})
        self.assertFalse(result.json()["result"]["isError"])
        for fingerprint in ("blocked", "missing"):
            result = self.rpc("tools/call", {"name": "get_fix_prompt", "arguments": {"fingerprint": fingerprint}})
            self.assertTrue(result.json()["result"]["isError"])

    def test_host_origin_and_body_limits(self):
        self.assertEqual(self.rpc("tools/list", headers={"Host": "evil.example"}).status_code, 421)
        self.assertEqual(self.rpc("tools/list", headers={"Origin": "https://evil.example"}).status_code, 403)
        result = self.client.post("/mcp", content="x" * 65537, headers={"Content-Type": "application/json"})
        self.assertEqual(result.status_code, 413)

    def test_guides_and_no_upload(self):
        for route in ("/mcp/connect", "/mcp/agent.txt", "/mcp/config.json", "/mcp/health"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        guide = self.client.get("/mcp/agent.txt").text
        self.assertIn("https://mcp.example.com/mcp", guide)
        self.assertIn("not the user's latest web scan", guide)
        self.assertIn("demo/example", guide)
        self.assertEqual(self.client.post("/mcp/connect", json={}).status_code, 405)
        self.assertEqual(self.client.get("/results.json").status_code, 404)

    def test_origin_is_not_request_controlled(self):
        for value in ("http://example.com", "https://user@example.com", "https://example.com/a",
                      "https://example.com?x=y", "https://example.com:443", "https://example.com;id"):
            with self.assertRaises(ValueError):
                public_origin(value)
