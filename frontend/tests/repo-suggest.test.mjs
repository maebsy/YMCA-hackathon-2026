import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const require = createRequire(import.meta.url);

// Each load has an independent module cache, including the public-repository cache.
function loadSuggestions(runtime = {}) {
  const modules = new Map();
  function load(url) {
    if (modules.has(url.href)) return modules.get(url.href).exports;
    const source = readFileSync(url, "utf8");
    const compiled = ts.transpileModule(source, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    } }).outputText;
    const loaded = { exports: {} };
    modules.set(url.href, loaded);
    vm.runInNewContext(compiled, {
      module: loaded, exports: loaded.exports, URL, AbortSignal, ...runtime,
      require(name) {
        if (name.startsWith("@/lib/")) return load(new URL(`../src/lib/${name.slice(6)}.ts`, import.meta.url));
        if (name.startsWith(".")) return load(new URL(`${name}.ts`, url));
        return require(name);
      },
    }, { filename: url.pathname });
    return loaded.exports;
  }
  return load(new URL("../src/lib/repo-suggest.ts", import.meta.url));
}

const plain = value => JSON.parse(JSON.stringify(value));
const response = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

test("repository prefix accepts GitHub and Pages forms with optional HTTPS", () => {
  const { parseRepoPrefix } = loadSuggestions();
  for (const [value, owner, partial] of [
    ["alice/", "alice", ""],
    ["Alice/Function_face-1.0", "Alice", "Function_face-1.0"],
    ["github.com/alice/", "alice", ""],
    ["https://github.com/alice/f", "alice", "f"],
    ["alice.github.io/", "alice", ""],
    ["https://alice.github.io/Function_face-1.0", "alice", "Function_face-1.0"],
    ["github.com/a/f", "a", "f"],
    [`github.com/${"a".repeat(39)}/f`, "a".repeat(39), "f"],
  ]) assert.deepEqual(plain(parseRepoPrefix(value)), { owner, partial }, value);
});

test("repository prefix rejects invalid owners, paths and lookalike domains", () => {
  const { parseRepoPrefix } = loadSuggestions();
  for (const value of [
    "", "github.com/alice", "alice.github.io", "http://github.com/alice/f",
    "github.com/-alice/f", "github.com/alice-/f", "github.com/al--ice/f",
    "github.com/al_ice/f", "github.com/al.ice/f", `github.com/${"a".repeat(40)}/f`,
    "-alice.github.io/f", "al--ice.github.io/f", "github.com//f",
    "github.com/alice/f/", "github.com/alice/f/tree/main", "alice.github.io/f/",
    "github.com/alice/f?x=1", "github.com/alice/f#readme", "github.com/alice/f%20",
    "github.com/alice/f x", "github.com/alice/한글", "github.com/alice/f\\x",
    "example.com/alice/f", "github.com.evil.com/alice/f", "x.github.io.evil.com/f",
    "https://github.com:443/alice/f", "https://user@github.com/alice/f",
  ]) assert.equal(parseRepoPrefix(value), null, value);
});

test("completion chooses the first case-insensitive prefix and preserves its remainder", () => {
  const { bestCompletion } = loadSuggestions();
  assert.deepEqual(plain(bestCompletion("fU", ["a-function", "Function-Face", "future"])), {
    name: "Function-Face", remainder: "nction-Face",
  });
  assert.deepEqual(plain(bestCompletion("Function-Face", ["Function-Face"])), {
    name: "Function-Face", remainder: "",
  });
  assert.equal(bestCompletion("", ["function-face"]), null);
  assert.equal(bestCompletion("face", ["function-face"]), null);
  assert.equal(bestCompletion("f", []), null);
});

test("public repositories preserve server order and use only the public API request", async () => {
  const timeouts = [];
  const signal = new AbortController().signal;
  const { loadPublicRepos } = loadSuggestions({ AbortSignal: { timeout(ms) { timeouts.push(ms); return signal; } } });
  const calls = [];
  const names = await loadPublicRepos("alice", async (url, options) => {
    calls.push({ url, options });
    return response([{ name: "recent" }, { name: "function-face" }, { name: "older" }]);
  });
  assert.deepEqual(plain(names), ["recent", "function-face", "older"]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.github.com/users/alice/repos?per_page=100&sort=updated&type=owner");
  assert.equal(calls[0].options.method ?? "GET", "GET");
  const headers = new Headers(calls[0].options.headers);
  assert.equal(headers.get("Accept"), "application/vnd.github+json");
  assert.equal(headers.has("Authorization"), false);
  assert.equal(calls[0].options.credentials, "omit");
  assert.equal(calls[0].url.toLowerCase().includes("authorization"), false);
  assert.equal(calls[0].options.signal, signal);
  assert.deepEqual(timeouts, [5000]);
});

test("concurrent and subsequent requests share a case-insensitive owner cache", async () => {
  const { loadPublicRepos } = loadSuggestions();
  let finish;
  const waiting = new Promise(resolve => { finish = resolve; });
  let calls = 0;
  const fetchImpl = async () => { calls++; await waiting; return response([{ name: "function-face" }]); };
  const first = loadPublicRepos("Alice", fetchImpl);
  const second = loadPublicRepos("ALICE", fetchImpl);
  await Promise.resolve();
  assert.equal(calls, 1);
  finish();
  assert.deepEqual(plain(await first), ["function-face"]);
  assert.deepEqual(plain(await second), ["function-face"]);
  assert.deepEqual(plain(await loadPublicRepos("alice", fetchImpl)), ["function-face"]);
  assert.equal(calls, 1);
  await loadPublicRepos("bob", fetchImpl);
  assert.equal(calls, 2);
});

for (const [name, fetchResult] of [
  ["404", () => response({ message: "Not Found" }, 404)],
  ["403 rate limit", () => response({ message: "API rate limit exceeded" }, 403)],
  ["network failure", () => { throw new Error("offline"); }],
  ["invalid top-level data", () => response({ items: [] })],
  ["invalid repository name", () => response([{ name: 42 }])],
  ["invalid JSON", () => ({ ok: true, json: async () => { throw new SyntaxError("invalid JSON"); } })],
]) {
  test(`public repository ${name} returns and briefly caches an empty list`, async () => {
    const { loadPublicRepos } = loadSuggestions();
    let calls = 0;
    const fetchImpl = async () => { calls++; return fetchResult(); };
    assert.deepEqual(plain(await loadPublicRepos("alice", fetchImpl)), []);
    assert.deepEqual(plain(await loadPublicRepos("ALICE", fetchImpl)), []);
    assert.equal(calls, 1);
  });
}

test("invalid owners never make a public API request", async () => {
  const { loadPublicRepos } = loadSuggestions();
  const fetchImpl = () => { assert.fail("invalid owner must not be requested"); };
  for (const owner of ["", "-alice", "alice-", "al--ice", "al_ice", "alice/path", "a".repeat(40)]) {
    assert.deepEqual(plain(await loadPublicRepos(owner, fetchImpl)), [], owner);
  }
});

test("inline completion only follows plain insertion at a collapsed end caret", () => {
  const { canCompleteInput } = loadSuggestions();
  const snapshot = { value: "github.com/alice/f", inputType: "insertText", isComposing: false,
    selectionStart: 18, selectionEnd: 18 };
  snapshot.selectionStart = snapshot.selectionEnd = snapshot.value.length;
  assert.equal(canCompleteInput(snapshot), true);
  for (const changed of [
    { inputType: "deleteContentBackward" }, { inputType: "deleteContentForward" },
    { inputType: "insertFromPaste" }, { inputType: "insertCompositionText" },
    { inputType: "" }, { isComposing: true },
    { selectionStart: 1, selectionEnd: 1 }, { selectionStart: 1 },
    { selectionStart: null, selectionEnd: null },
  ]) assert.equal(canCompleteInput({ ...snapshot, ...changed }), false, JSON.stringify(changed));
});

test("success and failure cache entries expire so a later request can refresh", async () => {
  let clock = 0;
  const { loadPublicRepos } = loadSuggestions({ Date: { now: () => clock } });
  let calls = 0;
  const fetchImpl = async () => {
    calls++;
    return calls === 1 ? response({}, 403) : response([{ name: `repo-${calls}` }]);
  };
  assert.deepEqual(plain(await loadPublicRepos("alice", fetchImpl)), []);
  clock = 29_999;
  assert.deepEqual(plain(await loadPublicRepos("alice", fetchImpl)), []);
  assert.equal(calls, 1);
  clock = 30_001;
  assert.deepEqual(plain(await loadPublicRepos("alice", fetchImpl)), ["repo-2"]);
  clock += 59_999;
  await loadPublicRepos("alice", fetchImpl);
  assert.equal(calls, 2);
  clock += 2;
  assert.deepEqual(plain(await loadPublicRepos("alice", fetchImpl)), ["repo-3"]);
});

// A small hook runner models controlled state commits and layout effects, without
// a browser or extra packages. API fixtures can remain pending across input edits.
function mountAutocomplete(loadPublicRepos = async () => ["function-face", "future"]) {
  const slots = [];
  let cursor = 0;
  let dirty = false;
  let state = "";
  let result;
  let effects = [];
  let layouts = [];
  const cleanups = [];
  const listeners = new Map();
  const pendingTimers = new Map();
  const scrolled = [];
  const list = { scrollTop: 0, children: [], contains: target => target === "option" };
  let timerId = 0;
  let clock = 0;
  const input = {
    value: "", selectionStart: 0, selectionEnd: 0, disabled: false, readOnly: false,
    ownerDocument: {
      addEventListener(name, callback) { listeners.set(name, callback); },
      removeEventListener(name) { listeners.delete(name); },
    },
    setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; },
    focus() { this.ownerDocument.activeElement = this; },
  };
  input.ownerDocument.activeElement = input;
  const inputRef = { current: input };
  const schedule = queue => (callback, deps) => {
    const index = cursor++;
    const old = slots[index];
    if (!old || !deps || deps.some((value, i) => value !== old[i])) queue.push(callback);
    slots[index] = deps;
  };
  const react = {
    useId() {
      const index = cursor++;
      if (!(index in slots)) slots[index] = `autocomplete-${index}`;
      return slots[index];
    },
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => {
        const next = typeof value === "function" ? value(slots[index]) : value;
        if (slots[index] !== next) { slots[index] = next; dirty = true; }
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useEffect: (callback, deps) => schedule(effects)(callback, deps),
    useLayoutEffect: (callback, deps) => schedule(layouts)(callback, deps),
  };
  const source = readFileSync(new URL("../src/lib/use-repo-autocomplete.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, {
    module: loaded, exports: loaded.exports,
    setTimeout(callback, ms) { const id = ++timerId; pendingTimers.set(id, { callback, at: clock + ms }); return id; },
    clearTimeout(id) { pendingTimers.delete(id); },
    require: name => name === "react" ? react : { ...loadSuggestions(), loadPublicRepos },
  });
  function render() {
    do {
      dirty = false; cursor = 0; layouts = []; effects = [];
      result = loaded.exports.useRepoAutocomplete({ value: state, setValue(value) { state = value; dirty = true; }, inputRef });
      // React commits the controlled value before running layout effects.
      if (input.value !== result.inputProps.value) {
        input.value = result.inputProps.value;
        input.setSelectionRange(input.value.length, input.value.length);
      }
      list.children = result.suggestions.map((_, index) => ({ scrollIntoView() {
        scrolled.push(index);
        list.scrollTop = index * 40;
      } }));
      result.listProps.ref.current = list;
      for (const callback of layouts) callback();
      for (const callback of effects) {
        const cleanup = callback();
        if (cleanup) cleanups.push(cleanup);
      }
    } while (dirty);
    return result;
  }
  render();
  return {
    input,
    list,
    get value() { return state; },
    get output() { return result; },
    scrolled,
    change(value, nativeEvent = {}, commit = true) {
      input.value = value;
      input.setSelectionRange(value.length, value.length);
      result.inputProps.onChange({ currentTarget: input, nativeEvent: { inputType: "insertText", isComposing: false, ...nativeEvent } });
      if (commit) render();
    },
    key(key) {
      let prevented = false;
      result.inputProps.onKeyDown({ key, currentTarget: input, nativeEvent: { isComposing: false },
        preventDefault() { prevented = true; } });
      render();
      return prevented;
    },
    async settle() { await Promise.resolve(); await Promise.resolve(); render(); },
    select(index) { result.select(result.suggestions[index]); render(); },
    outside(target = {}) { listeners.get("pointerdown")?.({ target }); render(); },
    advance(ms) {
      clock += ms;
      for (const [id, timer] of pendingTimers) {
        if (timer.at <= clock) { pendingTimers.delete(id); timer.callback(); }
      }
      render();
    },
    unmount() { cleanups.forEach(cleanup => cleanup()); },
  };
}

test("controlled autocomplete updates state then selects only the added suffix", async () => {
  const ownerRequests = [];
  const hook = mountAutocomplete(async owner => { ownerRequests.push(owner); return ["function-face"]; });
  hook.change("github.com/alice/");
  await hook.settle();
  assert.equal(hook.value, "github.com/alice/");
  hook.change("github.com/alice/f");
  await hook.settle();
  assert.equal(hook.value, "github.com/alice/function-face");
  assert.equal(hook.input.value, hook.value);
  assert.equal(hook.input.selectionStart, "github.com/alice/f".length);
  assert.equal(hook.input.selectionEnd, hook.value.length);
  assert.equal(hook.output.inputProps["aria-autocomplete"], "both");
  assert.equal(hook.output.inputProps.role, "combobox");
  assert.equal(hook.output.announcement, "후보 1개");
  assert.deepEqual(ownerRequests, ["alice", "alice"]);
  // Typing replaces the selected tail; completion is calculated from that input.
  hook.change("github.com/alice/fu");
  await hook.settle();
  assert.equal(hook.value, "github.com/alice/function-face");
  assert.equal(hook.input.selectionStart, "github.com/alice/fu".length);
  hook.unmount();
});

test("deletion, paste and IME changes never apply an inline suggestion", async () => {
  for (const nativeEvent of [
    { inputType: "deleteContentBackward" }, { inputType: "deleteContentForward" },
    { inputType: "insertFromPaste" }, { isComposing: true },
  ]) {
    const hook = mountAutocomplete();
    hook.change("github.com/alice/f", nativeEvent);
    await hook.settle();
    assert.equal(hook.value, "github.com/alice/f");
    assert.equal(hook.output.activeIndex, -1);
    hook.unmount();
  }
  const hook = mountAutocomplete();
  hook.output.inputProps.onCompositionStart();
  hook.change("github.com/alice/f");
  await hook.settle();
  assert.equal(hook.value, "github.com/alice/f");
  hook.output.inputProps.onCompositionEnd();
  hook.unmount();
});

test("late repository results cannot replace newer input or a moved caret", async () => {
  for (const invalidate of [
    hook => hook.change("unrelated input"),
    hook => hook.input.setSelectionRange(1, 1),
    hook => { hook.input.ownerDocument.activeElement = null; },
    hook => hook.output.inputProps.onBlur(),
    hook => hook.unmount(),
  ]) {
    let finish;
    const waiting = new Promise(resolve => { finish = resolve; });
    const hook = mountAutocomplete(() => waiting);
    hook.change("github.com/alice/f");
    invalidate(hook);
    const before = hook.value;
    finish(["function-face"]);
    await hook.settle();
    assert.equal(hook.value, before);
    hook.unmount();
  }
});

test("ArrowRight, End and Tab confirm an active completion only", async () => {
  for (const key of ["ArrowRight", "End", "Tab"]) {
    const hook = mountAutocomplete();
    assert.equal(hook.key(key), false);
    hook.change("github.com/alice/f");
    await hook.settle();
    const full = hook.value;
    assert.equal(hook.key(key), true);
    assert.equal(hook.value, full);
    assert.equal(hook.input.selectionStart, full.length);
    assert.equal(hook.input.selectionEnd, full.length);
    assert.equal(hook.output.announcement, "");
    assert.equal(hook.key(key), false);
    hook.unmount();
  }
});

test("Escape first closes the list and then restores only the typed prefix", async () => {
  const hook = mountAutocomplete();
  hook.change("github.com/alice/f");
  await hook.settle();
  const full = hook.value;
  assert.equal(hook.output.open, true);
  assert.equal(hook.key("Escape"), true);
  assert.equal(hook.value, full);
  assert.equal(hook.output.open, false);
  assert.equal(hook.key("Escape"), true);
  assert.equal(hook.value, "github.com/alice/f");
  assert.equal(hook.input.selectionStart, hook.value.length);
  assert.equal(hook.input.selectionEnd, hook.value.length);
  assert.equal(hook.key("Tab"), false);
  hook.unmount();
});

test("dropdown ranking keeps starts before contains and retains all 100 returned names", () => {
  const { matchingRepos } = loadSuggestions();
  assert.deepEqual(plain(matchingRepos("b", ["alpha-b", "B2-1", "cab", "b2-3", "none"])),
    ["B2-1", "b2-3", "alpha-b", "cab"]);
  const names = Array.from({ length: 100 }, (_, index) => `repo-${index}`);
  assert.deepEqual(plain(matchingRepos("", names)), names);
});

test("slash opens a loading row immediately, then reveals every returned repository", async () => {
  let finish;
  const hook = mountAutocomplete(() => new Promise(resolve => { finish = resolve; }));
  hook.change("github.com/alice/");
  assert.equal(hook.output.open, true);
  assert.equal(hook.output.loading, true);
  assert.equal(hook.output.announcement, "저장소 목록 불러오는 중");
  const names = Array.from({ length: 100 }, (_, index) => `repo-${index}`);
  finish(names);
  await hook.settle();
  assert.equal(hook.output.loading, false);
  assert.equal(hook.output.suggestions.length, 100);
  assert.equal(hook.output.activeIndex, -1);
  assert.equal(hook.output.announcement, "후보 100개");
  assert.equal(hook.value, "github.com/alice/");
  hook.unmount();
});

test("arrows wrap, synchronize inline text and scroll the active option into view", async () => {
  const hook = mountAutocomplete(async () => ["prefix-b", "b2-1", "b2-3"]);
  hook.change("github.com/alice/b");
  await hook.settle();
  assert.deepEqual(plain(hook.output.suggestions), ["b2-1", "b2-3", "prefix-b"]);
  assert.equal(hook.value, "github.com/alice/b2-1");
  assert.equal(hook.key("ArrowDown"), true);
  assert.equal(hook.output.activeIndex, 1);
  assert.equal(hook.value, "github.com/alice/b2-3");
  assert.equal(hook.input.selectionStart, "github.com/alice/b".length);
  hook.key("ArrowDown");
  assert.equal(hook.value, "github.com/alice/prefix-b");
  assert.equal(hook.input.selectionStart, "github.com/alice/".length);
  hook.key("ArrowDown");
  assert.equal(hook.output.activeIndex, 0);
  hook.key("ArrowUp");
  assert.equal(hook.output.activeIndex, 2);
  assert.equal(hook.output.inputProps["aria-activedescendant"], hook.output.optionId(2));
  assert.equal(hook.scrolled.at(-1), 2);
  hook.unmount();
});

test("a new owner list with no active option returns scrolling to its recent first item", async () => {
  const hook = mountAutocomplete(async owner => Array.from({ length: 30 }, (_, index) => `${owner}-recent-${index}`));
  hook.change("github.com/alice/"); await hook.settle();
  assert.equal(hook.output.activeIndex, -1);
  hook.key("ArrowUp");
  assert.equal(hook.output.activeIndex, 29);
  assert.equal(hook.scrolled.at(-1), 29);
  assert.ok(hook.list.scrollTop > 0);
  hook.change("github.com/bob/");
  assert.equal(hook.list.scrollTop, 0, "loading a different owner resets the existing list element");
  await hook.settle();
  assert.equal(hook.output.activeIndex, -1);
  assert.equal(hook.list.scrollTop, 0);
  assert.equal(hook.output.suggestions[0], "bob-recent-0");
  hook.unmount();
});

test("Enter confirms the active option once and leaves the next Enter to the form", async () => {
  const hook = mountAutocomplete();
  hook.change("github.com/alice/f");
  await hook.settle();
  assert.equal(hook.key("Enter"), true);
  assert.equal(hook.value, "github.com/alice/function-face");
  assert.equal(hook.output.open, false);
  assert.equal(hook.input.selectionStart, hook.value.length);
  assert.equal(hook.key("Enter"), false);
  hook.unmount();
});

test("selection closes the list and leaves input focused; outside and blur dismiss it", async () => {
  const hook = mountAutocomplete();
  hook.change("github.com/alice/");
  await hook.settle();
  hook.select(1);
  assert.equal(hook.value, "github.com/alice/future");
  assert.equal(hook.output.open, false);
  assert.equal(hook.input.ownerDocument.activeElement, hook.input);
  assert.equal(hook.input.selectionStart, hook.value.length);
  hook.change("github.com/alice/"); await hook.settle();
  hook.outside("option");
  assert.equal(hook.output.open, true);
  hook.outside();
  assert.equal(hook.output.open, false);
  hook.change("github.com/alice/"); await hook.settle();
  hook.output.inputProps.onBlur(); await hook.settle();
  assert.equal(hook.output.open, false);
  hook.unmount();
});

test("same completed value after batched typing still selects the new remainder", async () => {
  const hook = mountAutocomplete();
  hook.change("github.com/alice/f"); await hook.settle();
  const original = hook.value;
  // No intermediate commit of 'fu': this models React batching typed -> full.
  hook.change("github.com/alice/fu", {}, false);
  await hook.settle();
  assert.equal(hook.value, original);
  assert.equal(hook.input.selectionStart, "github.com/alice/fu".length);
  assert.equal(hook.input.selectionEnd, original.length);
  hook.unmount();
});

test("a disabled or read-only input rejects a repository response arriving after submit", async () => {
  for (const property of ["disabled", "readOnly"]) {
    let finish;
    const hook = mountAutocomplete(() => new Promise(resolve => { finish = resolve; }));
    hook.change("https://github.com/alice/f");
    hook.input[property] = true;
    finish(["function-face"]); await hook.settle();
    assert.equal(hook.value, "https://github.com/alice/f");
    assert.equal(hook.input.selectionStart, hook.value.length);
    hook.unmount();
  }
});

test("owner prefetch debounces for 350ms and runs once for each case-insensitive owner", async () => {
  const calls = [];
  const hook = mountAutocomplete(async owner => { calls.push(owner); return ["function-face"]; });
  hook.change("github.com/ali");
  hook.advance(200);
  hook.change("github.com/alice");
  hook.advance(349);
  assert.deepEqual(calls, []);
  hook.advance(1);
  assert.deepEqual(calls, ["alice"]);
  hook.change("github.com/ALICE");
  hook.advance(350);
  assert.deepEqual(calls, ["alice"]);
  hook.change("bob.github.io");
  hook.advance(350);
  assert.deepEqual(calls, ["alice", "bob"]);
  hook.unmount();
});

test("empty public repository response closes the menu without an error announcement", async () => {
  const hook = mountAutocomplete(async () => []);
  hook.change("github.com/alice/"); await hook.settle();
  assert.equal(hook.output.open, false);
  assert.equal(hook.output.announcement, "");
  assert.equal(hook.value, "github.com/alice/");
  hook.unmount();
});


test("short owner prefetch and completion preserve the short input", async () => {
  const calls = [];
  const hook = mountAutocomplete(async owner => { calls.push(owner); return ["function-face", "future"]; });
  hook.change("alice"); hook.advance(349); assert.deepEqual(calls, []);
  hook.advance(1); assert.deepEqual(calls, ["alice"]);
  hook.change("alice/"); assert.equal(hook.output.open, true); assert.equal(hook.output.loading, true);
  await hook.settle(); assert.equal(hook.output.suggestions.length, 2);
  hook.change("alice/f"); await hook.settle();
  assert.equal(hook.value, "alice/function-face");
  assert.equal(hook.input.selectionStart, "alice/f".length);
  hook.output.select("future"); assert.equal(hook.value, "alice/future");
  hook.unmount();
});

test("autocomplete rejects short domain lookalikes", () => {
  const { parseRepoPrefix } = loadSuggestions();
  for (const value of ["example.com/repo", "alice.github.io.evil/repo", "-alice/repo", "a--b/repo"]) assert.equal(parseRepoPrefix(value), null);
});

test("shorthand expansion distinguishes Pages hosts from repository names", () => {
  const { repositoryInputUrl, parseRepoPrefix } = loadSuggestions();
  for (const [value, , address, owner, partial] of [
    ["papawolf42/papawolf42.github.io", true, "https://github.com/papawolf42/papawolf42.github.io", "papawolf42", "papawolf42.github.io"],
    ["owner/name.github.io", true, "https://github.com/owner/name.github.io", "owner", "name.github.io"],
    ["owner/repo.github.com", true, "https://github.com/owner/repo.github.com", "owner", "repo.github.com"],
    ["x.github.io", false, "x.github.io", null, null],
    ["x.github.io/proj", false, "x.github.io/proj", "x", "proj"],
    ["github.com/x/y", false, "github.com/x/y", "x", "y"],
    ["https://github.com/x/y", false, "https://github.com/x/y", "x", "y"],
    [" X.GITHUB.IO/proj ", false, "X.GITHUB.IO/proj", null, null],
    ["httparty/repo", true, "https://github.com/httparty/repo", "httparty", "repo"],
    ["HttpClient/project", true, "https://github.com/HttpClient/project", "HttpClient", "project"],
  ]) {
    assert.equal(repositoryInputUrl(value), address, value);
    assert.deepEqual(plain(parseRepoPrefix(value)), owner ? { owner, partial } : null, value);
  }
});

test("http owners remain shorthand while only a scheme with :// counts as a URL", () => {
  const { repositoryInputUrl } = loadSuggestions();
  for (const value of ["httparty/repo", "HttpClient/project"]) {
    assert.equal(repositoryInputUrl(value), `https://github.com/${value}`);
  }
  for (const value of ["https://github.com/alice/repo", "HTTP://example.com/repo", "http://github.com/alice/repo"]) {
    assert.equal(repositoryInputUrl(value), value);
  }
});

test("all input styles and http owners prefetch, complete and select without changing format", async () => {
  for (const base of ["alice/", "github.com/alice/", "alice.github.io/", "httparty/", "HttpClient/"]) {
    const calls = [];
    const hook = mountAutocomplete(async owner => { calls.push(owner); return ["function-face", "future"]; });
    hook.change(base.slice(0,-1)); hook.advance(350);
    assert.equal(calls.length, 1, base);
    hook.change(base); await hook.settle();
    assert.equal(hook.output.suggestions.length, 2, base);
    hook.change(`${base}f`); await hook.settle();
    assert.equal(hook.value, `${base}function-face`, base);
    assert.equal(hook.input.selectionStart, `${base}f`.length);
    hook.output.select("future");
    assert.equal(hook.value, `${base}future`, base);
    hook.unmount();
  }
});

test("inline completion and dropdown selection retain repository names containing github.io", async () => {
  const hook = mountAutocomplete(async () => ["name.github.io", "next.github.io"]);
  hook.change("owner/name.github.i"); await hook.settle();
  assert.equal(hook.value, "owner/name.github.io");
  assert.equal(hook.input.selectionStart, "owner/name.github.i".length);
  assert.equal(hook.input.selectionEnd, hook.value.length);
  hook.output.select("next.github.io");
  assert.equal(hook.value, "owner/next.github.io");
  hook.unmount();
});
