import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

function load(env = {}) {
  const source = readFileSync(new URL("../src/lib/mcp-connect.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, JSON, process: { env } });
  return loaded.exports;
}
const URL_ = "https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/rpc";

test("every agent target uses the public endpoint and the one tentative name", () => {
  const { mcpTargets, MCP_ENDPOINT, MCP_SERVER_NAME } = load();
  assert.equal(MCP_ENDPOINT, URL_);
  assert.equal(MCP_SERVER_NAME, "72hour_mcp");
  const targets = Array.from(mcpTargets());
  assert.deepEqual(targets.map(item => item.label), ["Claude Code", "Codex", "Prompt"]);
  for (const item of targets) {
    assert.ok(item.text.includes(URL_), `${item.label} has the endpoint`);
    assert.ok(item.text.includes("72hour_mcp"), `${item.label} has the name`);
  }
  const byId = Object.fromEntries(targets.map(item => [item.id, item]));
  assert.equal(byId.codex.text, `codex mcp add 72hour_mcp --url ${URL_}`);
  assert.equal(byId.claude.text, `claude mcp add --transport http 72hour_mcp ${URL_}`);
  assert.equal(byId.prompt.kind, "prompt");
  assert.match(byId.prompt.text, /Streamable HTTP/);
  assert.match(byId.prompt.text, /No authentication/);
  assert.match(byId.prompt.text, /service_info/);
  assert.doesNotMatch(byId.prompt.text, /[가-힣]/, "the agent prompt is English");
});

test("a build-time origin override replaces the default and drops trailing slashes", () => {
  const { MCP_ENDPOINT } = load({ NEXT_PUBLIC_MCP_ORIGIN: " https://mcp.example.test/ " });
  assert.equal(MCP_ENDPOINT, "https://mcp.example.test/mcp/service/rpc");
});
