import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(relative, imports = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, URL,
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
