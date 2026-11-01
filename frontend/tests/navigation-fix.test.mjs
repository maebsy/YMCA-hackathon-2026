import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(file, imports, runtime = {}) {
  const source = readFileSync(new URL(file, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, URL, ...runtime,
    require: name => imports[name] ?? require(name) });
  return loaded.exports;
}
const jsx = (type, props) => ({ type, props: props ?? {} });
function text(tree) {
  if (tree == null || typeof tree === "boolean") return "";
  if (Array.isArray(tree)) return tree.map(text).join("");
  return typeof tree === "object" ? text(tree.props?.children) : String(tree);
}

test("legacy result routes wait for restoration, then replace with result or home", () => {
  for (const result of [null, {}]) {
    const effects = [], destinations = [];
    const state = { restored: false, result };
    const { default: Page } = load("../src/app/findings/page.tsx", {
      react: { useEffect: effect => effects.push(effect) },
      "react/jsx-runtime": { jsx, jsxs: jsx },
      "next/navigation": { useRouter: () => ({ replace: url => destinations.push(url) }) },
      "@/components/repository-provider": { useRepository: () => state },
      "@/lib/repository-routes": { REPOSITORY_RESULT_PATH: "/report" },
    });
    Page(); effects.splice(0).forEach(effect => effect());
    assert.deepEqual(destinations, [], "first render must not discard a saved result before restoration");
    state.restored = true;
    Page(); effects.splice(0).forEach(effect => effect());
    assert.deepEqual(destinations, [result ? "/report" : "/"]);
  }
  for (const [file, imported] of [["../src/app/repair/page.tsx", "../findings/page"], ["../src/app/repair/[id]/page.tsx", "../../findings/page"]]) {
    const destination = () => {};
    assert.equal(load(file, { [imported]: { default: destination } }).default, destination);
  }
});

test("progress guidance distinguishes completed, empty, failed and active scans", () => {
  const state = { phase: "idle", result: null, findings: [], logs: [], restored: true, resultRepo: "", repoInput: "", isScanning: false };
  const { default: Page } = load("../src/components/repository-workspace.tsx", {
    react: { useEffect() {}, useRef: () => ({ current: false }) },
    "react/jsx-runtime": { jsx, jsxs: jsx }, "next/link": { default: "a" },
    "next/navigation": { useRouter: () => ({ replace() {} }) },
    "@/components/repository-provider": { useRepository: () => state },
    "@/lib/repository-routes": { REPOSITORY_RESULT_PATH: "/report" },
    "@/components/progress/scan-progress": { default: "progress" }, "@/components/progress/scan-progress.css": {},
  });
  for (const phase of ["idle", "failed"]) {
    state.phase = phase;
    assert.ok(!text(Page()).includes("결과가 준비되면 자동"));
    assert.ok(!text(Page()).includes("검사가 끝났습니다."));
  }
  Object.assign(state, { phase: "done", result: {} });
  assert.ok(text(Page()).includes("검사가 끝났습니다. 결과 보기로 확인하세요."));
  Object.assign(state, { phase: "running", isScanning: true });
  assert.ok(text(Page()).includes("결과가 준비되면 자동으로 결과 화면으로 이동합니다."));
  assert.ok(!text(Page()).includes("검사가 끝났습니다."));
});

test("verify return link uses report for every real result including zero findings, and home otherwise", () => {
  let state = { result: null, restored: false };
  const { default: Return } = load("../src/app/verify/verify-return-link.tsx", {
    "react/jsx-runtime": { jsx, jsxs: jsx }, "next/link": { default: "a" },
    "@/components/repository-provider": { useRepository: () => state },
    "@/lib/repository-routes": { REPOSITORY_RESULT_PATH: "/report" },
  });
  assert.equal(Return().props.href, "/");
  assert.equal(text(Return()), "← 저장소 입력으로");
  state = { restored: true, result: { items: [] } };
  assert.equal(Return().props.href, "/report");
  assert.equal(text(Return()), "← 결과로 돌아가기");
  state = { restored: true, result: null };
  assert.equal(Return().props.href, "/");
});

test("verify run survives Strict Mode cleanup and uses router replacement without losing other URL parts", async () => {
  for (const mode of ["reference", "ai"]) {
    const effects = [], timers = new Map(), navigations = [], calls = [];
    let nextTimer = 0;
    const params = new URLSearchParams(`run=${mode}&source=report`);
    const { default: Panel } = load("../src/components/verify-panel.tsx", {
      react: { useEffect: effect => effects.push(effect), useRef: () => ({ current: 0 }), useState: value => [value, () => {}] },
      "react/jsx-runtime": { jsx, jsxs: jsx },
      "next/navigation": { useRouter: () => ({ replace: (...args) => navigations.push(args) }), useSearchParams: () => params },
      "@/lib/verify": { runVerify: async options => { calls.push(options.mode); return {}; } },
    }, { window: {
      location: { href: `http://localhost:3010/verify?run=${mode}&source=report#details` },
      setTimeout: callback => { const id = ++nextTimer; timers.set(id, callback); return id; },
      clearTimeout: id => timers.delete(id),
      history: { replaceState() { throw new Error("must not bypass the Next router"); } },
    } });
    Panel();
    const effect = effects[1];
    const cleanup = effect(); cleanup(); effect();
    assert.equal(timers.size, 1);
    for (const callback of timers.values()) callback();
    await Promise.resolve();
    assert.deepEqual(calls, [mode]);
    assert.equal(navigations[0][0], "/verify?source=report#details");
    assert.equal(navigations[0][1].scroll, false);
    params.delete("run"); effect();
    assert.equal(calls.length, 1, "consumed query must not restart on the cleaned URL");
  }
});
