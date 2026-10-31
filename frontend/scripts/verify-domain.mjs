import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../src/lib/sample.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { findings, repairRequest, reportMarkdown, validateWebsite, SAMPLE_SITE, SAMPLE_REPO } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

const cases = [
  ["https://example.com", "https://example.com/"],
  ["example.com", "https://example.com/"],
  ["  my-service.vercel.app  ", "https://my-service.vercel.app/"],
  ["HTTP://EXAMPLE.COM/hello", "http://example.com/hello"],
  ["https://example.com:8443/path", "https://example.com:8443/path"],
  ["https://예시.한국/경로", "https://xn--vv4b11d.xn--3e0b707e/%EA%B2%BD%EB%A1%9C"],
  ["https://tiny-shop.example", "https://tiny-shop.example/"],
  ["", null], ["hello", null], ["localhost", null], ["https://localhost", null],
  ["https://127.0.0.1", null], ["https://192.168.1.1", null], ["https://[::1]", null],
  ["https://0x7f000001", null], ["https://2130706433", null], ["https://service.local", null],
  ["https://service.internal", null], ["https://service.localhost", null],
  ["https://user:secret@example.com", null], ["https://@example.com", null],
  ["https://example.com?token=secret", null], ["https://example.com#secret", null],
  ["https://example.com?", null], ["https://example.com#", null],
  ["https://exa mple.com", null], ["https://example.com/line\nbreak", null],
  ["https://example.com/\u0000", null], ["https://example.com\\path", null],
  ["javascript:alert(1)", null], ["data:text/html,hello", null], ["ftp://example.com", null],
  ["//example.com", null], ["https:///example.com", null], ["https://-bad.example.com", null],
  ["https://example..com", null], ["https://example.com:99999", null],
];
for (const [input, expected] of cases) assert.equal(validateWebsite(input), expected, `URL: ${input}`);
const states = [[], ["SEC-002"], findings.map(f => f.id), ["SEC-002", "SEC-002", "unknown"]];
for (const marked of states) {
  const pending = findings.filter(f => marked.includes(f.id)).length;
  const report = reportMarkdown(marked, "https://user-service.example/");
  assert.ok(report.includes(SAMPLE_SITE) && report.includes(SAMPLE_REPO));
  assert.ok(report.includes("입력한 URL을 분석한 결과가 아닙니다"));
  assert.ok(report.includes(`미조치 ${4 - pending}건 · 재검증 대기 ${pending}건 · 검증 완료 0건`));
  assert.equal((report.match(/^## SEC-/gm) || []).length, 4);
  for (const finding of findings) assert.ok(report.includes(finding.verify) && report.includes(finding.location));
}
for (const finding of findings) {
  const request = repairRequest(finding);
  assert.ok(request.includes(SAMPLE_SITE) && request.includes(SAMPLE_REPO));
  assert.ok(request.includes("실제 사용자 사이트의 검사 결과가 아닙니다"));
  assert.ok(request.includes(finding.verify));
  for (const step of finding.steps) assert.ok(request.includes(step));
  assert.ok(!request.includes("https://user-service.example/"));
}
console.log(JSON.stringify({ urlCases: cases.length, reportStates: states.length, repairRequests: findings.length, assertions: "passed" }));
