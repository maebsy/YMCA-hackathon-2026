import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/lib/verify.ts'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;
const loaded = {exports: {}};
new Function('require', 'module', 'exports', compiled)(createRequire(import.meta.url), loaded, loaded.exports);
const {parseVerifyJob, requestLine, testsLabel, runVerify} = loaded.exports;

const result = {
  status: 'verified', message: '모든 공격이 수정 후 차단되고 기능 테스트를 통과했습니다.', sandbox: 'local',
  isolation: {network_isolated: false, non_root: null, caps_dropped: null, no_new_privs: null}, isolation_confirmed: false,
  attacks: [{id: 'sqli-orders', before_succeeded: true, after_succeeded: false, before_status: 200, after_status: 200,
    before_evidence: '[{"id":1},{"id":2}]', after_evidence: '[]', verdict: 'verified'}],
  before_tests: {ok: true, passed: 3, failed: 0}, after_tests: {ok: true, passed: 3, failed: 0}, duration_sec: 9.3,
};
const doneJob = {job_id: 'a'.repeat(32), status: 'done', reused: false, finished_at: '2026-10-31T03:04:05+00:00', result, error: null, target: 'demo',
  attacks: [{id: 'sqli-orders', cwe: 'CWE-89', runtime: true, request: {method: 'GET', path: '/api/orders', query: {orderId: '0 OR 1=1'}}},
    {id: 'jwt-hardcoded', cwe: 'CWE-798', runtime: false}],
  patched_files: ['server.js'], patch_diff: '--- a/server.js\n+++ b/server.js\n'};

test('a finished job keeps the result, attack definitions and diff', () => {
  const job = parseVerifyJob(doneJob);
  assert.equal(job.result.status, 'verified');
  assert.equal(job.attacks.length, 2);
  assert.deepEqual(job.patched_files, ['server.js']);
});

test('reuse metadata keeps the original completion time and validates its types', () => {
  const job = parseVerifyJob({...doneJob, reused: true});
  assert.equal(job.reused, true);
  assert.equal(job.finished_at, doneJob.finished_at);
  assert.equal(parseVerifyJob(doneJob).reused, false);
  assert.equal(parseVerifyJob({...doneJob, reused: 'true'}), null);
  assert.equal(parseVerifyJob({...doneJob, reused: undefined}), null);
  assert.equal(parseVerifyJob({...doneJob, finished_at: 123}), null);
  assert.equal(parseVerifyJob({...doneJob, finished_at: 'not-a-date'}), null);
});

test('a finished job with a malformed result is rejected instead of breaking the screen', () => {
  assert.equal(parseVerifyJob({...doneJob, result: {...result, attacks: [{id: 'x'}]}}), null);
  assert.equal(parseVerifyJob({...doneJob, result: {...result, status: 'maybe'}}), null);
  assert.equal(parseVerifyJob({...doneJob, result: {...result, before_tests: null}}), null);
  assert.equal(parseVerifyJob({status: 'done'}), null);
});

test('a running job needs no result', () => {
  const job = parseVerifyJob({job_id: 'b', status: 'running', reused: false, result: null, error: null});
  assert.equal(job.status, 'running');
  assert.equal(job.reused, false);
  assert.equal(job.finished_at, undefined);
});

test('attack request is shown as people read it', () => {
  assert.equal(requestLine(doneJob.attacks[0].request), 'GET /api/orders?orderId=0 OR 1=1');
  assert.equal(requestLine({path: '/search'}), 'GET /search');
});

test('test counts read as passed out of total', () => {
  assert.equal(testsLabel({ok: true, passed: 3, failed: 0}), '3/3 통과');
  assert.equal(testsLabel({ok: false, passed: 2, failed: 1}), '1건 실패 (2/3 통과)');
  assert.equal(testsLabel({ok: true, passed: null, failed: null}), '통과');
  assert.equal(testsLabel({ok: null, passed: null, failed: null}), '실행 결과 없음');
});

function fakeFetch(responses) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({url, method: init.method ?? 'GET', body: init.body});
    const [status, body] = responses.shift();
    return {ok: status < 400, status, json: async () => body};
  };
  return calls;
}

test('runVerify submits the demo target and polls until done', async () => {
  const calls = fakeFetch([[202, {job_id: 'j1', status: 'queued'}], [200, {job_id: 'j1', status: 'running', reused: false}], [200, doneJob]]);
  const seen = [];
  const job = await runVerify({intervalMs: 0, onStatus: s => seen.push(s)});
  assert.equal(job.result.status, 'verified');
  assert.deepEqual(JSON.parse(calls[0].body), {target: 'demo', mode: 'reference'});
  assert.equal(calls[0].method, 'POST');
  assert.equal(calls[1].url, '/api/verify/j1');
  assert.deepEqual(seen, ['queued', 'running']);
});

test('runVerify fetches an already finished POST once without waiting for a timer', async t => {
  const reusedJob = {...doneJob, reused: true};
  const calls = fakeFetch([[202, {job_id: reusedJob.job_id, status: 'done', reused: true}], [200, reusedJob]]);
  t.mock.method(globalThis, 'setTimeout', () => { throw new Error('a reused result must not wait'); });
  const seen = [];
  const job = await runVerify({onStatus: s => seen.push(s)});
  assert.equal(job.reused, true);
  assert.equal(job.finished_at, doneJob.finished_at);
  assert.deepEqual(calls.map(({method, url}) => [method, url]), [['POST', '/api/verify'], ['GET', `/api/verify/${reusedJob.job_id}`]]);
  assert.deepEqual(seen, []);
});

test('runVerify shows the server message when the server cannot run it', async () => {
  fakeFetch([[503, {detail: {code: 'VERIFY_UNAVAILABLE', message: '이 서버에는 실제검증을 실행할 환경(Docker 또는 Node 22.5 이상)이 없습니다.'}}]]);
  await assert.rejects(runVerify({intervalMs: 0}), /Docker 또는 Node/);
});

test('runVerify reports a failed job with its message', async () => {
  fakeFetch([[202, {job_id: 'j2', status: 'queued'}], [200, {job_id: 'j2', status: 'failed', reused: false, error: {code: 'VERIFY_ERROR', message: '실제검증 실행 중 오류가 났습니다.'}}]]);
  await assert.rejects(runVerify({intervalMs: 0}), /실제검증 실행 중 오류/);
});

test('ai mode keeps Red reasons, Blue summaries and skipped items; old responses default to reference', () => {
  const job = parseVerifyJob({...doneJob, target: 'demo-ai', mode: 'ai', ai: {
    attack_fingerprints: {a: 'f'}, red_reasons: {'sqli-orders': '조건이 항상 참', bad: 3},
    patch_summaries: {'server.js': '자리표시자로 고침'},
    skipped: [{fingerprint: 'demo:x', stage: 'blue', reason: '범위 밖'}, {stage: 'red'}]}});
  assert.equal(job.mode, 'ai');
  assert.deepEqual(job.ai.red_reasons, {'sqli-orders': '조건이 항상 참'});
  assert.deepEqual(job.ai.patch_summaries, {'server.js': '자리표시자로 고침'});
  assert.equal(job.ai.skipped.length, 1);
  const old = parseVerifyJob(doneJob);
  assert.equal(old.mode, 'reference');
  assert.equal(old.ai, null);
});

test('runVerify sends the chosen mode', async () => {
  const sent = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    if (init?.method === 'POST') { sent.push(JSON.parse(init.body)); return new Response(JSON.stringify({job_id: 'b'.repeat(32), status: 'done', reused: true})); }
    return new Response(JSON.stringify({...doneJob, mode: 'ai'}));
  };
  try {
    const job = await runVerify({mode: 'ai', intervalMs: 0});
    assert.equal(job.mode, 'ai');
    assert.deepEqual(sent, [{target: 'demo', mode: 'ai'}]);
  } finally { globalThis.fetch = realFetch; }
});

test('a fix that breaks the app is explained as a caught bad fix, not a tool failure', () => {
  const { verdictHelp } = loaded.exports;
  const broken = {status:'fix_failed', message:'수정 후 앱이 뜨지 않았습니다: probe timeout: 앱이 제한 시간 안에 응답하지 않았습니다'};
  const ai = verdictHelp({mode:'ai', result:broken});
  assert.match(ai[0], /수정이 앱 기능을 망가뜨렸다는 뜻/);
  assert.match(ai[1], /AI\(Blue\)/);
  assert.doesNotMatch(verdictHelp({mode:'reference', result:broken})[1], /AI/);
  assert.deepEqual(verdictHelp({mode:'reference', result:{status:'verified', message:'ok'}}), []);
  assert.match(verdictHelp({mode:'ai', result:{status:'not_reproduced', message:''}})[0], /오탐/);
});

test('AI retries are listed in order and old responses without attempts still parse', () => {
  const { attemptsLine } = loaded.exports;
  const job = parseVerifyJob({...doneJob, mode:'ai', ai:{red_reasons:{}, patch_summaries:{}, skipped:[],
    attempts:[{attempt:1, status:'fix_failed', message:'수정 후 앱이 뜨지 않았습니다'}, {attempt:2, status:'verified', message:'ok'}, {attempt:'x'}]}});
  assert.equal(job.ai.attempts.length, 2);
  assert.equal(attemptsLine(job.ai), '1회차 수정 미흡 → 2회차 검증됨');
  assert.equal(attemptsLine(parseVerifyJob({...doneJob, mode:'ai', ai:{red_reasons:{}, patch_summaries:{}, skipped:[]}}).ai), '');
});
