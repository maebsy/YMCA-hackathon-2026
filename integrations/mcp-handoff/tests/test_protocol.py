"""Real stdio handshake and both delivery paths, with synthetic results only."""

import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

from test_handoff import batch


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_tools_and_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            data = batch()
            blocked = batch()["results"][0]
            blocked["fingerprint"] = "blocked"
            blocked["explanation"]["fingerprint"] = "blocked"
            blocked["explanation"]["needs_manual_review"] = True
            data["results"].append(blocked)
            path.write_text(json.dumps(data), encoding="utf-8")
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(Path(__file__).resolve().parents[1] / "server.py"),
                      "--results", str(path), "--repository", "demo/example",
                      "--revision", "a" * 40],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as client:
                    initialized = await client.initialize()
                    self.assertEqual(initialized.serverInfo.name, "72hours-handoff")
                    tools = (await client.list_tools()).tools
                    self.assertEqual({t.name for t in tools}, {"list_findings", "get_fix_prompt"})
                    self.assertTrue(all(t.annotations.readOnlyHint for t in tools))
                    listing = await client.call_tool("list_findings", {})
                    self.assertFalse(listing.isError)
                    rows = json.loads(listing.content[0].text)["findings"]
                    self.assertEqual(rows[0], {"fingerprint": "demo-sql-001", "ready": True, "reason": None})
                    self.assertFalse(rows[1]["ready"])
                    result = await client.call_tool("get_fix_prompt", {"fingerprint": "demo-sql-001"})
                    self.assertFalse(result.isError)
                    self.assertIn("매개변수", result.content[0].text)
                    prompts = await client.list_prompts()
                    self.assertEqual([p.name for p in prompts.prompts], ["fix_finding"])
                    prompt = await client.get_prompt("fix_finding", {"fingerprint": "demo-sql-001"})
                    self.assertEqual(prompt.messages[0].role, "user")
                    self.assertEqual(prompt.messages[0].content.text, result.content[0].text)
                    for fingerprint in ("blocked", "missing"):
                        error = await client.call_tool("get_fix_prompt", {"fingerprint": fingerprint})
                        self.assertTrue(error.isError)
                        self.assertNotIn("매개변수", error.content[0].text)
                    with self.assertRaises(McpError):
                        await client.get_prompt("fix_finding", {"fingerprint": "blocked"})


if __name__ == "__main__":
    unittest.main()
