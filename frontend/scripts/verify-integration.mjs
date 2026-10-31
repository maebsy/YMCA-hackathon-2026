import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(resolve(root, "package.json"));
const ts = require("typescript");
const storage = new Map();
const requests = [];
let replies = [];
const runtime = {
  URL, Date, Map, Set, console, AbortSignal,
  setTimeout(callback) { callback(); return 0; },
  localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
  fetch: async (url, options) => {
    requests.push({ url, options });
    assert.ok(replies.length, `Unexpected request: ${url}`);
    const reply = replies.shift();
    if (reply instanceof Error) throw reply;
    return { ok: reply.ok ?? true, status: reply.status ?? 200, json: async () => reply.body,
      text: async () => typeof reply.body === "string" ? reply.body : JSON.stringify(reply.body) };
  },
};
function compile(relative, imports = {}) {
  const source = readFileSync(resolve(root, relative), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { ...runtime, module: loaded, exports: loaded.exports, require: name => imports[name] ?? require(name) }, { filename: relative });
  return loaded.exports;
}
const api = compile("src/lib/api.ts");
const provider = compile("src/components/repository-provider.tsx", { "@/lib/api": api });
const { normalizeRepositoryUrl, parseSavedRepository } = provider;
let checks = 0;
function check(name, fn) { fn(); checks++; console.log(`PASS ${name}`); }
async function checkAsync(name, fn) { requests.length = 0; replies = []; await fn(); assert.equal(replies.length, 0); checks++; console.log(`PASS ${name}`); }

check("GitHub URL accepts only a repository root and normalizes .git", () => {
  for (const [input, expected] of [
    ["https://github.com/acme/app", "https://github.com/acme/app"],
    ["github.com/acme/app", "https://github.com/acme/app"],
    [" github.com/acme/app.git/ ", "https://github.com/acme/app"],
    [" https://github.com/acme/app.git/ ", "https://github.com/acme/app"],
    ["https://GitHub.com/acme/app", "https://github.com/acme/app"],
    ["GitHub.com/acme/app", "https://github.com/acme/app"],
    ["https://github.com/a/a-b_c.d", "https://github.com/a/a-b_c.d"],
    [`https://github.com/${"a".repeat(39)}/${"b".repeat(100)}`, `https://github.com/${"a".repeat(39)}/${"b".repeat(100)}`],
  ]) assert.equal(normalizeRepositoryUrl(input), expected, input);
});
check("GitHub URL rejects website URLs, credentials, subpaths and ambiguous encodings", () => {
  const invalid = ["", "http://github.com/acme/app", "https://example.com/a/b", "https://github.com.evil.com/a/b",
    "https://github.com@evil.com/a/b", "https://user:secret@github.com/a/b", "https://github.com:443/a/b", "https://github.com/a/b/tree/main",
    "https://github.com/a/b?token=secret", "https://github.com/a/b#readme", "https://github.com/a/b%2fhidden", "https://github.com/a/b\\x",
    "https://github.com/a", "https://github.com/a//", "https://github.com/a/.", "https://github.com/a/..", "https://github.com/a/.git",
    "https://github.com/-a/b", "https://github.com/a-/b", "https://github.com/a--b/c", "https://github.com/a.b/c", `https://github.com/${"a".repeat(40)}/b`,
    `https://github.com/a/${"b".repeat(101)}`, "https://github.com/a/a b", "https://github.com/a/b//", "https://github.com./a/b"];
  invalid.forEach(input => assert.equal(normalizeRepositoryUrl(input), null, input));
});
const engineItem = { id: "opengrep:test", title: "Example issue", where: "src/app.ts:1", severity: "high", status: "open", kind: "code", what: "Example evidence", fix_hint: { command: "review", text: "Inspect the code" } };
const finding = api.itemToFinding(engineItem);
const saved = { verificationSource: "engine-status-v1", repoUrl: "https://github.com/acme/app", findings: [finding], result: { target: { repo_url: "https://github.com/acme/app" } },
  reportInput: { scan: { id: "scan-test" }, findings: [engineItem], explain_results: [] }, logs: [], pendingIds: [finding.id] };
check("Saved real result restores zero findings", () => assert.equal(parseSavedRepository({ ...saved, findings: [] }).findings.length, 0));
check("Saved malformed or demo-only state does not become a real result", () => {
  for (const input of [null, {}, { findings: [] }, { ...saved, result: null }, { ...saved, reportInput: null }, { ...saved, findings: [{}] },
    { ...saved, findings: [{ ...finding, commands: null }] }, { ...saved, repoUrl: "https://tiny-shop.example" }]) assert.equal(parseSavedRepository(input), null);
});
check("Saved pending flags remain separate and exclude engine-resolved or unknown IDs", () => {
  const restored = parseSavedRepository({ ...saved, findings: [finding, { ...finding, id: "resolved", fixed: true }], pendingIds: [finding.id, finding.id, "resolved", "missing"], logs: [{ bad: true }] });
  assert.equal(restored.findings[0].fixed, false); assert.deepEqual([...restored.pendingIds], [finding.id]); assert.equal(restored.logs.length, 0);
});
check("Legacy manual fixed flags restore as pending, never engine verified", () => {
  const restored = parseSavedRepository({ ...saved, verificationSource: undefined, findings: [{ ...finding, fixed: true }], pendingIds: [finding.id, finding.id] });
  assert.equal(restored.findings[0].fixed, false); assert.deepEqual([...restored.pendingIds], [finding.id]);
  assert.match(restored.findings[0].verdict, /재검증 필요/);
});
check("Versioned engine verification survives restore", () => {
  const restored = parseSavedRepository({ ...saved, findings: [{ ...finding, fixed: true }], pendingIds: [finding.id] });
  assert.equal(restored.findings[0].fixed, true); assert.equal(restored.pendingIds.length, 0);
});
check("Only code_resolved marks an engine finding fixed", () => {
  for (const status of ["open", "runtime_check_needed", "out_of_scope", "resolved", "code_resolved"]) assert.equal(api.itemToFinding({ ...engineItem, status }).fixed, status === "code_resolved");
  const enriched = api.mergeExplanation(finding, { explanation: { red_verdict: "pass", summary: "AI summary" } });
  assert.equal(enriched.fixed, false);
});
await checkAsync("Scan API submits same-repository previous results and polls until done", async () => {
  const previous = { target: { repo_url: saved.repoUrl }, findings: [] };
  const result = { llm_input: { items: [] } };
  const statuses = [];
  replies = [{ body: { job_id: "job-1" } }, { body: { status: "running" } }, { body: { status: "done", result } }];
  assert.equal(await api.startScan(saved.repoUrl, previous, status => statuses.push(status)), result);
  assert.deepEqual(statuses, ["running", "done"]);
  assert.deepEqual(JSON.parse(requests[0].options.body), { repo_url: saved.repoUrl, previous });
  assert.deepEqual(requests.map(request => request.url), ["/api/scans", "/api/scans/job-1", "/api/scans/job-1"]);
});
await checkAsync("Scan API sends null previous on first scan", async () => {
  replies = [{ body: { job_id: "first" } }, { body: { status: "done", result: {} } }];
  await api.startScan(saved.repoUrl); assert.equal(JSON.parse(requests[0].options.body).previous, null);
});
await checkAsync("Scan API surfaces queue rejection", async () => {
  replies = [{ ok: false, status: 400, body: { detail: { message: "invalid repo" } } }];
  await assert.rejects(api.startScan(saved.repoUrl), /invalid repo/);
});
await checkAsync("Scan API preserves login, owner-policy and queue errors", async () => {
  for (const [status, message] of [[401, "login required"], [403, "owner not allowed"], [429, "queue full"]]) {
    replies.push({ ok: false, status, body: { detail: { message } } });
    await assert.rejects(api.startScan(saved.repoUrl), new RegExp(message));
  }
});
await checkAsync("Scan API surfaces failed job without inventing results", async () => {
  replies = [{ body: { job_id: "failed" } }, { body: { status: "failed", error: { message: "clone failed" } } }];
  await assert.rejects(api.startScan(saved.repoUrl), /clone failed/);
});
await checkAsync("Scan API surfaces polling failure", async () => {
  replies = [{ body: { job_id: "gone" } }, { ok: false, status: 503, body: {} }];
  await assert.rejects(api.startScan(saved.repoUrl), /503/);
});
await checkAsync("LLM health network failure remains optional", async () => {
  replies = [new Error("offline")]; assert.equal(await api.llmHealthy(), false);
});
await checkAsync("LLM requests retain selected OS and engine findings", async () => {
  replies = [{ body: { job_id: "explain-1" } }, { body: { status: "running" } }, { body: { status: "done", result: { results: [] } } }];
  await api.explain([engineItem], "linux", "netlify");
  assert.equal(requests[0].url, "/api/llm/explain/tasks");
  assert.deepEqual(JSON.parse(requests[0].options.body), { findings: [engineItem], mode: "red_blue", environment: { os: "linux", hosting: "netlify" } });
  assert.deepEqual(requests.slice(1).map(request => request.url), ["/api/llm/explain/tasks/explain-1", "/api/llm/explain/tasks/explain-1"]);
});
await checkAsync("HTML and Markdown reports pass actual scan input to existing API", async () => {
  for (const format of ["html", "markdown"]) {
    replies.push({ body: `report-${format}` }); assert.equal(await api.plainReport(saved.reportInput, format), `report-${format}`);
    const request = requests.at(-1); assert.equal(request.url, `/api/reports/plain?format=${format}`);
    assert.deepEqual(JSON.parse(request.options.body), saved.reportInput);
  }
});
await checkAsync("Report API errors cannot masquerade as a document", async () => {
  replies = [{ ok: false, status: 500, body: "generation failed" }]; await assert.rejects(api.plainReport(saved.reportInput), /500.*generation failed/);
});
check("Existing API browser storage round-trips empty findings", () => {
  api.saveLast({ ...saved, findings: [] }); assert.equal(parseSavedRepository(api.loadLast()).findings.length, 0);
  storage.set("72hours:last-scan:v1", "{broken"); assert.equal(api.loadLast(), null);
});
console.log(`Verified ${checks} integration contracts. API transport uses local fixtures; no external repository scan was run.`);
