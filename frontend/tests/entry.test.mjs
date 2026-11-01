import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);
const reportPresentation = load("../src/lib/report-document.ts");
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
const { normalizeRepositoryUrl, detectBrowserOS } = load("../src/components/repository-provider.tsx", { "@/lib/api": {} });
test("display OS prefers client hints, falls back to user agent, then Windows", () => {
  for (const [browser, expected] of [
    [{ userAgentData: { platform: "Windows" }, userAgent: "Macintosh" }, "windows"],
    [{ userAgentData: { platform: "macOS" }, userAgent: "Windows NT" }, "macos"],
    [{ userAgentData: { platform: "Linux" } }, "linux"],
    [{ userAgentData: { platform: "Unknown" }, userAgent: "Macintosh; Intel Mac OS X" }, "macos"],
    [{ userAgent: "Mozilla/5.0 (X11; Linux x86_64)" }, "linux"],
    [{ userAgent: "Mozilla/5.0 (Windows NT 10.0)" }, "windows"],
    [{ userAgent: "Unknown" }, "windows"], [{}, "windows"], [undefined, "windows"],
  ]) assert.equal(detectBrowserOS(browser), expected);
});
const element = (type, props) => ({ type, props: props ?? {} });
function nodes(tree) {
  if (!tree || typeof tree !== "object") return [];
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  return [tree, ...nodes(tree.props?.children)];
}
function entry(overrides = {}) {
  const calls = [], navigation = [], errors = [], events = [];
  let focusCount = 0;
  const repository = { repoInput: "https://github.com/acme/app.git/", restored: true, isScanning: false,
    setRepoInput: value => { repository.repoInput = value; },
    runScan: value => { calls.push(value); events.push("scan"); return Promise.resolve(); }, ...overrides };
  const { default: Home } = load("../src/app/page.tsx", {
    react: { useState: () => ["", value => errors.push(value)], useRef: () => ({ current: { focus: () => focusCount++ } }), useSyncExternalStore: (_subscribe, _client, server) => server() },
    "react/jsx-runtime": { jsx: element, jsxs: element },
    "next/link": { default: "a" },
    "next/navigation": { useRouter: () => ({ push: path => { navigation.push(path); events.push("navigate"); } }) },
    "@/components/repository-provider": { useRepository: () => repository, normalizeRepositoryUrl },
    "@/lib/repo-suggest": load("../src/lib/repo-suggest.ts"),
    "./repo-suggest.css": {}, "@/components/mcp-connect": { default: "mcp-connect" },
    "@/lib/use-repo-autocomplete": { useRepoAutocomplete: ({ value, setValue }) => ({
      inputProps: { value, role: "combobox", "aria-autocomplete": "both", "aria-expanded": true, "aria-controls": "repo-options", onChange: event => setValue(event.currentTarget.value) },
      listProps: { role: "listbox", id: "repo-options" }, suggestions: ["function-face"],
      optionId: index => `repo-option-${index}`, activeIndex: 0, partial: "f", open: true, loading: false, select() {},
      announcement: "후보 1개",
    }) },
  });
  const tree = nodes(Home());
  const form = tree.find(node => node.type === "form");
  const submit = () => form.props.onSubmit({ preventDefault() {} });
  return { calls, navigation, errors, events, tree, submit, focused: () => focusCount };
}

function repositoryView(overrides = {}) {
  const repository = { repoInput: "", resultRepo: "", result: null, findings: [], pendingIds: [], logs: [],
    restored: true, isScanning: false, error: "", message: "", os: "windows", phase: "idle", ...overrides };
  const { default: RepositoryWorkspace } = load("../src/components/repository-workspace.tsx", {
    react: { useEffect() {}, useRef: () => ({ current: false }) }, "react/jsx-runtime": { jsx: element, jsxs: element },
    "next/link": { default: "a" }, "@/components/tabs/WorkspaceTab": { WorkspaceTab: "workspace-tab" },
    "next/navigation": { useRouter: () => ({ replace() {} }) },
    "@/lib/repository-routes": { REPOSITORY_RESULT_PATH: "/report" },
    "@/components/progress/scan-progress": { default: "progress-h" }, "@/components/progress/scan-progress.css": {},
    "@/components/repository-provider": { useRepository: () => repository, normalizeRepositoryUrl },
    "@/components/ui/notice": { Notice: "notice" }, "@/components/ui/clipboard": {}, "@/lib/api": {},
  });
  return nodes(RepositoryWorkspace());
}

test("repository has no environment selectors and detail OS tabs drive commands and MCP paths", () => {
  const tree = repositoryView();
  assert.equal(tree.some(node => node.type === "fieldset"), false);
  const { WorkspaceTab } = load("../src/components/tabs/WorkspaceTab.tsx", {
    react: { useState: () => [false, () => {}] }, "react/jsx-runtime": { jsx: element, jsxs: element },
    "@/components/McpHandoff": { McpHandoff: "mcp-handoff" }, "next/link": { default: "a" },
  });
  const { clientConfig } = load("../src/lib/mcp.ts");
  for (const [os, path] of [["windows", "C:/Users/"], ["macos", "/Users/"], ["linux", "/home/"]]) {
    const selection = [];
    const detail = nodes(WorkspaceTab({ compact: true, findings: [{ id: "one", commands: {
      windows: "windows-command", macos: "macos-command", linux: "linux-command" }, why: [] }],
      logs: [], os, onChangeOS: value => selection.push(value) }));
    for (const [label, value] of [["Windows", "windows"], ["macOS", "macos"], ["Linux", "linux"]]) {
      detail.find(node => node.type === "button" && node.props.children === label).props.onClick();
      assert.equal(selection.at(-1), value);
    }
    assert.ok(detail.some(node => node.type === "pre" && node.props.children === `${os}-command`));
    assert.equal(detail.find(node => node.type === "mcp-handoff").props.os, os);
    const config = JSON.parse(clientConfig({ fileName: "scan.json", repository: "acme/app" }, os));
    assert.ok(config.mcpServers["72hours-handoff"].args[2].startsWith(path));
  }
});

test("the verify shortcut is an in-app link so a running interpretation is not cut off", () => {
  // 페이지를 통째로 다시 열면 결과 화면에서 이어 돌던 언어모델 해석이 끊깁니다 (#144 후속)
  const LinkStub = "next-link";
  const { WorkspaceTab } = load("../src/components/tabs/WorkspaceTab.tsx", {
    react: { useState: () => [false, () => {}] }, "react/jsx-runtime": { jsx: element, jsxs: element },
    "@/components/McpHandoff": { McpHandoff: "mcp-handoff" }, "next/link": { default: LinkStub },
  });
  const finding = cwe => ({ id: "one", commands: { windows: "", macos: "", linux: "" }, why: [], cwe, fixed: false });
  const sqli = nodes(WorkspaceTab({ compact: true, findings: [finding("CWE-89")], logs: [], os: "windows", onChangeOS() {} }));
  const link = sqli.find(node => node.props.href === "/verify?run=reference");
  assert.equal(link?.type, LinkStub);
  const secret = nodes(WorkspaceTab({ compact: true, findings: [finding("CWE-798")], logs: [], os: "windows", onChangeOS() {} }));
  assert.equal(secret.some(node => node.props.href === "/verify?run=reference"), false);
});

test("home submit starts the actual scan once with the normalized explicit URL", () => {
  const ui = entry();
  assert.equal(ui.calls.length, 0, "render must never auto-start scans");
  ui.submit();
  assert.deepEqual(ui.calls, ["https://github.com/acme/app"]);
  assert.deepEqual(ui.navigation, ["/repository"]);
  assert.deepEqual(ui.events, ["scan", "navigate"]);
});

test("home wires inline suggestions and submits the controlled completed URL", () => {
  const ui = entry({ repoInput: "github.com/alice/f" });
  const input = ui.tree.find(node => node.type === "input" && node.props.id === "repository");
  assert.equal(input.props.value, "github.com/alice/f");
  assert.equal(input.props["aria-autocomplete"], "both");
  assert.equal(input.props.role, "combobox");
  assert.equal(ui.tree.find(node => node.props.role === "listbox").props.id, input.props["aria-controls"]);
  assert.equal(ui.tree.find(node => node.props.role === "option").props["aria-selected"], true);
  const live = ui.tree.find(node => node.props["aria-live"] === "polite");
  assert.equal(live.props.className, "sr-only");
  assert.equal(live.props.children, "후보 1개");
  input.props.onChange({ currentTarget: { value: "github.com/alice/function-face" } });
  ui.submit();
  assert.deepEqual(ui.calls, ["https://github.com/alice/function-face"]);
  assert.deepEqual(ui.events, ["scan", "navigate"]);
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
  assert.equal(input.props.placeholder, "owner/repository");
  assert.equal(input.props["aria-describedby"], "repository-hint");
  const hint = ui.tree.find(node => node.props.id === "repository-hint");
  assert.equal(hint.props.children, "github.com/owner/repo 또는 owner.github.io");
  assert.equal(ui.tree.some(node => node.type === "span" && node.props.children === "실제 엔진 검사"), false);
});
test("website and malformed repository inputs stay on the form without engine requests", () => {
  for (const repoInput of ["", "https://example.com", "https://github.com/acme/app/tree/main", "https://github.com/acme/app?token=x"]) {
    const ui = entry({ repoInput }); ui.submit();
    assert.equal(ui.calls.length, 0); assert.equal(ui.navigation.length, 0);
    assert.ok(ui.errors.some(Boolean)); assert.equal(ui.focused(), 1);
  }
});
test("restoration blocks home submissions", () => {
  const ui = entry({ restored: false }); ui.submit();
  assert.equal(ui.calls.length, 0); assert.equal(ui.navigation.length, 0);
  assert.equal(ui.tree.find(node => node.type === "button" && node.props.type === "submit").props.disabled, true);
});
test("home returns to the in-flight scan without validation or starting another request", () => {
  const ui = entry({ isScanning: true, repoInput: "" }); ui.submit();
  assert.equal(ui.calls.length, 0);
  assert.deepEqual(ui.navigation, ["/repository"]);
  assert.equal(ui.errors.length, 0);
  assert.equal(ui.tree.find(node => node.type === "button" && node.props.type === "submit").props.disabled, false);
});
test("repository has no duplicate input, shows the active URL and preserves the rescan callback", () => {
  const current = "https://github.com/alice/project", previous = "https://github.com/acme/old";
  const calls = [];
  for (const state of [{}, { phase: "running", isScanning: true, repoInput: current }, { phase: "done", result: {}, resultRepo: previous },
    { phase: "running", isScanning: true, repoInput: current, result: {}, resultRepo: previous }]) {
    const tree = repositoryView({ ...state, runScan: url => calls.push(url) });
    assert.equal(tree.some(node => ["input", "form", "fieldset"].includes(node.type)), false);
    assert.equal(calls.length, 0, "render never starts a scan");
    const progress = tree.find(node => node.type === "progress-h");
    assert.equal(!!progress, !!state.phase);
    if (progress) assert.equal(progress.props.repo, (state.isScanning ? current : previous).replace("https://", ""));
    if (state.isScanning) assert.equal(progress.props.counts, undefined, "old result counts must not label a new scan");
    assert.equal(tree.some(node => node.type === "workspace-tab"), false, "details belong on /report");
    assert.equal(tree.some(node => node.props.className === "result-context"), false);
    if (!state.result && !state.isScanning) assert.ok(tree.some(node => node.props.href === "/"));
  }
  const tree = repositoryView({ phase: "done", result: {}, resultRepo: current, runScan: url => calls.push(url) });
  tree.find(node => node.type === "progress-h").props.onRetry();
  assert.deepEqual(calls, [current]);
});
test("empty repository directs to home and failed scans still show their error", () => {
  const empty = repositoryView();
  assert.ok(empty.some(node => node.type === "p" && Array.isArray(node.props.children)
    && node.props.children[0] === "홈에서 검사할 GitHub 주소를 입력하세요. "));
  const failed = repositoryView({ error: "검사 요청 실패" });
  assert.equal(failed.find(node => node.props.role === "alert").props.children, "검사 요청 실패");
});

test("H receives current progress, records and retry identity while compact legacy logs stay hidden", () => {
  const calls = [];
  const current = "https://github.com/acme/new", previous = "https://github.com/acme/old";
  const failed = repositoryView({ phase: "failed", repoInput: current, resultRepo: previous, result: {}, error: "Clone failed",
    startedAt: 100, logs: [{ time: "12:00:00", step: "error", msg: "Clone failed", status: "실패" }], runScan: url => calls.push(url) });
  const progress = failed.find(node => node.type === "progress-h");
  assert.equal(progress.props.phase, "failed"); assert.equal(progress.props.startedAt, 100);
  assert.equal(progress.props.error, "Clone failed"); assert.equal(progress.props.counts, undefined);
  assert.deepEqual(Array.from(progress.props.logs), ["[12:00:00] error · Clone failed · 실패"]);
  progress.props.onRetry(); assert.deepEqual(calls, [current]);
  const enriching = repositoryView({ phase: "explaining", isScanning: true, repoInput: current, resultRepo: current, result: {},
    findings: [{ fixed: true }, { fixed: false }], pendingIds: ["manual"], explained: { done: 1, total: 2 }, message: "추가 해석 1/2건 처리." });
  const enrichment = enriching.find(node => node.type === "progress-h");
  assert.equal(enrichment.props.counts.total, 2); assert.equal(enrichment.props.counts.open, 1);
  assert.equal(enrichment.props.explained.done, 1);
  assert.equal(enriching.some(node => node.props.className === "feedback"), false);
  const { WorkspaceTab } = load("../src/components/tabs/WorkspaceTab.tsx", {
    react: { useState: () => [false, () => {}] }, "react/jsx-runtime": { jsx: element, jsxs: element },
    "@/components/McpHandoff": { McpHandoff: "mcp-handoff" }, "next/link": { default: "a" },
  });
  const compact = nodes(WorkspaceTab({ compact: true, findings: [], logs: [], pendingIds: [] }));
  assert.equal(compact.some(node => node.props.children === "⑤ 재검사 실행"), false);
});
test("former sample routes lead to the actual workspace without starting a scan", () => {
  for (const path of ["scan", "findings", "repair", "repair/[id]"]) {
    const redirects = [];
    const { default: Page } = load(`../src/app/${path}/page.tsx`, {
      "next/navigation": { redirect: destination => redirects.push(destination) },
    });
    Page();
    assert.deepEqual(redirects, ["/repository"], path);
  }
});

function resultView(overrides = {}, reportOnly = false, runtime = {}) {
  const repository = { repoInput: "https://github.com/acme/new", resultRepo: "https://github.com/acme/app", result: {}, findings: [], pendingIds: [], logs: [], restored: true, isScanning: false,
    message: "", reportInput: {}, reportHtml: "<html>Prepared document</html>", reportMarkdown: "# Prepared MD", reportError: "", prepareReport() {}, ...overrides };
  const effects = [], navigation = [];
  const { default: Result, RepositoryReport } = load("../src/components/repository-result.tsx", {
    react: { useEffect: effect => effects.push(effect), useRef: () => ({ current: 0 }), useState: () => ["", () => {}] },
    "react/jsx-runtime": { jsx: element, jsxs: element }, "next/link": { default: "a" },
    "next/navigation": { useRouter: () => ({ push: path => navigation.push(path) }) },
    "@/lib/repository-routes": { REPOSITORY_PROGRESS_PATH: "/repository" }, "./repository-result.css": {},
    "@/lib/report-document": reportPresentation,
    "@/components/report-scorecard": { default: "report-scorecard" },
    "@/lib/report-scorecard": load("../src/lib/report-scorecard.ts"),
    "@/components/repository-provider": { useRepository: () => repository },
    "@/components/tabs/WorkspaceTab": { WorkspaceTab: "workspace-tab" }, "@/components/ui/notice": { Notice: "notice" },
  }, runtime);
  return { tree: nodes(reportOnly ? RepositoryReport() : Result()), effects, navigation, Report: RepositoryReport };
}

test("/report renders results, details and routes a same-repository rescan to progress", () => {
  const calls = [];
  const ui = resultView({ runScan: url => calls.push(url) });
  assert.equal(ui.tree.some(node => ["result-context", "feedback"].includes(node.props.className)), false);
  assert.equal(ui.tree.some(node => node.type === "notice"), false);
  assert.equal(ui.tree.find(node => node.type === "main").props.children[0], ui.tree.find(node => node.type === "report-scorecard"));
  assert.ok(ui.tree.some(node => node.props.className === "count-grid"), "manual pending counts are absent in the document");
  assert.ok(ui.tree.some(node => node.type === "workspace-tab"));
  assert.equal(ui.tree.some(node => node.type === "progress-h"), false);
  ui.tree.find(node => node.type === "button" && node.props.children === "재검사").props.onClick();
  assert.deepEqual(calls, ["https://github.com/acme/app"]); assert.deepEqual(ui.navigation, ["/repository"]);
  const busy = resultView({ isScanning: true });
  assert.equal(busy.tree.find(node => node.type === "button" && node.props.children === "재검사").props.disabled, true);
  const empty = resultView({ result: null }); assert.ok(empty.tree.some(node => node.props.href === "/"));
  const { default: Page } = load("../src/app/report/page.tsx", { "react/jsx-runtime": { jsx: element }, "@/components/repository-result": { default: "result-page" } });
  assert.equal(Page().type, "result-page");
});

test("report is visible immediately with two small MD actions using the prepared document", () => {
  const writes = []; let fetches = 0, generates = 0;
  const ui = resultView({ prepareReport: () => generates++ }, true, {
    navigator: { clipboard: { writeText: text => { writes.push(text); return Promise.resolve(); } } },
    fetch() { fetches++; throw new Error("no click fetch"); },
  });
  ui.effects.forEach(effect => effect()); assert.equal(generates, 0);
  assert.ok(ui.tree.find(node => node.type === "iframe").props.srcDoc.includes("<html>Prepared document</html>"));
  const frame = ui.tree.find(node => node.type === "iframe");
  assert.equal(frame.props.sandbox, "allow-same-origin");
  assert.ok(!frame.props.sandbox.includes("allow-scripts"));
  const buttons = ui.tree.filter(node => node.type === "button"); assert.equal(buttons.length, 2);
  const copy = buttons.find(node => node.props.children.at(-1) === "복사");
  copy.props.onClick(); assert.deepEqual(writes, ["# Prepared MD"]); assert.equal(fetches, 0);
  assert.equal(ui.tree.some(node => node.props.children === "HTML 리포트 보기"), false);
});

test("restored report generates once on entry and errors require an explicit retry", () => {
  let generates = 0;
  const restored = resultView({ reportHtml: "", reportMarkdown: "", prepareReport: () => generates++ }, true);
  restored.effects.forEach(effect => effect()); assert.equal(generates, 1);
  const failed = resultView({ reportHtml: "", reportMarkdown: "", reportError: "Report failed", prepareReport: () => generates++ }, true);
  failed.effects.forEach(effect => effect()); assert.equal(generates, 1);
  failed.tree.find(node => node.type === "button" && node.props.children === "다시 만들기").props.onClick(); assert.equal(generates, 2);
});

test("progress navigates to /report only after a scan observed on this page signals readiness", () => {
  const navigation = [], effects = [];
  const observed = { current: false };
  let consumed = 0;
  let repository = { phase: "running", result: null, repoInput: "github.com/acme/app", findings: [], logs: [], isScanning: true,
    consumeResultReady: () => { consumed++; repository = { ...repository, resultReady: false }; } };
  const { default: Progress } = load("../src/components/repository-workspace.tsx", {
    react: { useEffect: effect => effects.push(effect), useRef: () => observed }, "react/jsx-runtime": { jsx: element, jsxs: element },
    "next/link": { default: "a" }, "next/navigation": { useRouter: () => ({ replace: path => navigation.push(path) }) },
    "@/lib/repository-routes": { REPOSITORY_RESULT_PATH: "/report" }, "@/components/repository-provider": { useRepository: () => repository },
    "@/components/progress/scan-progress": { default: "progress-h" }, "@/components/progress/scan-progress.css": {},
  });
  Progress(); effects.splice(0).forEach(effect => effect()); assert.deepEqual(navigation, []);
  repository = { ...repository, phase: "reporting" }; Progress(); effects.splice(0).forEach(effect => effect()); assert.deepEqual(navigation, []);
  repository = { ...repository, phase: "done", isScanning: false, resultReady: true, resultRepo: "github.com/acme/app" };
  Progress(); effects.splice(0).forEach(effect => effect()); assert.deepEqual(navigation, ["/report"]); assert.equal(consumed, 1);
  navigation.length = 0; observed.current = false;
  Progress(); effects.splice(0).forEach(effect => effect()); assert.deepEqual(navigation, [], "a restored or previously finished result must not auto-navigate");
  assert.equal(consumed, 1, "the consumed signal must stay cleared on re-entry");
  repository = { ...repository, phase: "running", isScanning: true };
  Progress(); effects.splice(0).forEach(effect => effect());
  repository = { ...repository, phase: "done", isScanning: false, resultReady: true };
  Progress(); effects.splice(0).forEach(effect => effect());
  assert.deepEqual(navigation, ["/report"], "a new scan gets one new navigation"); assert.equal(consumed, 2);
});

test("completed progress exposes a manual result link with or without a prepared report", () => {
  for (const reportHtml of ["", "<html>Ready</html>"]) {
    const tree = repositoryView({ phase: "done", result: {}, resultRepo: "github.com/acme/app", reportHtml });
    const action = tree.find(node => node.type === "a" && node.props.className === "button primary");
    assert.equal(action?.props.href, "/report");
    assert.equal(action.props.children[0], "결과 보기 ");
    assert.equal(action.props.disabled, undefined);
  }
  const busy = repositoryView({ phase: "running", result: {}, isScanning: true });
  assert.equal(busy.some(node => node.props.className === "repository-progress-result-action"), false);
});

test("report entry consumes a fresh navigation signal, including a late arrival", () => {
  let consumed = 0;
  for (const resultReady of [false, true]) {
    const ui = resultView({ resultReady, consumeResultReady: () => consumed++ });
    ui.effects.forEach(effect => effect());
    assert.equal(consumed, resultReady ? 1 : 0);
  }
});

test("header destination, label and aria-current follow scanning, result and empty state", () => {
  let repository = { isScanning: false, result: null };
  let pathname = "/";
  const { default: Shell } = load("../src/components/shell.tsx", {
    react: { useEffect() {} }, "react/jsx-runtime": { jsx: element, jsxs: element },
    "next/link": { default: "a" }, "next/navigation": { usePathname: () => pathname },
    "@/components/repository-provider": { useRepository: () => repository },
    "@/lib/repository-routes": { REPOSITORY_PROGRESS_PATH: "/repository", REPOSITORY_RESULT_PATH: "/report" },
  });
  function headerLink() {
    const nav = nodes(Shell({ children: null })).find(node => node.type === "nav");
    return nav.props.children[0];
  }
  // The server and first client render use the provider's empty default.
  assert.equal(headerLink().props.href, "/");
  assert.equal(headerLink().props.children, "점검");
  for (const [state, href, label] of [
    [{ isScanning: true, result: null }, "/repository", "진행 중"],
    [{ isScanning: true, result: {} }, "/repository", "진행 중"],
    [{ isScanning: false, result: {} }, "/report", "결과"],
    [{ isScanning: false, result: null }, "/", "점검"],
  ]) {
    repository = state; pathname = href;
    assert.equal(headerLink().props.href, href); assert.equal(headerLink().props.children, label);
    assert.equal(headerLink().props["aria-current"], "page");
    pathname = "/help";
    assert.equal(headerLink().props["aria-current"], undefined);
  }
});


test("short entries submit canonical URLs and expose the accessible fixed prefix", () => {
  for (const repoInput of ["acme/app", " acme/app/ "]) {
    const ui = entry({ repoInput });
    const prefix = ui.tree.find(node => node.props.id === "repository-prefix");
    assert.equal(prefix.props.children, "https://github.com/");
    prefix.props.onClick(); assert.equal(ui.focused(), 1);
    assert.equal(ui.tree.find(node => node.type === "input").props["aria-describedby"], "repository-prefix repository-hint");
    ui.submit(); assert.deepEqual(ui.calls, ["https://github.com/acme/app"]);
  }
  for (const repoInput of ["https://github.com/acme/app", "github.com/acme/app", "alice.github.io"]) {
    assert.equal(entry({ repoInput }).tree.some(node => node.props.id === "repository-prefix"), false);
  }
  for (const repoInput of ["example.com/repo", "-alice/repo", "a--b/repo", "alice/../repo", "alice/repo?x=1"]) {
    const ui = entry({ repoInput }); ui.submit(); assert.deepEqual(ui.calls, [], repoInput);
  }
});
