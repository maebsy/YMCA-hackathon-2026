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
const doneJob = {job_id: 'a'.repeat(32), status: 'done', result, error: null, target: 'demo',
  attacks: [{id: 'sqli-orders', cwe: 'CWE-89', runtime: true, request: {method: 'GET', path: '/api/orders', query: {orderId: '0 OR 1=1'}}},
    {id: 'jwt-hardcoded', cwe: 'CWE-798', runtime: false}],
  patched_files: ['server.js'], patch_diff: '--- a/server.js\n+++ b/server.js\n'};

test('a finished job keeps the result, attack definitions and diff', () => {
  const job = parseVerifyJob(doneJob);
  assert.equal(job.result.status, 'verified');
  assert.equal(job.attacks.length, 2);
  assert.deepEqual(job.patched_files, ['server.js']);
});

test('a finished job with a malformed result is rejected instead of breaking the screen', () => {
  assert.equal(parseVerifyJob({...doneJob, result: {...result, attacks: [{id: 'x'}]}}), null);
  assert.equal(parseVerifyJob({...doneJob, result: {...result, status: 'maybe'}}), null);
  assert.equal(parseVerifyJob({...doneJob, result: {...result, before_tests: null}}), null);
  assert.equal(parseVerifyJob({status: 'done'}), null);
});

test('a running job needs no result', () => {
  assert.equal(parseVerifyJob({job_id: 'b', status: 'running', result: null, error: null}).status, 'running');
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
  const calls = fakeFetch([[202, {job_id: 'j1', status: 'queued'}], [200, {job_id: 'j1', status: 'running'}], [200, doneJob]]);
  const seen = [];
  const job = await runVerify({intervalMs: 0, onStatus: s => seen.push(s)});
  assert.equal(job.result.status, 'verified');
  assert.deepEqual(JSON.parse(calls[0].body), {target: 'demo'});
  assert.equal(calls[0].method, 'POST');
  assert.equal(calls[1].url, '/api/verify/j1');
  assert.deepEqual(seen, ['queued', 'running']);
});

test('runVerify shows the server message when the server cannot run it', async () => {
  fakeFetch([[503, {detail: {code: 'VERIFY_UNAVAILABLE', message: '이 서버에는 실검증을 실행할 환경(Docker 또는 Node 22.5 이상)이 없습니다.'}}]]);
  await assert.rejects(runVerify({intervalMs: 0}), /Docker 또는 Node/);
});

test('runVerify reports a failed job with its message', async () => {
  fakeFetch([[202, {job_id: 'j2', status: 'queued'}], [200, {job_id: 'j2', status: 'failed', error: {code: 'VERIFY_ERROR', message: '실검증 실행 중 오류가 났습니다.'}}]]);
  await assert.rejects(runVerify({intervalMs: 0}), /실검증 실행 중 오류/);
});
