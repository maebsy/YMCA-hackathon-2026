import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
function mount(step = 0) {
  const slots = [], pending = [], calls = [];
  let cursor = 0;
  const incident = { step, assessment: {} };
  const target = { focus: options => calls.push(["focus", options]), scrollIntoView: options => calls.push(["scroll", options]) };
  const jsx = (type, props) => ({ type, props });
  const imports = {
    react: {
      useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
      useEffect(effect, deps) {
        const index = cursor++, previous = slots[index];
        if (!previous || deps.some((value, i) => value !== previous[i])) pending.push(effect);
        slots[index] = deps;
      },
    },
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "./incident-provider": { useIncident: () => incident },
    "./repository-provider": {}, "./ui/notice": {}, "./ui/clipboard": {}, "@/lib/incident": {},
  };
  const compiled = ts.transpileModule(readFileSync(new URL("../src/components/incident-workspace.tsx", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, require: name => imports[name] ?? require(name) });
  function render(nextStep = incident.step) {
    incident.step = nextStep; cursor = 0;
    const tree = loaded.exports.default();
    tree.props.children[1].props.ref.current = target;
    const effects = pending.splice(0); effects.forEach(effect => effect());
    return effects;
  }
  return { calls, render };
}

test("incident first mount and Strict Mode replay do not move focus or scroll", () => {
  for (const step of [0, 1]) {
    const page = mount(step);
    const effects = page.render();
    effects.forEach(effect => effect()); // React development setup replay with refs preserved.
    page.render(step);
    assert.deepEqual(page.calls, []);
  }
});

test("incident scrolls once per visible step change, including returning to facts", () => {
  const page = mount(); page.render();
  const effects = page.render(1);
  effects.forEach(effect => effect());
  assert.equal(page.calls.filter(([kind]) => kind === "scroll").length, 1);
  assert.equal(page.calls.filter(([kind]) => kind === "focus").length, 1);
  assert.equal(page.calls[0][1].preventScroll, true);
  assert.equal(page.calls[1][1].block, "start");
  page.render(1); page.render(2); // Both positive values render the same second step.
  assert.equal(page.calls.filter(([kind]) => kind === "scroll").length, 1);
  page.render(0);
  assert.equal(page.calls.filter(([kind]) => kind === "scroll").length, 2);
});
