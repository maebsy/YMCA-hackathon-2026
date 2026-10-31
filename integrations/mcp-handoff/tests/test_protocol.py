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

    async def test_stdio_live_file_updates_without_restart(self):
        """--revision 없이 띄우면 웹이 덮어쓴 최신 파일을 다음 호출에서 읽습니다 (#65)."""
        from test_live import REV_A, REV_B, web_file

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "72hours-mcp-demo-example.json"
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(Path(__file__).resolve().parents[1] / "server.py"),
                      "--results", str(path), "--repository", "demo/example"],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as client:
                    await client.initialize()
                    # 최초 연결: 파일이 아직 없어도 서버는 뜨고 다음 할 일을 알려 줌
                    empty = json.loads((await client.call_tool("list_findings", {})).content[0].text)
                    self.assertEqual(empty["findings"], [])
                    self.assertIn("자동 저장", empty["notice"])

                    path.write_text(json.dumps(web_file("first", REV_A)), encoding="utf-8")
                    os.utime(path, (1_700_000_000, 1_700_000_000))
                    first = json.loads((await client.call_tool("list_findings", {})).content[0].text)
                    self.assertEqual(first["source"]["revision"], REV_A)
                    self.assertEqual(first["findings"][0]["fingerprint"], "first")

                    # 재검사 결과로 덮어쓰기 → 같은 MCP 세션에서 바로 최신 결과
                    path.write_text(json.dumps(web_file("second", REV_B, prompt="재검사 뒤 새 지시")), encoding="utf-8")
                    os.utime(path, (1_700_000_100, 1_700_000_100))
                    second = json.loads((await client.call_tool("list_findings", {})).content[0].text)
                    self.assertEqual(second["source"]["revision"], REV_B)
                    result = await client.call_tool("get_fix_prompt", {"fingerprint": "second"})
                    self.assertFalse(result.isError)
                    self.assertIn("재검사 뒤 새 지시", result.content[0].text)
                    stale = await client.call_tool("get_fix_prompt", {"fingerprint": "first"})
                    self.assertTrue(stale.isError)


if __name__ == "__main__":
    unittest.main()
