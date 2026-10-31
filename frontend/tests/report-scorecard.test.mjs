import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";
const loaded = { exports: {} };
vm.runInNewContext(ts.transpileModule(readFileSync(new URL("../src/lib/report-scorecard.ts", import.meta.url),"utf8"), { compilerOptions:{ module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022 } }).outputText, { module:loaded,exports:loaded.exports });
const { scoreRows, claimScorecardAnimation, stampDuration } = loaded.exports;

test("scorecard uses raw report severity, classification, tool and source coordinates with SSVC tie ordering", () => {
  const base = { category:"code", rule_id:"sql.rule", tool:"semgrep", file_path:"src/db.ts", start_line:42, title:"Engine title", refs:{ cwe:["CWE-89"] } };
  const raw = [ { ...base,fingerprint:"a",severity:"high" }, { ...base,fingerprint:"b",severity:"critical" }, { ...base,fingerprint:"c",severity:"high" } ];
  const rows = scoreRows(raw,[{ id:"a",decision:"attend",title:"쉬운 제목" },{ id:"c",decision:"act",fixed:true }],["a"]);
  assert.deepEqual(Array.from(rows,row=>row.id),["b","c","a"]);
  assert.equal(rows[0].rule,"sql.rule"); assert.equal(rows[0].fullLocation,"src/db.ts:42");
  assert.equal(rows[0].severity,"critical"); assert.equal(rows[0].kind,"SQL 인젝션");
  assert.equal(rows[0].tool,"Semgrep"); assert.equal(rows[0].location,"db.ts:42");
  assert.equal(rows[1].action,"해결 확인"); assert.equal(rows[2].action,"재검증 대기"); assert.equal(rows[2].title,"쉬운 제목");
});
test("unknown data stays unknown; missing columns are dashes rather than fabricated engine values", () => {
  const rows = scoreRows([{ fingerprint:"empty",severity:"unrecognized" }],[],[]);
  assert.equal(rows[0].severity,"unknown");
  for(const field of ["kind","tool","location","title"]) assert.equal(rows[0][field],"—");
  const partial = scoreRows([{ fingerprint:"partial",severity:"info",category:"dependency",rule_id:"CVE-2026-1234",tool:"osv",file_path:"package-lock.json" }],[],[])[0];
  assert.equal(partial.severity,"info"); assert.equal(partial.location,"package-lock.json"); assert.equal(partial.kind,"외부 부품(라이브러리)");
  assert.equal(scoreRows([],[],[]).length,0);
});
test("stamp timing is bounded under 2.5 seconds and automatic replay is claimed once per fresh result", () => {
  assert.ok(stampDuration(10)<2500); assert.equal(stampDuration(300),stampDuration(10));
  assert.equal(stampDuration(0),450);
  assert.equal(claimScorecardAnimation("restored",false),false);
  assert.equal(claimScorecardAnimation("fresh",true),true); assert.equal(claimScorecardAnimation("fresh",true),false);
});

test("engine aliases and Windows source paths use display labels while preserving full locations", () => {
  for (const [tool, expected] of [["semgrep","Semgrep"],["opengrep","Semgrep"],["gitleaks","Gitleaks"],["osv","OSV-Scanner"],["osv-scanner","OSV-Scanner"],["custom-engine","custom-engine"]]) {
    const row=scoreRows([{tool,file_path:"src\\nested\\file.ts",start_line:8}],[],[])[0];
    assert.equal(row.tool,expected); assert.equal(row.location,"file.ts:8"); assert.equal(row.fullLocation,"src\\nested\\file.ts:8");
  }
});
