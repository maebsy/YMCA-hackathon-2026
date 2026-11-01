import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { test } from "node:test";
import ts from "typescript";

const require = createRequire(import.meta.url);
const element = (type, props) => ({ type, props: props ?? {} });
function nodes(tree) {
  if (!tree || typeof tree !== "object") return [];
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  return [tree, ...nodes(tree.props?.children)];
}
function mount(repository = { result: null, isScanning: false }) {
  const slots = [], listeners = new Map(), frames = [];
  let index = 0, pending = [], tree, pathname = "/", focus = 0;
  const desktop = { matches: false, addEventListener: (_type, fn) => listeners.set("resize", fn), removeEventListener: () => listeners.delete("resize") };
  const react = {
    useState(initial) {
      const slot = index++;
      slots[slot] ??= { value: initial };
      return [slots[slot].value, value => { slots[slot].value = value; }];
    },
    useRef(initial) { const slot = index++; return slots[slot] ??= { current: initial }; },
    useCallback(callback) { const slot = index++; return slots[slot] ??= callback; },
    useEffect(effect, deps) {
      const slot = index++, previous = slots[slot];
      if (!previous || deps.some((dep, i) => dep !== previous.deps[i])) pending.push(() => {
        previous?.cleanup?.(); slots[slot] = { deps, cleanup: effect() };
      });
    },
  };
  const loaded = { exports: {} };
  const source = ts.transpileModule(readFileSync(new URL("../src/components/shell.tsx", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(source, {
    module: loaded, exports: loaded.exports,
    require: name => ({ react, "react/jsx-runtime": { jsx: element, jsxs: element },
      "next/link": { default: "a" }, "next/navigation": { usePathname: () => pathname },
      "@/components/repository-provider": { useRepository: () => repository },
      "@/lib/repository-routes": { REPOSITORY_PROGRESS_PATH: "/repository", REPOSITORY_RESULT_PATH: "/report" },
    })[name] ?? require(name),
    document: { documentElement: { dataset: {} }, getElementById: () => ({ focus() {} }),
      addEventListener: (type, fn) => listeners.set(type, fn), removeEventListener: type => listeners.delete(type) },
    window: { matchMedia: () => desktop }, localStorage: { getItem: () => null },
    requestAnimationFrame: fn => { frames.push(fn); return frames.length; }, cancelAnimationFrame() {},
  });
  function render() {
    index = 0; pending = [];
    tree = nodes(loaded.exports.default({ children: null }));
    for (const node of tree.filter(node => node.props.ref)) node.props.ref.current = {
      contains: target => target === node.props.ref.current,
      getClientRects: () => desktop.matches && node.props.className?.includes("menu-toggle") ? [] : [{}],
      focus: () => { if (node.props.className?.includes("menu-toggle")) focus++; },
    };
    pending.forEach(effect => effect()); frames.splice(0).forEach(frame => frame());
  }
  render();
  return {
    render, button: () => tree.find(n => n.props.className === "icon-button menu-toggle"),
    panel: () => tree.find(n => n.props.id === "header-menu"),
    open() { this.button().props.onClick(); render(); }, focus: () => focus,
    dispatch: (type, event) => listeners.get(type)?.(event),
    route(path) { pathname = path; render(); render(); },
    widen() { desktop.matches = true; listeners.get("resize")?.(); render(); },
    tree: () => tree,
  };
}

test("header starts closed with a labelled disclosure and an always present mobile incident link", () => {
  const ui = mount();
  assert.equal(ui.button().props["aria-expanded"], false);
  assert.equal(ui.button().props["aria-label"], "메뉴 열기");
  assert.equal(ui.button().props["aria-controls"], ui.panel().props.id);
  assert.equal(ui.panel().props.hidden, true);
  assert.ok(ui.tree().some(n => n.props.className === "header-incident-link mobile-incident" && n.props.href === "/incident"));
  assert.equal(ui.tree().find(n => n.props.className === "header-incident-link mobile-incident").props.children[1], "사고 신고 72h");
  assert.equal(nodes(ui.panel()).find(n => n.props.href === "/incident").props.children, "사고 신고 72h");
  ui.open();
  assert.equal(ui.button().props["aria-label"], "메뉴 닫기");
  assert.equal(ui.panel().props.hidden, false);
});

test("Escape, outside click, link navigation, route changes and wide screens close and restore focus", () => {
  for (const reason of ["escape", "outside", "link", "route", "wide", "toggle"]) {
    const ui = mount(); ui.open();
    if (reason === "escape") ui.dispatch("keydown", { key: "Escape", preventDefault() {} });
    if (reason === "outside") ui.dispatch("pointerdown", { target: {}, preventDefault() {} });
    if (reason === "link") nodes(ui.panel()).find(n => n.props.href === "/help").props.onClick();
    if (reason === "route") ui.route("/incident");
    if (reason === "wide") ui.widen();
    if (reason === "toggle") ui.button().props.onClick();
    ui.render();
    assert.equal(ui.panel().props.hidden, true, reason);
    assert.equal(ui.focus(), reason === "wide" ? 0 : 1, reason);
  }
});

test("pointer events inside the menu or its button do not close it", () => {
  const ui = mount(); ui.open();
  for (const node of [ui.panel(), ui.button()]) {
    ui.dispatch("pointerdown", { target: node.props.ref.current }); ui.render();
    assert.equal(ui.panel().props.hidden, false);
  }
});

test("mobile inspection link follows empty, result and in-flight state", () => {
  for (const [state, href, label] of [
    [{ result: null, isScanning: false }, "/", "GitHub 실제 검사"],
    [{ result: {}, isScanning: false }, "/report", "검사 결과"],
    [{ result: {}, isScanning: true }, "/repository", "검사 진행"],
  ]) {
    const ui = mount(state);
    const link = nodes(ui.panel()).find(n => n.type === "a");
    assert.equal(link.props.href, href); assert.equal(link.props.children, label);
  }
});
