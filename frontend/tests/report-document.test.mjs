import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

function presentation(runtime = {}) {
  const loaded = { exports: {} };
  const source = readFileSync(new URL("../src/lib/report-document.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, ...runtime });
  return loaded.exports;
}

test("report presentation keeps every row in the HTML and adds mobile and theme styles without a second animation", () => {
  const { reportDocumentHtml } = presentation();
  const body = "<main><section><table><tr><td>항목</td></tr></table></section></main>";
  const html = reportDocumentHtml("<!doctype html><html><head></head><body>" + body + "</body></html>");
  assert.ok(html.includes(body));
  assert.ok(html.indexOf("data-report-presentation") < html.indexOf("</head>"));
  assert.equal(html.includes("report-score-row"), false);
  assert.equal(html.includes("@keyframes"), false);
  assert.match(html, /data-theme="dark"/); assert.match(html, /max-width:440px/);
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("display:none"), false);
});

test("document sizing and theme changes stay live until cleanup", async () => {
  const rows = Array.from({ length: 22 }, (_, index) => ({
    classes: [], properties: {},
    matches: () => index === 3,
    closest: () => index === 4 ? {} : null,
    style: { setProperty(key, value) { rows[index].properties[key] = value; } },
    classList: { add(value) { rows[index].classes.push(value); } },
  }));
  let height = 1600, fontDone;
  const main = { querySelectorAll: () => rows, getBoundingClientRect: () => ({ height }) };
  const root = { dataset: { theme: "dark" } };
  const doc = { querySelector: () => main, documentElement: { dataset: {} }, fonts: { ready: new Promise(resolve => { fontDone = resolve; }) } };
  const observers = [];
  class Observer {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(target) { this.target = target; }
    disconnect() { this.disconnected = true; }
  }
  const { mountReportDocument } = presentation({ document: { documentElement: root }, ResizeObserver: Observer, MutationObserver: Observer });
  const frame = { contentDocument: doc, style: {} };
  const cleanup = mountReportDocument(frame);
  assert.equal(rows.filter(row => row.classes.length).length, 0, "iframe has no row animations");
  assert.equal(frame.style.height, "1602px"); assert.equal(doc.documentElement.dataset.theme, "dark");
  height = 800; observers[0].callback(); assert.equal(frame.style.height, "802px", "resizing can shrink as well as grow");
  root.dataset.theme = "light"; observers[1].callback(); assert.equal(doc.documentElement.dataset.theme, "light");
  assert.equal(observers[0].target, main);
  cleanup(); assert.ok(observers.every(observer => observer.disconnected));
  height = 900; fontDone(); await Promise.resolve(); assert.equal(frame.style.height, "802px", "late font readiness cannot touch an unmounted frame");
});
