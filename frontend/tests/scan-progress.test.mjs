import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
const element = (type, props) => ({ type, props: props ?? {} });
function nodes(tree) {
  if (!tree || typeof tree !== "object") return [];
  return Array.isArray(tree) ? tree.flatMap(nodes) : [tree, ...nodes(tree.props?.children)];
}
function load(relative, imports) {
  const compiled = ts.transpileModule(readFileSync(new URL(relative, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, require: name => imports[name] ?? require(name) });
  return loaded.exports;
}
function mount(mobile = false) {
  const slots = [];
  let cursor = 0, effects = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], update => { slots[index] = typeof update === "function" ? update(slots[index]) : update; }];
    },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useEffect: effect => effects.push(effect), useId: () => "test-logs", useSyncExternalStore: () => mobile,
  };
  const { default: ProgressH } = load("../src/components/progress/scan-progress.tsx", {
    react, "react/jsx-runtime": { jsx: element, jsxs: element },
  });
  return props => {
    cursor = 0; effects = [];
    const tree = nodes(ProgressH({ repo: "github.com/acme/app", phase: "running", logs: [], ...props }));
    return { tree, flush: () => effects.forEach(effect => effect()),
      viewport: tree.find(node => node.props.className === "ph-log-viewport") };
  };
}

test("H preserves the stage, outcome and console containers across phases and keeps only status live", () => {
  const render = mount();
  for (const phase of ["queued", "running", "explaining", "reporting", "done", "failed"]) {
    const { tree } = render({ phase, logs: ["[12:00:00] 엔진 상태: running"], counts: { total: 0, open: 0 },
      explained: { done: 3, total: 5 }, error: "상태 조회 실패", onRetry() {} });
    assert.equal(tree.filter(node => node.props.className === "ph-columns").length, 1);
    assert.equal(tree.filter(node => node.props.className === "ph-console").length, 1);
    assert.equal(tree.filter(node => node.props.className === "ph-outcome").length, 1);
    assert.equal(tree.filter(node => node.type === "li" && node.props.className?.startsWith("ph-step")).length, 4);
    assert.equal(tree.filter(node => node.props.role === "status").length, 1);
    assert.equal(tree.find(node => node.props.className === "ph-console-body").props["aria-live"], "off");
    assert.equal(tree.find(node => node.type === "button" && node.props.children === "재검사").props.disabled,
      ["queued", "running", "explaining", "reporting"].includes(phase));
    if (phase === "done") assert.equal(tree.filter(node => node.type === "strong" && node.props.children[0] === 0).length, 2);
    if (phase === "failed") assert.ok(tree.some(node => node.props.children === "상태 조회 실패"));
  }
});

test("H pauses the recent log window on upward scroll and latest resumes following", () => {
  const render = mount();
  const logs = Array.from({ length: 20 }, (_, index) => `[12:00:00] record ${index}`);
  let ui = render({ logs });
  const view = { scrollHeight: 1000, scrollTop: 0, clientHeight: 200 };
  ui.viewport.props.ref.current = view;
  ui.viewport.props.onScroll({ currentTarget: view });
  ui = render({ logs: [...logs, "[12:00:01] new record"] });
  assert.equal(ui.tree.filter(node => node.props.className === "ph-log-line").length, 8);
  assert.equal(ui.tree.some(node => node.props.children === "new record"), false, "reading older records must not move the visible window");
  ui.flush(); assert.equal(view.scrollTop, 0);
  ui.tree.find(node => node.type === "button" && node.props.children === "최신으로 ↓").props.onClick();
  ui = render({ logs: [...logs, "[12:00:01] new record"] }); ui.flush();
  assert.equal(view.scrollTop, 1000);
  assert.ok(ui.tree.some(node => node.props.children === "new record"));
});

test("H mobile starts with four records; full history and collapse do not remove the console shell", () => {
  const render = mount(true);
  const logs = Array.from({ length: 100 }, (_, index) => `[12:00:00] record ${index}`);
  let ui = render({ logs });
  assert.equal(ui.tree.filter(node => node.props.className === "ph-log-line").length, 4);
  ui.tree.find(node => node.type === "button" && node.props.children === "전체 보기").props.onClick();
  ui = render({ logs });
  assert.equal(ui.tree.filter(node => node.props.className === "ph-log-line").length, 100);
  ui.tree.find(node => node.type === "button" && node.props["aria-expanded"] === true).props.onClick();
  ui = render({ logs });
  assert.equal(ui.tree.find(node => node.props.className === "ph-console-body").props.hidden, true);
  assert.ok(ui.tree.some(node => node.props.className === "ph-console"));
});

test("H reporting spins the result stage and report failures offer rebuild and result-only navigation", () => {
  const render = mount();
  let ui = render({ phase: "reporting", onRetry() {}, logs: ["LLM · 해석 없음"] });
  const stages = ui.tree.filter(node => node.type === "li" && node.props.className?.startsWith("ph-step"));
  assert.equal(stages[3].props["aria-current"], "step"); assert.match(stages[3].props.className, /ph-step-current/);
  assert.ok(ui.tree.some(node => node.props.children === "건너뜀(연결 안 됨)"));
  let retries = 0;
  ui = render({ phase: "failed", reportFailed: true, error: "HTML failed", resultHref: "/report", onRetry: () => retries++ });
  ui.tree.find(node => node.type === "button" && node.props.children === "다시 만들기").props.onClick(); assert.equal(retries, 1);
  assert.ok(ui.tree.some(node => node.props.children === "결과만 보기" && node.props.href === "/report"));
});
