import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(resolve(root, "package.json"));
const ts = require("typescript");
const repoA = "https://github.com/test-org/project-a";
const repoB = "https://github.com/test-org/project-b";

function loadSource(relative, imports = {}) {
  const compiled = ts.transpileModule(readFileSync(resolve(root, relative), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, URL, Date, Error, console,
    require: name => imports[name] ?? require(name) }, { filename: relative });
  return loaded.exports;
}
const realAPI = loadSource("src/lib/api.ts");
const { buildHandoff } = loadSource("src/lib/mcp.ts");
function deferred() {
  let resolvePromise, rejectPromise;
  const promise = new Promise((resolve, reject) => { resolvePromise = resolve; rejectPromise = reject; });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}
function item(id, status = "open") {
  return { id: `opengrep:${id}`, title: `Issue ${id}`, where: `src/file-${id}.ts:1`, severity: "high", status,
    kind: "code", what: `Observed issue ${id}`, rule_id: `rule-${id}`, fix_hint: { command: "review manually", text: "Inspect the evidence" } };
}
function result(repoUrl, items = []) {
  return { result: { target: { repo_url: repoUrl }, items }, report_scan: { id: `scan-${repoUrl.split("/").at(-1)}` },
    findings: items, llm_input: { items }, coverage: { opengrep: { engine: "Opengrep", status: "ok", count: items.length } } };
}

/**
 * Executes the real provider with persistent hook slots and explicit commit/effect
 * flushing. API promises are controlled at the existing adapter boundary. This
 * tests state orchestration; browser QA still owns DOM and React scheduling.
 */
function mountProvider({ saved = null, scan = async url => result(url), health = async () => false,
  explain = async () => [] } = {}) {
  const slots = [];
  let cursor = 0, dirty = true, mounted = true, view;
  let pendingEffects = [];
  const calls = { scans: [], health: 0, explanations: [], saved: [] };
  const api = { ...realAPI, now: () => "12:00:00", loadLast: () => saved,
    saveLast: data => calls.saved.push(structuredClone(data)),
    startScan: (url, previous, onStatus) => { calls.scans.push({ url, previous }); return scan(url, previous, onStatus); },
    llmHealthy: () => { calls.health++; return health(); },
    explain: (findings, os, hosting) => { calls.explanations.push({ findings, os, hosting }); return explain(findings, os, hosting); },
  };
  function nextSlot(kind, initialize) {
    const index = cursor++;
    if (!slots[index]) slots[index] = { kind, ...initialize() };
    assert.equal(slots[index].kind, kind, "Hook ordering changed");
    return slots[index];
  }
  const react = {
    createContext: () => ({ Provider: Symbol("Provider") }),
    useContext: () => { throw new Error("The provider test does not render consumers"); },
    useState(initial) {
      const slot = nextSlot("state", () => ({ value: typeof initial === "function" ? initial() : initial }));
      return [slot.value, update => {
        assert.ok(mounted, "Provider wrote state after unmount");
        const next = typeof update === "function" ? update(slot.value) : update;
        if (!Object.is(next, slot.value)) { slot.value = next; dirty = true; }
      }];
    },
    useRef(initial) { return nextSlot("ref", () => ({ ref: { current: initial } })).ref; },
    useEffect(effect, dependencies) {
      const slot = nextSlot("effect", () => ({ dependencies: undefined, cleanup: undefined }));
      if (!dependencies || !slot.dependencies || dependencies.some((value, index) => !Object.is(value, slot.dependencies[index]))) {
        slot.dependencies = dependencies;
        pendingEffects.push(() => { slot.cleanup?.(); slot.cleanup = effect(); });
      }
    },
  };
  const jsx = (type, props) => ({ type, props });
  const { RepositoryProvider } = loadSource("src/components/repository-provider.tsx", {
    react, "react/jsx-runtime": { jsx, jsxs: jsx }, "@/lib/api": api,
  });
  function flush() {
    let commits = 0;
    while (dirty) {
      assert.ok(commits++ < 30, "Provider did not settle after effect flushing");
      dirty = false; cursor = 0;
      view = RepositoryProvider({ children: null }).props.value;
      const effects = pendingEffects; pendingEffects = [];
      for (const effect of effects) effect();
    }
    return view;
  }
  flush();
  return { calls, flush, get value() { return view; },
    async run(url) { const running = view.runScan(url); flush(); await running; flush(); },
    async until(predicate) {
      for (let turn = 0; turn < 20; turn++) { await Promise.resolve(); flush(); if (predicate()) return; }
      assert.fail("Expected async provider phase was not reached");
    },
    unmount() { for (const slot of slots) if (slot.kind === "effect") slot.cleanup?.(); mounted = false; },
  };
}
let checks = 0;
async function check(name, callback) { await callback(); checks++; console.log(`PASS ${name}`); }

await check("Empty provider has no invented result and invalid input never reaches the engine", async () => {
  const provider = mountProvider();
  assert.equal(provider.value.restored, true); assert.equal(provider.value.result, null); assert.equal(provider.value.findings.length, 0);
  await provider.run("https://website.example");
  assert.equal(provider.calls.scans.length, 0); assert.ok(provider.value.error); assert.equal(provider.calls.saved.length, 0);
  provider.unmount();
});

await check("Pages input sends and displays the canonical repository throughout a scan", async () => {
  const provider = mountProvider();
  await provider.run("Alice.github.io/project/docs/");
  const expected = "https://github.com/alice/project";
  assert.equal(provider.calls.scans[0].url, expected);
  assert.equal(provider.value.repoInput, expected);
  assert.equal(provider.value.resultRepo, expected);
  assert.equal(provider.calls.saved.at(-1).repoUrl, expected);
  provider.unmount();
});

await check("In-flight duplicate requests are blocked and zero findings still publish and persist", async () => {
  const engine = deferred();
  const data = result(repoA);
  const provider = mountProvider({ scan: () => engine.promise });
  const first = provider.value.runScan(repoA);
  await provider.value.runScan(repoA);
  provider.flush();
  assert.equal(provider.calls.scans.length, 1); assert.equal(provider.value.isScanning, true); assert.equal(provider.value.result, null);
  engine.resolve(data); await first; provider.flush();
  assert.equal(provider.value.isScanning, false); assert.equal(provider.value.result, data.result); assert.equal(provider.value.resultRepo, repoA);
  assert.equal(provider.value.findings.length, 0); assert.ok(provider.value.reportInput); assert.equal(provider.calls.health, 0);
  assert.equal(provider.calls.saved.at(-1).verificationSource, "engine-status-v1"); assert.equal(provider.calls.saved.at(-1).findings.length, 0);
  provider.unmount();
});

await check("Rescans send only the same repository's previous engine result", async () => {
  const provider = mountProvider();
  await provider.run(repoA);
  const previous = provider.value.result;
  await provider.run(`${repoA}.git/`);
  await provider.run(repoB);
  assert.equal(provider.calls.scans[0].previous, null);
  assert.equal(provider.calls.scans[1].url, repoA); assert.equal(provider.calls.scans[1].previous, previous);
  assert.equal(provider.calls.scans[2].previous, null); assert.equal(provider.value.resultRepo, repoB);
  provider.unmount();
});

await check("Unavailable optional AI leaves raw engine findings and actual report input intact", async () => {
  const data = result(repoA, [item("one"), item("two")]);
  const provider = mountProvider({ scan: async () => data, health: async () => false });
  await provider.run(repoA);
  assert.equal(provider.value.result, data.result); assert.equal(provider.value.findings.length, 2); assert.equal(provider.value.isScanning, false);
  assert.equal(provider.value.reportInput.findings, data.findings); assert.equal(provider.value.reportInput.explain_results.length, 0);
  assert.equal(provider.calls.explanations.length, 0); assert.ok(provider.value.logs.some(log => log.type === "warn"));
  assert.equal(provider.calls.saved.at(-1).findings.length, 2); assert.equal(provider.value.error, "");
  provider.unmount();
});

await check("Rejected optional AI cannot erase successful engine results", async () => {
  const data = result(repoA, [item("one")]);
  const provider = mountProvider({ scan: async () => data, health: async () => true, explain: async () => { throw new Error("AI unavailable"); } });
  await provider.run(repoA);
  assert.equal(provider.value.result, data.result); assert.equal(provider.value.findings[0].id, "opengrep:one");
  assert.equal(provider.value.reportInput.findings, data.findings); assert.equal(provider.value.error, "");
  assert.equal(provider.value.isScanning, false); assert.ok(provider.value.logs.some(log => log.type === "warn"));
  assert.equal(provider.calls.saved.at(-1).findings.length, 1);
  provider.unmount();
});

await check("Delayed AI enrichment preserves selection/environment and keeps LLM_PARALLEL requests in flight (#91)", async () => {
  const ai = deferred();
  let inFlight = 0, peak = 0;
  const data = result(repoA, [item("resolved", "code_resolved"), ...Array.from({ length: 6 }, (_, index) => item(String(index)))]);
  const provider = mountProvider({ scan: async () => data, health: async () => true, explain: findings => {
    inFlight++; peak = Math.max(peak, inFlight);
    return (findings[0].id === "opengrep:0" ? ai.promise : Promise.resolve([])).finally(() => { inFlight--; });
  } });
  provider.value.setOS("linux"); provider.flush();
  provider.value.setHosting("netlify"); provider.flush();
  const running = provider.value.runScan(repoA); provider.flush();
  await provider.until(() => provider.calls.explanations.length >= 2);
  assert.equal(peak, realAPI.LLM_PARALLEL, "The second item must not wait for the slow first one");
  assert.equal(provider.value.isScanning, true); assert.equal(provider.value.findings.length, 7);
  provider.value.selectFinding("opengrep:1"); provider.flush();
  ai.resolve([{ fingerprint: "opengrep:0", status: "done", explanation: { summary: "Enriched explanation", red_verdict: "pass" } }]);
  await running; provider.flush();
  assert.equal(provider.value.selectedFindingId, "opengrep:1");
  assert.equal(provider.value.findings.find(finding => finding.id === "opengrep:0").title, "Enriched explanation");
  assert.equal(provider.value.findings.find(finding => finding.id === "opengrep:1").fixed, false);
  assert.equal(provider.value.findings.find(finding => finding.id === "opengrep:resolved").fixed, true);
  assert.equal(provider.calls.explanations[0].os, "linux"); assert.equal(provider.calls.explanations.length, 5);
  assert.equal(peak, realAPI.LLM_PARALLEL, "Never more than LLM_PARALLEL explanation requests at once");
  assert.ok(provider.calls.explanations.every(call => call.findings.length === 1));
  assert.equal(provider.calls.explanations[0].hosting, "netlify");
  assert.ok(provider.calls.explanations[0].findings.every(finding => finding.status !== "code_resolved"));
  provider.value.selectFinding("opengrep:3"); provider.flush(); await provider.run(repoA);
  assert.equal(provider.value.selectedFindingId, "opengrep:3", "Same-repository rescan should preserve a surviving selection");
  provider.unmount();
});

await check("A later failed AI item retains earlier explanations and continues the next item", async () => {
  const second = deferred();
  const first = { fingerprint: "opengrep:first", status: "done", explanation: { summary: "First complete" } };
  const provider = mountProvider({ scan: async () => result(repoA, [item("first"), item("second"), item("third")]),
    health: async () => true, explain: findings => findings[0].id === "opengrep:first" ? Promise.resolve([first])
      : findings[0].id === "opengrep:second" ? second.promise : Promise.resolve([]) });
  const running = provider.value.runScan(repoA); provider.flush();
  await provider.until(() => provider.value.findings[0]?.title === "First complete" && provider.calls.explanations.length === 3);
  assert.equal(provider.value.isScanning, true, "The slow second item must not block the third (#91)");
  assert.equal(provider.calls.saved.at(-1).reportInput.explain_results[0].fingerprint, first.fingerprint);
  second.reject(new Error("second timed out"));
  await running; provider.flush();
  assert.equal(provider.calls.explanations.length, 3);
  assert.equal(provider.value.reportInput.explain_results[0].fingerprint, first.fingerprint);
  assert.equal(provider.value.reportInput.explain_results[1].status, "failed");
  assert.equal(provider.value.findings[1].fixed, false);
  assert.equal(provider.value.findings[1].verdict, "LLM 해석 실패");
  assert.equal(provider.value.error, "");
  provider.unmount();
});

await check("Published and restored engine results retain the current MCP handoff contract", async () => {
  const data = result(repoA, [item("handoff")]);
  const revision = "a".repeat(40);
  data.result.target.commit_sha = revision;
  data.result.scanned_at = "2026-10-31T00:00:00Z";
  const explanation = { fingerprint: "opengrep:handoff", status: "done", explanation: {
    fingerprint: "opengrep:handoff", summary: "Review the observed input boundary", variant: "D", red_verdict: "pass",
    red_rounds: [{ verdict: "pass", issues: [] }], needs_manual_review: false, false_positive_suspect: false,
    ai_fix_prompt: "Review the observed boundary in src/file-handoff.ts before applying a fix.", model: "qa-fixture", prompt_version: "test",
  } };
  const provider = mountProvider({ scan: async () => data, health: async () => true, explain: async () => [explanation] });
  await provider.run(repoA);
  const saved = provider.calls.saved.at(-1);
  const handoff = buildHandoff(saved);
  assert.equal(handoff.ok, true); assert.equal(handoff.repository, "test-org/project-a");
  assert.equal(handoff.revision, revision); assert.equal(handoff.ready, 1); assert.equal(handoff.blocked.length, 0);
  assert.equal(handoff.snapshot.source.generated_at, data.result.scanned_at);
  assert.equal(handoff.snapshot.results[0].fingerprint, explanation.fingerprint);
  provider.unmount();
  const restored = mountProvider({ saved });
  assert.equal(restored.value.resultRepo, repoA); assert.equal(restored.calls.scans.length, 0);
  const restoredHandoff = buildHandoff({ result: restored.value.result, reportInput: restored.value.reportInput });
  assert.equal(restoredHandoff.ok, true); assert.equal(restoredHandoff.ready, 1);
  assert.equal(restoredHandoff.revision, revision);
  restored.unmount();
});

await check("Manual pending flags never change engine fixed state and are locked during a scan", async () => {
  const nextEngine = deferred();
  let scans = 0;
  const initial = result(repoA, [item("open"), item("resolved", "code_resolved")]);
  const provider = mountProvider({ scan: () => ++scans === 1 ? Promise.resolve(initial) : nextEngine.promise });
  await provider.run(repoA);
  provider.value.togglePending("opengrep:open"); provider.flush();
  assert.deepEqual([...provider.value.pendingIds], ["opengrep:open"]); assert.equal(provider.value.findings[0].fixed, false);
  provider.value.togglePending("opengrep:resolved"); provider.flush();
  assert.deepEqual([...provider.value.pendingIds], ["opengrep:open"]); assert.equal(provider.value.findings[1].fixed, true);
  const running = provider.value.runScan(repoA); provider.flush();
  provider.value.togglePending("opengrep:open"); provider.flush();
  assert.deepEqual([...provider.value.pendingIds], ["opengrep:open"]);
  nextEngine.resolve(result(repoA, [item("open", "code_resolved")])); await running; provider.flush();
  assert.equal(provider.value.pendingIds.length, 0); assert.equal(provider.value.findings[0].fixed, true);
  assert.equal(provider.calls.saved.at(-1).verificationSource, "engine-status-v1");
  provider.unmount();
});

await check("A failed next-repository scan retains the previous result's identity and report", async () => {
  const successful = result(repoA, [item("existing")]);
  const provider = mountProvider({ scan: async url => { if (url === repoB) throw new Error("Clone failed"); return successful; } });
  await provider.run(repoA);
  const reportInput = provider.value.reportInput;
  await provider.run(repoB);
  assert.equal(provider.value.repoInput, repoB); assert.equal(provider.value.resultRepo, repoA);
  assert.equal(provider.value.result, successful.result); assert.equal(provider.value.reportInput, reportInput);
  assert.equal(provider.value.findings[0].id, "opengrep:existing"); assert.equal(provider.value.isScanning, false); assert.ok(provider.value.error);
  assert.equal(provider.calls.saved.at(-1).repoUrl, repoA);
  provider.unmount();
});

await check("Malformed engine response cannot replace an earlier valid result", async () => {
  let scans = 0;
  const successful = result(repoA);
  const provider = mountProvider({ scan: async () => ++scans === 1 ? successful : { llm_input: { items: [] } } });
  await provider.run(repoA); await provider.run(repoB);
  assert.equal(provider.value.resultRepo, repoA); assert.equal(provider.value.result, successful.result); assert.ok(provider.value.error);
  assert.equal(provider.calls.saved.at(-1).repoUrl, repoA);
  provider.unmount();
});

await check("Hydration restores a saved zero-finding result without sending a scan", async () => {
  const saved = { verificationSource: "engine-status-v1", repoUrl: repoA, findings: [], result: result(repoA).result,
    reportInput: { scan: { id: "saved" }, findings: [], explain_results: [] }, logs: [], pendingIds: [] };
  const provider = mountProvider({ saved });
  assert.equal(provider.value.restored, true); assert.equal(provider.value.resultRepo, repoA); assert.ok(provider.value.result);
  assert.equal(provider.value.findings.length, 0); assert.equal(provider.calls.scans.length, 0); assert.equal(provider.calls.saved.length, 0);
  provider.unmount();
});

await check("A late engine result after provider unmount cannot publish or persist", async () => {
  const engine = deferred();
  const provider = mountProvider({ scan: () => engine.promise });
  const running = provider.value.runScan(repoA); provider.flush();
  provider.unmount(); engine.resolve(result(repoA, [item("late")])); await running;
  assert.equal(provider.calls.saved.length, 0); assert.equal(provider.calls.health, 0);
});

console.log(`Verified ${checks} real provider orchestration scenarios with controlled hook commits and API fixtures. No browser or external repository scan was used.`);
