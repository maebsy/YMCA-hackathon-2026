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

test('explanations omit environment and malformed responses fail clearly', async () => {
  const original = global.fetch;
  let payload;
  global.fetch = async (_, options) => {
    payload = JSON.parse(options.body);
    return {ok:true, json:async()=>({})};
  };
  try {
    await assert.rejects(explain([{}]), /LLM/);
    assert.deepEqual(payload, {findings:[{}], mode:'red_blue'});
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
    assert.deepEqual(await explain([{}]), results);
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
      await assert.rejects(explain([{}]), expired ? /만료/ : /GPU 오류/);
    }
  } finally { global.fetch = original; }
});

// ── #59: GPU 해석을 백엔드 동시 실행 수만큼 함께 보내기 ──
const {runLimited, LLM_PARALLEL} = loaded.exports;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

test('runLimited never exceeds the limit and finishes every item', async () => {
  let active = 0, peak = 0;
  const seen = [];
  await runLimited([30, 10, 20, 5, 15], async ms => {
    active += 1; peak = Math.max(peak, active);
    await sleep(ms);
    active -= 1;
    return ms;
  }, (i, outcome) => seen.push([i, outcome.value]), 2);
  assert.equal(peak, 2);
  assert.deepEqual(seen.map(([i]) => i).sort(), [0, 1, 2, 3, 4]);
});

test('runLimited reports each result as soon as it finishes, not in input order', async () => {
  const order = [];
  await runLimited([40, 5], async ms => { await sleep(ms); return ms; }, i => order.push(i), 2);
  assert.deepEqual(order, [1, 0]);
});

test('a failed item does not stop the others', async () => {
  const outcomes = [];
  await runLimited(['a', 'boom', 'c'], async x => {
    if (x === 'boom') throw new Error('GPU error');
    return x.toUpperCase();
  }, (i, outcome) => outcomes[i] = outcome, 2);
  assert.deepEqual(outcomes.map(o => o.ok), [true, false, true]);
  assert.equal(outcomes[0].value, 'A');
  assert.match(outcomes[1].error.message, /GPU error/);
});

test('invalid or large limits stay bounded', async () => {
  for (const [limit, expected] of [[0, 1], [-3, 1], [10, 3]]) {
    let active = 0, peak = 0;
    await runLimited([1, 1, 1], async () => { active += 1; peak = Math.max(peak, active); await sleep(5); active -= 1; },
      () => {}, limit);
    assert.equal(peak, expected, `limit ${limit}`);
  }
  let called = false;
  await runLimited([], async () => { called = true; }, () => {});
  assert.equal(called, false);
});

test('frontend asks for all top findings at once without exceeding backend running slots', () => {
  // 한 사용자의 상위 5건이 자기 요청 뒤에 줄 서지 않게 한 번에 보내되, 서버 전체 동시 실행 수(#145)는 넘지 않습니다
  const config = fs.readFileSync(path.join(__dirname, '../../backend/app/config.py'), 'utf8');
  const queue = fs.readFileSync(path.join(__dirname, '../../backend/app/llm/preview_jobs.py'), 'utf8');
  const configured = Number(/llm_parallel_jobs: int = (\d+)/.exec(config)?.[1]);
  const fallback = Number(/running=(\d+)/.exec(queue)?.[1]);
  assert.equal(LLM_PARALLEL, 5);
  assert.ok(LLM_PARALLEL <= configured && configured === fallback, `${LLM_PARALLEL} <= ${configured} == ${fallback}`);
});
