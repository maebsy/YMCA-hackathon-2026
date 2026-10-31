import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(resolve(root, "package.json"));
const ts = require("typescript");
const repo = "https://github.com/test-org/incident-evidence";
const clone = value => structuredClone(value);

function loadSource(relative, imports = {}) {
  const compiled = ts.transpileModule(readFileSync(resolve(root, relative), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(compiled, { module: loaded, exports: loaded.exports, Date, Error, console,
    require: name => imports[name] ?? require(name) }, { filename: relative });
  return loaded.exports;
}
const domain = loadSource("src/lib/incident.ts");
function deferred() {
  let resolvePromise, rejectPromise;
  const promise = new Promise((resolve, reject) => { resolvePromise = resolve; rejectPromise = reject; });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}
function assessment() {
  return { needs: [
    { kind: "incident_24h", required: false, reasons: ["검증용 API 응답"], deadline: null },
    { kind: "privacy_72h", required: false, reasons: ["추가 확인 필요"], deadline: null },
  ] };
}
function report(kind) {
  return { kind, title: `${kind} 검토용 초안`, subtitle: null, generated_at: "2026-10-31T09:00:00+09:00",
    status: { text: "작성 중", tone: "warning" }, deadline: null, sections: [], missing: ["담당자"],
    submit_to: ["공식 제출처에서 확인"], disclaimer: "테스트용 응답 · 실제 신고 없음" };
}
function evidence(fingerprint = "raw-fingerprint", suffix = "") {
  return { repo, fingerprint, title: `직접 선택한 발견 ${suffix}`, finding: {
    fingerprint, id: `different-ui-id-${suffix}`, tool: "semgrep", category: "code", rule_id: `rule-${suffix}`,
    title: `직접 선택한 발견 ${suffix}`, severity: "high",
  } };
}

/**
 * Runs the real provider with persistent hook slots and explicit effect commits.
 * Only the report API is stubbed; input/evidence conversion is the real module.
 * Browser verification remains responsible for DOM, focus and React scheduling.
 */
function mountProvider({ assess = async () => assessment(), filing = async (_, kind) => report(kind),
  document = async (_, kind) => `# ${kind} 초안` } = {}) {
  const slots = [];
  let cursor = 0, dirty = true, mounted = true, view, children = "incident-consumer";
  let pendingEffects = [];
  const calls = { assessments: [], reports: [], documents: [] };
  const api = {
    assessIncident: input => { calls.assessments.push(clone(input)); return assess(input); },
    getFilingReport: (body, kind) => { calls.reports.push({ body: clone(body), kind }); return filing(body, kind); },
    getFilingDocument: (body, kind, format) => { calls.documents.push({ body: clone(body), kind, format }); return document(body, kind, format); },
  };
  function nextSlot(kind, initialize) {
    const index = cursor++;
    if (!slots[index]) slots[index] = { kind, ...initialize() };
    assert.equal(slots[index].kind, kind, "Hook ordering changed");
    return slots[index];
  }
  const react = {
    createContext: () => ({ Provider: Symbol("Provider") }),
    useContext: () => view,
    useState(initial) {
      const slot = nextSlot("state", () => ({ value: typeof initial === "function" ? initial() : initial }));
      return [slot.value, update => {
        assert.ok(mounted, "Provider wrote state after unmount");
        const next = typeof update === "function" ? update(slot.value) : update;
        if (!Object.is(next, slot.value)) { slot.value = next; dirty = true; }
      }];
    },
    useRef(initial) { return nextSlot("ref", () => ({ ref: { current: initial } })).ref; },
    useEffect(effect, dependencies) {
      const slot = nextSlot("effect", () => ({ dependencies: undefined, cleanup: undefined }));
      if (!dependencies || !slot.dependencies || dependencies.some((value, index) => !Object.is(value, slot.dependencies[index]))) {
        slot.dependencies = dependencies;
        pendingEffects.push(() => { slot.cleanup?.(); slot.cleanup = effect(); });
      }
    },
  };
  const jsx = (type, props) => ({ type, props });
  const { IncidentProvider, useIncident } = loadSource("src/components/incident-provider.tsx", {
    react, "react/jsx-runtime": { jsx, jsxs: jsx }, "@/lib/api": api, "@/lib/incident": domain,
  });
  function Consumer() { return useIncident(); }
  function flush() {
    let commits = 0;
    while (dirty) {
      assert.ok(commits++ < 30, "Provider did not settle after effect flushing");
      dirty = false; cursor = 0;
      view = IncidentProvider({ children }).props.value;
      const effects = pendingEffects; pendingEffects = [];
      for (const effect of effects) effect();
    }
    return view;
  }
  flush();
  return { calls, flush, get value() { return view; },
    async assess() { const running = view.assess(); flush(); await running; flush(); },
    async generate(kind, replaceEdited = false) { const running = view.generate(kind, replaceEdited); flush(); await running; flush(); },
    update(key, value) { view.updateForm(key, value); flush(); },
    toggle(item) { view.toggleEvidence(item); flush(); },
    edit(kind, markdown) { view.editDocument(kind, markdown); flush(); },
    consumer(name) { children = name; dirty = true; flush(); return Consumer(); },
    unmount() { for (const slot of slots) if (slot.kind === "effect") slot.cleanup?.(); mounted = false; },
  };
}
function fill(provider, overrides = {}) {
  const values = { discoveredAt: "2026-10-31T08:30", summary: "로그에서 직접 확인한 사실", incidentTypes: ["hacking"],
    incidentStatus: "contained", filingType: "initial", leakState: "suspected", subjectsNotified: "no", ...overrides };
  for (const [key, value] of Object.entries(values)) provider.update(key, value);
}

let checks = 0;
async function check(name, callback) { await callback(); checks++; console.log(`PASS ${name}`); }

await check("Blank incident form and render make no API requests", async () => {
  const provider = mountProvider();
  assert.equal(provider.value.form.discoveredAt, "");
  assert.equal(provider.value.form.leakState, "unknown");
  assert.equal(provider.value.form.incidentStatus, "unknown");
  assert.equal(provider.value.form.filingType, "unknown");
  assert.equal(provider.value.assessment, null);
  assert.equal(Object.keys(provider.value.documents).length, 0);
  assert.equal(provider.calls.assessments.length, 0);
  await provider.assess(); await provider.generate("incident_24h"); await provider.generate("privacy_72h");
  assert.equal(provider.calls.assessments.length, 0); assert.equal(provider.calls.reports.length, 0); assert.equal(provider.calls.documents.length, 0);
  assert.ok(provider.value.errors.assessment); assert.ok(provider.value.errors.incident_24h); assert.ok(provider.value.errors.privacy_72h);
  assert.equal(provider.value.step, 0);
  provider.unmount();
});

await check("Explicit assessment uses real KST mapping and advances only after success", async () => {
  const pending = deferred();
  const provider = mountProvider({ assess: () => pending.promise });
  fill(provider, { leakState: "unknown", subjectsNotified: "unknown", incidentStatus: "unknown", filingType: "unknown" });
  const running = provider.value.assess(); provider.flush();
  assert.equal(provider.value.step, 0); assert.equal(provider.value.busy.assessment, true);
  assert.equal(provider.calls.assessments[0].discovered_at, "2026-10-31T08:30:00+09:00");
  assert.equal(provider.calls.assessments[0].summary, "로그에서 직접 확인한 사실");
  assert.equal(provider.calls.assessments[0].personal_info, null);
  assert.ok(!("status" in provider.calls.assessments[0]));
  assert.ok(!("is_supplement" in provider.calls.assessments[0]));
  assert.ok(!("incident" in provider.calls.assessments[0]));
  pending.resolve(assessment()); await running; provider.flush();
  assert.equal(provider.value.step, 1); assert.equal(provider.value.busy.assessment, false);
  assert.equal(provider.value.assessment.revision, provider.value.revision);
  provider.unmount();
});

await check("Assessment failures retain facts and support retry", async () => {
  let attempt = 0;
  const provider = mountProvider({ assess: async () => { if (++attempt === 1) throw new Error("연결 실패"); return assessment(); } });
  fill(provider);
  await provider.assess();
  assert.match(provider.value.errors.assessment, /연결 실패/); assert.equal(provider.value.busy.assessment, false);
  assert.equal(provider.value.form.summary, "로그에서 직접 확인한 사실"); assert.equal(provider.value.assessment, null);
  await provider.assess(); assert.equal(provider.calls.assessments.length, 2); assert.equal(provider.value.errors.assessment, "");
  assert.equal(provider.value.step, 1);
  provider.unmount();
});

await check("Duplicate assessment calls share one pending request", async () => {
  const pending = deferred();
  const provider = mountProvider({ assess: () => pending.promise }); fill(provider);
  const first = provider.value.assess();
  await provider.value.assess(); provider.flush();
  assert.equal(provider.calls.assessments.length, 1); assert.equal(provider.value.busy.assessment, true);
  pending.resolve(assessment()); await first; provider.flush();
  assert.equal(provider.value.busy.assessment, false);
  provider.unmount();
});

await check("Changed facts invalidate old assessment without clearing a newer request", async () => {
  const old = deferred(), current = deferred();
  const provider = mountProvider({ assess: () => provider.calls.assessments.length === 1 ? old.promise : current.promise });
  fill(provider);
  const first = provider.value.assess(); provider.flush();
  provider.update("summary", "새로 확인한 사실");
  assert.equal(provider.value.busy.assessment, false);
  const second = provider.value.assess(); provider.flush();
  old.resolve(assessment()); await first; provider.flush();
  assert.equal(provider.value.assessment, null); assert.equal(provider.value.busy.assessment, true);
  assert.equal(provider.calls.assessments[1].summary, "새로 확인한 사실");
  current.resolve(assessment()); await second; provider.flush();
  assert.equal(provider.value.assessment.revision, provider.value.revision); assert.equal(provider.value.busy.assessment, false);
  provider.unmount();
});

await check("Privacy drafts require explicit leak and notification facts", async () => {
  for (const leakState of ["unknown", "none", "suspected", "confirmed"]) {
    const provider = mountProvider(); fill(provider, { leakState, subjectsNotified: "unknown" });
    await provider.generate("privacy_72h");
    assert.equal(provider.calls.reports.length, 0, `${leakState}: unknown notification must not become not notified`);
    assert.equal(provider.calls.documents.length, 0); assert.ok(provider.value.errors.privacy_72h);
    provider.unmount();
  }
  for (const leakState of ["suspected", "confirmed"]) for (const subjectsNotified of ["yes", "no"]) {
    const provider = mountProvider(); fill(provider, { leakState, subjectsNotified });
    await provider.generate("privacy_72h");
    assert.equal(provider.calls.reports.length, 1); assert.equal(provider.calls.documents.length, 1);
    assert.equal(provider.calls.reports[0].body.incident.personal_info.subjects_notified, subjectsNotified === "yes");
    assert.ok(provider.value.documents.privacy_72h);
    provider.unmount();
  }
});

await check("Every draft requires known response status and initial or supplementary filing history", async () => {
  for (const kind of ["incident_24h", "privacy_72h"]) {
    for (const choices of [{ incidentStatus: "unknown", filingType: "unknown" }, { incidentStatus: "unknown", filingType: "initial" },
      { incidentStatus: "contained", filingType: "unknown" }]) {
      const provider = mountProvider(); fill(provider, choices);
      await provider.generate(kind);
      assert.equal(provider.calls.reports.length, 0, `${kind}: missing facts must not become ongoing or first filing`);
      assert.equal(provider.calls.documents.length, 0); assert.ok(provider.value.errors[kind]);
      provider.unmount();
    }
    const provider = mountProvider(); fill(provider, { incidentStatus: "recovered", filingType: "supplement" });
    await provider.generate(kind);
    assert.equal(provider.calls.reports.length, 1);
    assert.equal(provider.calls.reports[0].body.incident.status, "recovered");
    assert.equal(provider.calls.reports[0].body.incident.is_supplement, true);
    assert.equal(provider.calls.documents[0].body.incident.status, "recovered");
    assert.equal(provider.calls.documents[0].body.incident.is_supplement, true);
    provider.unmount();
  }
});

await check("Duplicate filing requests are blocked for each kind", async () => {
  for (const kind of ["incident_24h", "privacy_72h"]) {
    const pendingReport = deferred(), pendingMarkdown = deferred();
    const provider = mountProvider({ filing: () => pendingReport.promise, document: () => pendingMarkdown.promise }); fill(provider);
    const first = provider.value.generate(kind); await provider.value.generate(kind); provider.flush();
    assert.equal(provider.calls.reports.length, 1); assert.equal(provider.calls.documents.length, 1); assert.equal(provider.value.busy[kind], true);
    pendingReport.resolve(report(kind)); pendingMarkdown.resolve(`# ${kind} 첫 초안`); await first; provider.flush();
    assert.equal(provider.value.busy[kind], false); assert.equal(provider.value.documents[kind].markdown, `# ${kind} 첫 초안`);
    assert.equal(provider.value.documents[kind].revision, provider.value.revision);
    provider.unmount();
  }
});

await check("Each filing progresses independently and later failure retains the successful kind", async () => {
  const firstReport = deferred(), firstMarkdown = deferred(), secondReport = deferred();
  const provider = mountProvider({ filing: (_, kind) => kind === "incident_24h" ? firstReport.promise : secondReport.promise,
    document: (_, kind) => kind === "incident_24h" ? firstMarkdown.promise : Promise.resolve("# 개인정보 초안") }); fill(provider);
  const incident = provider.value.generate("incident_24h"); provider.flush();
  const privacy = provider.value.generate("privacy_72h"); provider.flush();
  assert.equal(provider.value.busy.incident_24h, true); assert.equal(provider.value.busy.privacy_72h, true);
  firstReport.resolve(report("incident_24h")); firstMarkdown.resolve("# 먼저 완성된 침해사고 초안"); await incident; provider.flush();
  const successful = provider.value.documents.incident_24h;
  assert.ok(successful); assert.equal(provider.value.busy.incident_24h, false); assert.equal(provider.value.busy.privacy_72h, true);
  secondReport.reject(new Error("개인정보 문서 연결 실패")); await privacy; provider.flush();
  assert.equal(provider.value.documents.incident_24h, successful); assert.equal(provider.value.documents.privacy_72h, undefined);
  assert.match(provider.value.errors.privacy_72h, /연결 실패/); assert.equal(provider.value.errors.incident_24h, "");
  assert.equal(provider.value.busy.privacy_72h, false);
  provider.unmount();
});

await check("Partial report/Markdown failure never publishes an incomplete document", async () => {
  const provider = mountProvider({ document: async () => { throw new Error("문서 다운로드 형식 오류"); } }); fill(provider);
  await provider.generate("incident_24h");
  assert.equal(provider.value.documents.incident_24h, undefined); assert.match(provider.value.errors.incident_24h, /형식 오류/);
  assert.equal(provider.value.busy.incident_24h, false);
  provider.unmount();
});

await check("Manual edits survive normal generation and only explicit replacement can overwrite them", async () => {
  let generation = 0;
  const provider = mountProvider({ document: async () => `# 생성 ${++generation}` }); fill(provider);
  await provider.generate("incident_24h"); provider.edit("incident_24h", "# 사용자가 보완한 사실");
  const edited = provider.value.documents.incident_24h;
  await provider.generate("incident_24h");
  assert.equal(provider.calls.reports.length, 1); assert.equal(provider.calls.documents.length, 1);
  assert.equal(provider.value.documents.incident_24h, edited); assert.equal(provider.value.documents.incident_24h.edited, true);
  await provider.generate("incident_24h", true);
  assert.equal(provider.calls.reports.length, 2); assert.equal(provider.value.documents.incident_24h.markdown, "# 생성 2");
  assert.equal(provider.value.documents.incident_24h.edited, false);
  provider.unmount();
});

await check("Editing during replacement invalidates its late response", async () => {
  const pendingReport = deferred(), pendingMarkdown = deferred();
  let delayed = false;
  const provider = mountProvider({ filing: (_, kind) => delayed ? pendingReport.promise : Promise.resolve(report(kind)),
    document: async () => delayed ? pendingMarkdown.promise : "# 최초 생성" }); fill(provider);
  await provider.generate("incident_24h"); provider.edit("incident_24h", "# 첫 사용자 편집");
  delayed = true;
  const running = provider.value.generate("incident_24h", true); provider.flush();
  assert.equal(provider.value.busy.incident_24h, true);
  provider.edit("incident_24h", "# 요청 중 추가로 보완한 사실");
  assert.equal(provider.value.busy.incident_24h, false);
  pendingReport.resolve(report("incident_24h")); pendingMarkdown.resolve("# 늦게 도착한 자동 문서"); await running; provider.flush();
  assert.equal(provider.value.documents.incident_24h.markdown, "# 요청 중 추가로 보완한 사실");
  assert.equal(provider.value.documents.incident_24h.edited, true);
  provider.unmount();
});

await check("Changed facts retain a prior document snapshot and reject an outdated replacement", async () => {
  let delayed = false;
  const pendingReport = deferred(), pendingMarkdown = deferred();
  const provider = mountProvider({ filing: (_, kind) => delayed ? pendingReport.promise : Promise.resolve(report(kind)),
    document: () => delayed ? pendingMarkdown.promise : Promise.resolve("# 이전 사실로 만든 초안") }); fill(provider);
  await provider.generate("incident_24h");
  const previous = provider.value.documents.incident_24h;
  delayed = true;
  const running = provider.value.generate("incident_24h"); provider.flush();
  provider.update("summary", "입력 내용이 변경됨");
  pendingReport.resolve(report("incident_24h")); pendingMarkdown.resolve("# 오래된 입력 결과"); await running; provider.flush();
  assert.equal(provider.value.documents.incident_24h, previous);
  assert.ok(previous.revision < provider.value.revision);
  assert.equal(previous.body.incident.summary, "로그에서 직접 확인한 사실");
  assert.equal(provider.value.busy.incident_24h, false);
  provider.unmount();
});

await check("Only explicitly selected raw fingerprints reach filing requests", async () => {
  const provider = mountProvider(); fill(provider);
  const chosen = evidence("actual-raw-fingerprint", "one"), removed = evidence("not-selected", "two");
  provider.toggle(chosen); provider.toggle(removed); provider.toggle(removed);
  await provider.generate("incident_24h");
  const body = provider.calls.reports[0].body;
  assert.deepEqual(body.findings, [chosen.finding]);
  assert.deepEqual(body.incident.related_fingerprints, ["actual-raw-fingerprint"]);
  assert.equal(body.incident.cause, null);
  assert.deepEqual(provider.calls.documents[0].body, body); assert.equal(provider.calls.documents[0].format, "markdown");
  provider.unmount();
});

await check("Evidence changes invalidate late assessments and documents", async () => {
  const pendingAssessment = deferred(), pendingReport = deferred(), pendingMarkdown = deferred();
  const provider = mountProvider({ assess: () => pendingAssessment.promise, filing: () => pendingReport.promise, document: () => pendingMarkdown.promise }); fill(provider);
  const assessmentRequest = provider.value.assess(); const filingRequest = provider.value.generate("incident_24h"); provider.flush();
  provider.toggle(evidence());
  pendingAssessment.resolve(assessment()); pendingReport.resolve(report("incident_24h")); pendingMarkdown.resolve("# 이전 근거로 만든 초안");
  await Promise.all([assessmentRequest, filingRequest]); provider.flush();
  assert.equal(provider.value.assessment, null); assert.equal(provider.value.documents.incident_24h, undefined);
  assert.equal(provider.value.busy.assessment, false); assert.equal(provider.value.busy.incident_24h, false);
  assert.equal(provider.value.evidence.length, 1);
  provider.unmount();
});

await check("Selection bounds and malformed findings cannot silently reach the API", async () => {
  const provider = mountProvider(); fill(provider);
  for (let index = 0; index < 51; index++) provider.toggle(evidence(`finding-${index}`, String(index)));
  assert.equal(provider.value.evidence.length, 50);
  await provider.generate("incident_24h");
  assert.equal(provider.calls.reports[0].body.findings.length, 50);
  provider.unmount();
  const malformed = mountProvider(); fill(malformed);
  malformed.toggle({ repo, fingerprint: "malformed", title: "잘못된 검사 항목", finding: { fingerprint: "malformed" } });
  await malformed.generate("incident_24h");
  assert.equal(malformed.calls.reports.length, 0); assert.ok(malformed.value.errors.incident_24h);
  malformed.unmount();
});

await check("Consumer navigation preserves the provider's facts, step, evidence and edited documents", async () => {
  const provider = mountProvider(); fill(provider); provider.toggle(evidence());
  await provider.assess(); await provider.generate("incident_24h"); provider.edit("incident_24h", "# 화면 이동 전 편집");
  provider.value.setStep(2); provider.flush();
  const before = provider.value;
  const help = provider.consumer("help-consumer");
  const returned = provider.consumer("incident-consumer");
  assert.equal(help.form, before.form); assert.equal(returned.form, before.form);
  assert.equal(returned.evidence, before.evidence); assert.equal(returned.step, 2);
  assert.equal(returned.documents.incident_24h.markdown, "# 화면 이동 전 편집");
  assert.equal(provider.calls.assessments.length, 1); assert.equal(provider.calls.reports.length, 1);
  provider.unmount();
});

await check("Late API responses cannot update an unmounted provider", async () => {
  const pendingAssessment = deferred(), pendingReport = deferred(), pendingMarkdown = deferred();
  const provider = mountProvider({ assess: () => pendingAssessment.promise, filing: () => pendingReport.promise, document: () => pendingMarkdown.promise }); fill(provider);
  const assessmentRequest = provider.value.assess(), filingRequest = provider.value.generate("incident_24h"); provider.flush();
  provider.unmount();
  pendingAssessment.resolve(assessment()); pendingReport.resolve(report("incident_24h")); pendingMarkdown.resolve("# 완료");
  await Promise.all([assessmentRequest, filingRequest]);
});

console.log(`Verified ${checks} incident provider scenarios. Real input/evidence mapping with local report API fixtures; no external scan or incident submission was performed.`);
