import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/api.ts'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const loaded = {exports: {}};
new Function('require', 'module', 'exports', compiled)(createRequire(import.meta.url), loaded, loaded.exports);
const {itemToFinding, mergeExplanation, explain} = loaded.exports;
const item = {id:'osv:test', title:'Test vulnerability', severity:'unknown', status:'code_issue', kind:'dependency'};

test('unrequested findings do not claim an LLM request is still running', () => {
  assert.doesNotMatch(itemToFinding(item).redScenario, /대기 중/);
});

test('failed LLM result remains a finding and displays failure', () => {
  const original = itemToFinding(item);
  const result = mergeExplanation(original, {status:'failed', error_code:'LLM_BAD_OUTPUT'});
  assert.equal(result.id, original.id);
  assert.equal(result.fixed, false);
  assert.match(result.verdict, /실패/);
  assert.match(result.redScenario, /LLM_BAD_OUTPUT/);
});

test('SSVC priority and factors replace the severity fallback', () => {
  const result = mergeExplanation(itemToFinding(item), {status:'done', explanation:{
    summary:'Explained', risk:{decision:'act', factors:[{reason:'Publicly exploitable'}]}, red_verdict:'pass',
    fix_steps:[{title:'Upgrade', detail:'Upgrade dependency'}],
  }});
  assert.equal(result.decision, 'act');
  assert.match(result.decisionLabel, /지금 바로/);
  assert.ok(result.why.includes('Publicly exploitable'));
});

test('manual review is never shown as Red passed', () => {
  const result = mergeExplanation(itemToFinding(item), {status:'done', explanation:{
    needs_manual_review:true, red_verdict:'pass', fix_steps:[],
  }});
  assert.equal(result.verdict, '수동 확인');
  assert.equal(result.verdictType, 'warn');
});

test('environment includes the selected hosting and malformed responses fail clearly', async () => {
  const original = global.fetch;
  let payload;
  global.fetch = async (_, options) => {
    payload = JSON.parse(options.body);
    return {ok:true, json:async()=>({})};
  };
  try {
    await assert.rejects(explain([{}], 'windows', 'netlify'), /LLM/);
    assert.deepEqual(payload.environment, {os:'windows', hosting:'netlify'});
  } finally {
    global.fetch = original;
  }
});

test('LLM result is retrieved from the accepted job without holding the POST open', async () => {
  const original = global.fetch, calls = [];
  const results = [{status:'done', fingerprint:'test'}];
  global.fetch = async (url, options) => {
    calls.push({url, options});
    return {ok:true, json:async()=>calls.length === 1
      ? {job_id:'test-job', status:'queued'} : {status:'done', result:{results}}};
  };
  try {
    assert.deepEqual(await explain([{}], 'linux'), results);
    assert.equal(calls[0].url, '/api/llm/explain/tasks');
    assert.equal(calls[0].options.method, 'POST');
    assert.equal(calls[1].url, '/api/llm/explain/tasks/test-job');
    assert.equal(calls[1].options.cache, 'no-store');
  } finally { global.fetch = original; }
});

test('failed and expired LLM jobs surface the server message', async () => {
  const original = global.fetch;
  try {
    for (const expired of [false, true]) {
      let calls = 0;
      global.fetch = async () => ({ok:++calls === 1 || !expired, status:expired ? 404 : 200,
        json:async()=>calls === 1 ? {job_id:'test-job'} : expired
          ? {detail:{message:'작업이 만료됐습니다'}} : {status:'failed', error:{message:'GPU 오류'}}});
      await assert.rejects(explain([{}], 'linux'), expired ? /만료/ : /GPU 오류/);
    }
  } finally { global.fetch = original; }
});
