import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(relative, imports = {}, runtime = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, URL, ...runtime,
    require: name => imports[name] ?? require(name) }, { filename: relative });
  return loaded.exports;
}
const { normalizeRepositoryUrl } = load("../src/components/repository-provider.tsx", { "@/lib/api": {} });
const element = (type, props) => ({ type, props: props ?? {} });
function nodes(tree) {
  if (!tree || typeof tree !== "object") return [];
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  return [tree, ...nodes(tree.props?.children)];
}
function simpleShell(stored = null, blocked = false) {
  const storage = new Map(stored === null ? [] : [["72hours-simple", stored]]);
  const document = { documentElement: { dataset: {} } };
  const localStorage = {
    getItem(key) { if (blocked) throw new Error("Storage blocked"); return storage.get(key) ?? null; },
    setItem(key, value) { if (blocked) throw new Error("Storage blocked"); storage.set(key, value); },
  };
  const runtime = { document, localStorage, window: new EventTarget(), Event };
  const jsx = { jsx: element, jsxs: element };
  const { default: Layout } = load("../src/app/layout.tsx", {
    "react/jsx-runtime": jsx, "@/components/incident-provider": {}, "@/components/repository-provider": {},
    "@/components/shell": {}, "./globals.css": {}, "./flow.css": {}, "./incident.css": {},
  });
  const layout = nodes(Layout({ children: null }));
  const head = layout.find(node => node.type === "head");
  const script = nodes(head).find(node => node.type === "script");
  // The head script runs before the body can display marked elements.
  vm.runInNewContext(script.props.dangerouslySetInnerHTML.__html, runtime);
  let subscriptions = 0;
  const cleanups = [];
  const { default: Shell } = load("../src/components/shell.tsx", {
    react: { useEffect() {}, useSyncExternalStore(subscribe, read, serverRead) {
      assert.equal(serverRead(), false);
      cleanups.push(subscribe(() => subscriptions++));
      return read();
    } },
    "react/jsx-runtime": jsx, "next/link": { default: "a" },
    "next/navigation": { usePathname: () => "/" },
  }, runtime);
  return { document, storage, render: () => nodes(Shell({ children: null })),
    notifications: () => subscriptions, cleanup: () => cleanups.forEach(fn => fn()) };
}
test("Simple toggles immediately after theme, persists and restores before body display", () => {
  const ui = simpleShell();
  assert.equal(ui.document.documentElement.dataset.simple, "off");
  const tree = ui.render();
  const buttons = tree.filter(node => node.type === "button");
  assert.match(buttons.at(-2).props.className, /theme-toggle/);
  const simple = buttons.at(-1);
  assert.equal(simple.props.children, "Simple");
  assert.equal(simple.props["aria-pressed"], false);
  simple.props.onClick();
  assert.equal(ui.document.documentElement.dataset.simple, "on");
  assert.equal(ui.storage.get("72hours-simple"), "on");
  assert.equal(ui.notifications(), 1);
  assert.equal(ui.render().find(node => node.props.children === "Simple").props["aria-pressed"], true);
  const restored = simpleShell(ui.storage.get("72hours-simple"));
  assert.equal(restored.document.documentElement.dataset.simple, "on");
  const restoredButton = restored.render().find(node => node.props.children === "Simple");
  assert.equal(restoredButton.props["aria-pressed"], true);
  restoredButton.props.onClick();
  assert.equal(restored.document.documentElement.dataset.simple, "off");
  assert.equal(restored.storage.get("72hours-simple"), "off");
  ui.cleanup(); restored.cleanup();
});
test("Simple defaults off for invalid preferences and works when storage is blocked", () => {
  for (const stored of [null, "off", "invalid"]) {
    const ui = simpleShell(stored);
    assert.equal(ui.document.documentElement.dataset.simple, "off");
    ui.cleanup();
  }
  const ui = simpleShell("on", true);
  const button = ui.render().find(node => node.props.children === "Simple");
  assert.equal(button.props["aria-pressed"], false);
  button.props.onClick();
  assert.equal(ui.document.documentElement.dataset.simple, "on");
  assert.equal(ui.notifications(), 1);
  ui.cleanup();
});
function entry(overrides = {}) {
  const calls = [], navigation = [], errors = [];
  let focusCount = 0;
  const repository = { repoInput: "https://github.com/acme/app.git/", restored: true, isScanning: false,
    setRepoInput: value => { repository.repoInput = value; },
    runScan: value => { calls.push(value); return Promise.resolve(); }, ...overrides };
  const { default: Home } = load("../src/app/page.tsx", {
    react: { useState: () => ["", value => errors.push(value)], useRef: () => ({ current: { focus: () => focusCount++ } }) },
    "react/jsx-runtime": { jsx: element, jsxs: element },
    "next/link": { default: "a" },
    "next/navigation": { useRouter: () => ({ push: path => navigation.push(path) }) },
    "@/components/repository-provider": { useRepository: () => repository, normalizeRepositoryUrl },
  });
  const tree = nodes(Home());
  const form = tree.find(node => node.type === "form");
  const submit = () => form.props.onSubmit({ preventDefault() {} });
  return { calls, navigation, errors, tree, submit, focused: () => focusCount };
}

test("home submit starts the actual scan once with the normalized explicit URL", () => {
  const ui = entry();
  assert.equal(ui.calls.length, 0, "render must never auto-start scans");
  ui.submit();
  assert.deepEqual(ui.calls, ["https://github.com/acme/app"]);
  assert.deepEqual(ui.navigation, ["/repository"]);
});
test("home submit prepends https:// when github.com URL is entered without scheme", () => {
  const ui = entry({ repoInput: "github.com/papawolf42/kdfakdff" });
  ui.submit();
  assert.deepEqual(ui.calls, ["https://github.com/papawolf42/kdfakdff"]);
  assert.deepEqual(ui.navigation, ["/repository"]);
});
test("GitHub Pages user and project sites normalize to repository roots", () => {
  for (const [input, expected] of [
    ["alice.github.io", "https://github.com/alice/alice.github.io"],
    ["https://alice.github.io/", "https://github.com/alice/alice.github.io"],
    [" ALIce.GitHub.IO/ ", "https://github.com/alice/alice.github.io"],
    ["HTTPS://ALIce.GitHub.IO", "https://github.com/alice/alice.github.io"],
    ["alice.github.io/My-Repo", "https://github.com/alice/My-Repo"],
    ["https://alice.github.io/My-Repo/", "https://github.com/alice/My-Repo"],
    ["Alice.GITHUB.IO/My-Repo/docs/start.html", "https://github.com/alice/My-Repo"],
    ["https://alice.github.io/My-Repo/docs/", "https://github.com/alice/My-Repo"],
    ["a-b.github.io/repo.git/", "https://github.com/a-b/repo"],
    [`${"a".repeat(39)}.github.io`, `https://github.com/${"a".repeat(39)}/${"a".repeat(39)}.github.io`],
  ]) assert.equal(normalizeRepositoryUrl(input), expected, input);
});
test("GitHub Pages rejects invalid owners, spoofed domains and ambiguous URLs", () => {
  for (const input of [
    "github.io", "https://github.io/", "-alice.github.io", "alice-.github.io", "a--b.github.io",
    "a_b.github.io", "a.b.github.io", `${"a".repeat(40)}.github.io`, "https://example.com/repo",
    "alice.github.io.evil.com/repo", "https://alice.github.io.evil.com/repo", "https://alice.github.io./repo",
    "http://alice.github.io/repo", "https://user:pass@alice.github.io/repo", "https://alice.github.io:443/repo",
    "https://alice.github.io/repo?token=x", "https://alice.github.io/repo#fragment", "https://alice.github.io/repo%2Fother",
    "https://alice.github.io/repo\\other", "alice.github.io//repo", "alice.github.io/./repo", "alice.github.io/../repo",
    "alice.github.io/.git", `alice.github.io/${"a".repeat(101)}`,
  ]) assert.equal(normalizeRepositoryUrl(input), null, input);
});
test("home sends a Pages site's repository URL and shows both supported input formats", () => {
  const ui = entry({ repoInput: "Alice.github.io/project/docs/" });
  ui.submit();
  assert.deepEqual(ui.calls, ["https://github.com/alice/project"]);
  assert.deepEqual(ui.navigation, ["/repository"]);
  const input = ui.tree.find(node => node.type === "input");
  assert.equal(input.props.placeholder, "github.com/owner/repository");
  assert.equal(input.props["aria-describedby"], "repository-hint");
  const hint = ui.tree.find(node => node.props.id === "repository-hint");
  assert.equal(hint.props.children[0], "github.com/owner/repository 또는 owner.github.io를 입력하세요.");
  assert.equal(hint.props.children[1].type, "br");
  assert.equal(hint.props.children[2], "GitHub Pages는 해당 저장소로 변환해 검사합니다.");
  assert.equal(ui.tree.some(node => node.type === "span" && node.props.children === "실제 엔진 검사"), false);
});
test("website and malformed repository inputs stay on the form without engine requests", () => {
  for (const repoInput of ["", "https://example.com", "https://github.com/acme/app/tree/main", "https://github.com/acme/app?token=x"]) {
    const ui = entry({ repoInput }); ui.submit();
    assert.equal(ui.calls.length, 0); assert.equal(ui.navigation.length, 0);
    assert.ok(ui.errors.some(Boolean)); assert.equal(ui.focused(), 1);
  }
});
test("Simple hides the three home links and the whole benefits layout without hiding the form", () => {
  const ui = entry();
  const marked = ui.tree.filter(node => node.props["data-simple-hide"] === true);
  assert.equal(marked.length, 4);
  const links = marked.flatMap(nodes).filter(node => node.props.href).map(node => node.props.href);
  assert.deepEqual(links, ["/repository", "/incident", "/verify"]);
  const benefits = marked.find(node => node.props.className === "entry-benefits");
  assert.deepEqual(nodes(benefits).filter(node => node.type === "h2").map(node => node.props.children),
    ["엔진으로 발견", "GPU로 해석", "MCP로 전달"]);
  assert.equal(marked.some(node => nodes(node).some(child => child.type === "form")), false);
});
test("restoration and in-flight scans block home submissions", () => {
  for (const state of [{ restored: false }, { isScanning: true }]) {
    const ui = entry(state); ui.submit();
    assert.equal(ui.calls.length, 0); assert.equal(ui.navigation.length, 0);
    assert.equal(ui.tree.find(node => node.type === "button" && node.props.type === "submit").props.disabled, true);
  }
});
test("former sample routes lead to the actual workspace without starting a scan", () => {
  for (const path of ["scan", "findings", "repair", "repair/[id]", "report"]) {
    const redirects = [];
    const { default: Page } = load(`../src/app/${path}/page.tsx`, {
      "next/navigation": { redirect: destination => redirects.push(destination) },
    });
    Page();
    assert.deepEqual(redirects, ["/repository"], path);
  }
});
