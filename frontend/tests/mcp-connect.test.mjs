import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

function load(env = {}) {
  const source = readFileSync(new URL("../src/lib/mcp-connect.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, JSON, process: { env } });
  return loaded.exports;
}
const URL_ = "https://oboe-handiness-enroll.ngrok-free.dev/mcp/service/rpc";

test("every agent target uses the public endpoint and the one tentative name", () => {
  const { mcpTargets, MCP_ENDPOINT, MCP_SERVER_NAME } = load();
  assert.equal(MCP_ENDPOINT, URL_);
  assert.equal(MCP_SERVER_NAME, "72hour_mcp");
  const targets = Array.from(mcpTargets());
  assert.deepEqual(targets.map(item => item.label), ["Claude Code", "Codex", "Prompt"]);
  for (const item of targets) {
    assert.ok(item.text.includes(URL_), `${item.label} has the endpoint`);
    assert.ok(item.text.includes("72hour_mcp"), `${item.label} has the name`);
  }
  const byId = Object.fromEntries(targets.map(item => [item.id, item]));
  assert.equal(byId.codex.text, `codex mcp add 72hour_mcp --url ${URL_}`);
  assert.equal(byId.claude.text, `claude mcp add --transport http 72hour_mcp ${URL_}`);
  assert.equal(byId.prompt.kind, "prompt");
  assert.match(byId.prompt.text, /Streamable HTTP/);
  assert.match(byId.prompt.text, /No authentication/);
  assert.match(byId.prompt.text, /service_info/);
  assert.doesNotMatch(byId.prompt.text, /[가-힣]/, "the agent prompt is English");
});

test("a build-time origin override replaces the default and drops trailing slashes", () => {
  const { MCP_ENDPOINT } = load({ NEXT_PUBLIC_MCP_ORIGIN: " https://mcp.example.test/ " });
  assert.equal(MCP_ENDPOINT, "https://mcp.example.test/mcp/service/rpc");
});

function mountCard() {
  const slots = [], writes = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => { slots[index] = value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
  };
  const element = (type, props) => ({ type, props: props ?? {} });
  const icons = { Check: "check-icon", Copy: "copy-icon", Unplug: "unplug-icon" };
  const source = readFileSync(new URL("../src/components/mcp-connect.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, {
    module: loaded, exports: loaded.exports,
    navigator: { clipboard: { writeText(text) {
      return new Promise((resolve, reject) => { writes.push({ text, resolve, reject }); });
    } } },
    require(name) {
      if (name === "react") return react;
      if (name === "react/jsx-runtime") return { jsx: element, jsxs: element };
      if (name === "lucide-react") return icons;
      if (name === "@/lib/mcp-connect") return load();
      if (name === "./mcp-connect.css") return {};
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  function nodes(tree) {
    if (!tree || typeof tree !== "object") return [];
    if (Array.isArray(tree)) return tree.flatMap(nodes);
    return [tree, ...nodes(tree.props?.children)];
  }
  function render() {
    cursor = 0;
    return nodes(loaded.exports.default({}));
  }
  return {
    writes,
    choose(label) { render().find(node => node.type === "button" && node.props.children === label).props.onClick(); },
    copy() { render().find(node => node.props.className === "mc-copy").props.onClick(); },
    view() {
      const tree = render();
      return {
        selected: tree.find(node => node.props["aria-pressed"] === true).props.children,
        text: tree.find(node => node.type === "pre").props.children,
        status: tree.find(node => node.props.role === "status").props.children,
        copied: tree.some(node => node.type === icons.Check),
      };
    },
    async finish(index, failure = false) {
      if (failure) writes[index].reject(new Error("Clipboard denied"));
      else writes[index].resolve();
      // Let the component's await continuation run before inspecting its state.
      await Promise.resolve();
      await Promise.resolve();
    },
  };
}

test("a delayed copy cannot update the card after changing tools, including switching back", async () => {
  for (const failure of [false, true]) {
    for (const switchBack of [false, true]) {
      const card = mountCard();
      card.copy();
      assert.match(card.writes[0].text, /^claude mcp add /);
      card.choose("Codex");
      if (switchBack) card.choose("Claude Code");
      const before = card.view();
      assert.equal(before.status, "");
      assert.equal(before.copied, false);
      await card.finish(0, failure);
      assert.deepEqual(card.view(), before);
    }
  }
});

test("an older copy cannot overwrite a newer copy's success or failure", async () => {
  for (const changeTool of [false, true]) {
    for (const latestFails of [false, true]) {
      const card = mountCard();
      card.copy();
      if (changeTool) card.choose("Codex");
      card.copy();
      await card.finish(1, latestFails);
      const before = card.view();
      assert.equal(before.copied, !latestFails);
      assert.equal(before.status, latestFails
        ? "복사하지 못했습니다. 내용을 직접 선택해 복사해 주세요."
        : `${changeTool ? "Codex" : "Claude Code"} 명령을 복사했습니다.`);
      await card.finish(0, !latestFails);
      assert.deepEqual(card.view(), before);
    }
  }
});

test("the current tool still reports copy success and failure", async () => {
  for (const label of ["Claude Code", "Codex", "Prompt"]) {
    const card = mountCard();
    card.choose(label);
    card.copy();
    assert.equal(card.writes[0].text, card.view().text);
    await card.finish(0);
    assert.equal(card.view().copied, true);
    assert.equal(card.view().status, label === "Prompt"
      ? "지시문을 복사했습니다. 사용하는 AI 에이전트 채팅에 붙여 넣으세요."
      : `${label} 명령을 복사했습니다.`);
    card.copy();
    await card.finish(1, true);
    assert.equal(card.view().copied, false);
    assert.equal(card.view().status, "복사하지 못했습니다. 내용을 직접 선택해 복사해 주세요.");
  }
});
