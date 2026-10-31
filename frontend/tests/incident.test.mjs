import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';

const directory = path.dirname(fileURLToPath(import.meta.url));
function load(relative) {
  const source = fs.readFileSync(path.join(directory, relative), 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions: {
    module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022,
  }}).outputText;
  const loaded = {exports:{}};
  new Function('require', 'module', 'exports', compiled)(createRequire(import.meta.url), loaded, loaded.exports);
  return loaded.exports;
}
const domain = load('../src/lib/incident.ts');
const api = load('../src/lib/api.ts');
const form = (changes = {}) => ({...domain.initialIncidentForm, incidentTypes:[], discoveredAt:'2026-10-31T08:30', ...changes});
const finding = (fingerprint = 'chosen') => ({fingerprint, tool:'semgrep', category:'code', rule_id:'rule', title:'Finding', severity:'high'});
const deadline = {label:'기한', basis:'API 기준', starts_at:'2026-10-31T08:30:00+09:00', due_at:'2026-11-01T08:30:00+09:00', hours:24, remaining_minutes:120, overdue:false, stopped_at:null};
const report = (kind = 'incident_24h') => ({kind, title:'신고서 초안', subtitle:null, generated_at:'2026-10-31T09:30:00+09:00', status:{text:'작성 중', tone:'warning'}, deadline,
  sections:[{heading:'확인할 사실', paragraphs:[], fields:[{label:'원인', value:null, required:true, auto:false, hint:'조사 중'}], bullets:[], steps:[], cards:[]}],
  missing:['원인'], submit_to:['공식 제출처'], disclaimer:'제출 전 확인'});
const assessment = () => ({needs:[{kind:'incident_24h', required:true, reasons:['확인한 유형'], deadline}, {kind:'privacy_72h', required:false, reasons:['추가 확인 필요'], deadline:null}]});

test('incident starts blank, preserves unknown facts, and requires an awareness time', () => {
  assert.equal(domain.initialIncidentForm.discoveredAt, '');
  assert.equal(domain.initialIncidentForm.leakState, 'unknown');
  assert.equal(domain.initialIncidentForm.incidentStatus, 'unknown');
  assert.equal(domain.initialIncidentForm.filingType, 'unknown');
  assert.throws(() => domain.buildIncidentInput({...domain.initialIncidentForm}), /인지.*시각/);
  const input = domain.buildIncidentInput(form());
  assert.equal(input.personal_info, null);
  assert.equal(input.summary, null);
  assert.deepEqual(input.actions_taken, []);
  assert.deepEqual(input.incident_types, []);
  assert.ok(!('status' in input));
  assert.ok(!('is_supplement' in input));
});

test('only confirmed response status and filing history are serialized', () => {
  for (const incidentStatus of ['ongoing', 'contained', 'recovered']) {
    for (const filingType of ['initial', 'supplement']) {
      const input = domain.buildIncidentInput(form({incidentStatus, filingType}));
      assert.equal(input.status, incidentStatus);
      assert.equal(input.is_supplement, filingType === 'supplement');
    }
  }
  const statusOnly = domain.buildIncidentInput(form({incidentStatus:'recovered'}));
  assert.equal(statusOnly.status, 'recovered');
  assert.ok(!('is_supplement' in statusOnly));
  const filingOnly = domain.buildIncidentInput(form({filingType:'supplement'}));
  assert.equal(filingOnly.is_supplement, true);
  assert.ok(!('status' in filingOnly));
});

test('invalid response status or filing history is rejected rather than defaulted', () => {
  for (const incidentStatus of ['', 'resolved', 'initial', null, undefined]) {
    assert.throws(() => domain.buildIncidentInput(form({incidentStatus})), /사고 대응 상태/);
  }
  for (const filingType of ['', 'first', 'ongoing', null, undefined]) {
    assert.throws(() => domain.buildIncidentInput(form({filingType})), /신고 여부/);
  }
});

test('datetime-local is explicitly KST under different host time zones', () => {
  const previous = process.env.TZ;
  try {
    for (const zone of ['UTC', 'America/Los_Angeles', 'Asia/Seoul']) {
      process.env.TZ = zone;
      const input = domain.buildIncidentInput(form({occurredAt:'2026-10-30T23:59:12'}));
      assert.equal(input.discovered_at, '2026-10-31T08:30:00+09:00');
      assert.equal(input.occurred_at, '2026-10-30T23:59:12+09:00');
    }
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});

test('impossible calendar dates and offset input cannot be silently normalized', () => {
  for (const value of ['2026-02-29T08:00', '2026-04-31T08:00', '2026-10-31T24:00', '2026-10-31', '2026-10-31T08:00Z']) {
    assert.throws(() => domain.buildIncidentInput(form({discoveredAt:value})), /시각/);
  }
  assert.equal(domain.buildIncidentInput(form({discoveredAt:'2028-02-29T08:00'})).discovered_at, '2028-02-29T08:00:00+09:00');
});

test('blank count stays unknown and only nonnegative safe whole counts are accepted', () => {
  assert.equal(domain.buildIncidentInput(form({leakState:'suspected'})).personal_info.affected_count, null);
  assert.equal(domain.buildIncidentInput(form({leakState:'confirmed', affectedCount:'0'})).personal_info.affected_count, 0);
  assert.equal(domain.buildIncidentInput(form({leakState:'confirmed', affectedCount:'1000'})).personal_info.affected_count, 1000);
  for (const affectedCount of ['-1', '1.5', '1e3', '1,000', '9007199254740992']) {
    assert.throws(() => domain.buildIncidentInput(form({leakState:'suspected', affectedCount})), /규모/);
  }
});

test('known yes/no answers map to booleans while unknown answers are omitted', () => {
  const personal = domain.buildIncidentInput(form({leakState:'suspected', externalAccess:'yes', includesSensitive:'no'})).personal_info;
  assert.equal(personal.external_unauthorized_access, true);
  assert.equal(personal.includes_sensitive, false);
  assert.ok(!('includes_unique_id' in personal));
  assert.ok(!('recovered_low_risk' in personal));
  assert.ok(!('subjects_notified' in personal));
});

test('inactive privacy details are not submitted after user chooses no leak', () => {
  const personal = domain.buildIncidentInput(form({leakState:'none', externalAccess:'yes', affectedCount:'100', personalItems:'이메일'})).personal_info;
  assert.deepEqual(personal, {leaked:'none'});
});

test('actions and personal items follow API limits without inventing action times', () => {
  const input = domain.buildIncidentInput(form({actions:'키 폐기\n\n접근 차단', leakState:'confirmed', personalItems:'이름, 이메일\n전화번호'}));
  assert.deepEqual(input.actions_taken, [{action:'키 폐기'}, {action:'접근 차단'}]);
  assert.deepEqual(input.personal_info.items, ['이름', '이메일', '전화번호']);
  assert.throws(() => domain.buildIncidentInput(form({actions:Array(31).fill('조치').join('\n')})), /30/);
  assert.throws(() => domain.buildIncidentInput(form({actions:'x'.repeat(501)})), /500/);
  assert.throws(() => domain.buildIncidentInput(form({leakState:'confirmed', personalItems:Array(31).fill('항목').join(',')})), /30/);
  assert.throws(() => domain.buildIncidentInput(form({summary:'x'.repeat(1001)})), /1000/);
});

test('assessment gaps describe missing inputs without treating unknown as no obligation', () => {
  assert.ok(domain.getAssessmentGaps(form(), 'incident_24h').length > 0);
  assert.ok(domain.getAssessmentGaps(form(), 'privacy_72h').length > 0);
  assert.deepEqual(domain.getAssessmentGaps(form({leakState:'none'}), 'privacy_72h'), []);
  const known = form({incidentTypes:['data_leak'], leakState:'confirmed', affectedCount:'999', includesSensitive:'no', includesUniqueId:'no', externalAccess:'no', recoveredLowRisk:'no'});
  assert.deepEqual(domain.getAssessmentGaps(known, 'privacy_72h'), []);
  known.affectedCount = '';
  assert.ok(domain.getAssessmentGaps(known, 'privacy_72h').some(gap => /규모/.test(gap)));
});

test('filing links only explicitly selected valid findings and preserves their fingerprints', () => {
  assert.deepEqual(domain.buildFilingRequest(form(), []).findings, []);
  assert.deepEqual(domain.buildFilingRequest(form(), []).incident.related_fingerprints, []);
  const selected = [finding('a'), finding('b')];
  const request = domain.buildFilingRequest(form(), selected);
  assert.deepEqual(request.findings, selected);
  assert.deepEqual(request.incident.related_fingerprints, ['a', 'b']);
  assert.equal(request.incident.cause, null);
  assert.throws(() => domain.buildFilingRequest(form(), [{fingerprint:'a'}]), /검사.*형식/);
  assert.throws(() => domain.buildFilingRequest(form(), Array.from({length:51}, (_,i) => finding(String(i)))), /50/);
  assert.throws(() => domain.buildFilingRequest(form(), [finding('a'), finding('a')]), /중복/);
});

test('assessment posts the incident directly with a bounded uncached request', async () => {
  const original = global.fetch;
  try {
    const body = domain.buildIncidentInput(form());
    global.fetch = async (url, options) => {
      assert.equal(url, '/api/reports/assess');
      assert.deepEqual(JSON.parse(options.body), body);
      assert.equal(options.method, 'POST');
      assert.equal(options.cache, 'no-store');
      assert.ok(options.signal instanceof AbortSignal);
      return Response.json(assessment());
    };
    assert.deepEqual(await api.assessIncident(body), assessment());
  } finally {global.fetch = original;}
});

test('filing JSON and documents use wrapped payloads and correct formats', async () => {
  const original = global.fetch;
  const body = domain.buildFilingRequest(form(), [finding()]);
  try {
    for (const kind of ['incident_24h', 'privacy_72h']) {
      const endpoint = kind === 'incident_24h' ? 'incident-24h' : 'privacy-72h';
      global.fetch = async (url, options) => {
        assert.equal(url, `/api/reports/${endpoint}?format=json`);
        assert.deepEqual(JSON.parse(options.body), body);
        return Response.json(report(kind));
      };
      assert.deepEqual(await api.getFilingReport(body, kind), report(kind));
      for (const format of ['html', 'markdown']) {
        const text = format === 'html' ? '<!doctype html><html><body>초안</body></html>' : '# 신고서 초안';
        global.fetch = async (url, options) => {
          assert.equal(url, `/api/reports/${endpoint}?format=${format}`);
          assert.deepEqual(JSON.parse(options.body), body);
          return new Response(text, {headers:{'content-type':format === 'html' ? 'text/html' : 'text/markdown'}});
        };
        assert.equal(await api.getFilingDocument(body, kind, format), text);
      }
    }
  } finally {global.fetch = original;}
});

test('report errors explain validation or retry without rendering error bodies as documents', async () => {
  const original = global.fetch;
  const body = domain.buildFilingRequest(form(), []);
  try {
    global.fetch = async () => Response.json({detail:[{loc:['body','discovered_at'], msg:'Input should have timezone info', input:'private value'}]}, {status:422});
    await assert.rejects(api.assessIncident(body.incident), error => /422/.test(error.message) && /시각/.test(error.message) && !/private value/.test(error.message));
    global.fetch = async () => Response.json({detail:{message:'서버가 일시적으로 응답하지 않습니다'}}, {status:503});
    await assert.rejects(api.getFilingReport(body, 'incident_24h'), /503.*일시적/);
    global.fetch = async () => {throw new TypeError('Failed to fetch');};
    await assert.rejects(api.assessIncident(body.incident), /연결|네트워크/);
    global.fetch = async () => {throw new DOMException('timeout', 'TimeoutError');};
    await assert.rejects(api.getFilingDocument(body, 'incident_24h', 'html'), /시간|다시/);
    global.fetch = async () => Response.json({detail:'error'});
    await assert.rejects(api.getFilingDocument(body, 'incident_24h', 'html'), /문서|형식/);
  } finally {global.fetch = original;}
});

test('incomplete, duplicate and malformed assessments cannot masquerade as decisions', async () => {
  const original = global.fetch;
  try {
    for (const value of [{needs:[]}, {needs:[assessment().needs[0], assessment().needs[0]]}, {...assessment(), needs:[{...assessment().needs[0], required:'yes'}, assessment().needs[1]]}]) {
      global.fetch = async () => Response.json(value);
      await assert.rejects(api.assessIncident(domain.buildIncidentInput(form())), /형식/);
    }
  } finally {global.fetch = original;}
});

test('wrong report kinds, invalid dates and malformed nested fields are rejected', async () => {
  const original = global.fetch;
  const body = domain.buildFilingRequest(form(), []);
  try {
    for (const value of [report('privacy_72h'), {...report(), deadline:{...deadline, due_at:'invalid'}}, {...report(), sections:[{...report().sections[0], fields:[{label:'원인', value:{}}]}]}]) {
      global.fetch = async () => Response.json(value);
      await assert.rejects(api.getFilingReport(body, 'incident_24h'), /형식/);
    }
  } finally {global.fetch = original;}
});

// Captured from backend/app/reports (TestClient) with sensitive/unique-id/external/recovered answers left unknown.
const unknownPrivacy = JSON.parse(fs.readFileSync(path.join(directory, 'fixtures/privacy-72h-unknown-facts.json'), 'utf8'));

test('external access is asked for the 24h duty only when the form can send it', () => {
  const gaps = leakState => domain.getAssessmentGaps(form({incidentTypes:['data_leak'], leakState}), 'incident_24h');
  assert.deepEqual(gaps('none'), []);
  assert.deepEqual(gaps('unknown'), []);
  assert.ok(gaps('suspected').some(gap => /외부의 불법 접근/.test(gap)));
});

test('draft blockers list only the facts the API would otherwise default', () => {
  assert.deepEqual(domain.draftBlockers(form()), {incident_24h:['현재 대응 상태', '최초·보완 신고 구분'],
    privacy_72h:['현재 대응 상태', '최초·보완 신고 구분', '개인정보 유출 의심 또는 확인']});
  const known = form({incidentStatus:'contained', filingType:'initial', leakState:'suspected'});
  assert.deepEqual(domain.draftBlockers(known), {incident_24h:[], privacy_72h:['영향받은 분들께 이미 통지했는지']});
  assert.deepEqual(domain.draftBlockers({...known, subjectsNotified:'no'}).privacy_72h, []);
});

test('missing labels from both real drafts become one shared question per fact', () => {
  const {questions, unmapped} = domain.remainingQuestions({incident_24h:unknownPrivacy.incident_missing, privacy_72h:unknownPrivacy.report.missing});
  assert.deepEqual(unmapped, []);
  assert.deepEqual(questions.map(question => question.key), ['occurredAt', 'cause', 'damage', 'department', 'contactName', 'contactPhone']);
  assert.deepEqual(questions.find(question => question.key === 'contactName').kinds, ['incident_24h', 'privacy_72h']);
  assert.deepEqual(domain.remainingQuestions({privacy_72h:['신고서 · 새 칸']}).unmapped, ['새 칸']);
});

test('auto-filled API values are surfaced for confirmation, and only a cause can be moved into the facts', () => {
  const suggestions = domain.autoSuggestions({privacy_72h:unknownPrivacy.report});
  assert.ok(suggestions.length >= 2);
  assert.ok(suggestions.every(item => item.value && item.kinds[0] === 'privacy_72h' && !item.usableAs));
  const cause = {...report(), sections:[{...report().sections[0], fields:[{label:'원인', value:'점검 발견이 원인일 수 있습니다', required:true, auto:true}]}]};
  assert.deepEqual(domain.autoSuggestions({incident_24h:cause, privacy_72h:cause})[0], {label:'원인', value:'점검 발견이 원인일 수 있습니다', kinds:['incident_24h', 'privacy_72h'], usableAs:'cause'});
});

test('unknown privacy answers never reach the draft as a not-required conclusion', () => {
  const gaps = domain.getAssessmentGaps(form({leakState:'suspected', affectedCount:'200'}), 'privacy_72h');
  const {report: qualified, markdown} = domain.qualifyPrivacyDraft(unknownPrivacy.report, unknownPrivacy.markdown, gaps);
  assert.match(unknownPrivacy.markdown, /해당하지 않습니다/);
  assert.doesNotMatch(markdown, /해당하지 않습니다|신고 대상 아닐 수 있음/);
  assert.match(markdown, /\*\*상태\*\* ⚠️ 신고 대상 판단 보류/);
  assert.match(markdown, /## 신고 대상인지\n\n- 아직 확인하지 못한 사실이 있어[\s\S]*민감정보 포함 여부[\s\S]*\n\n## 기한/);
  assert.equal(qualified.status.text, domain.heldStatus);
  assert.ok(qualified.sections.find(section => section.heading === '신고 대상인지').bullets.some(line => /고유식별정보/.test(line)));
  // Known answers keep the API's own conclusion.
  assert.equal(domain.qualifyPrivacyDraft(unknownPrivacy.report, unknownPrivacy.markdown, []).markdown, unknownPrivacy.markdown);
  const required = {...unknownPrivacy.report, status:{text:'작성 중 · 3칸 남음', tone:'warning'}};
  assert.equal(domain.qualifyPrivacyDraft(required, unknownPrivacy.markdown, gaps).markdown, unknownPrivacy.markdown);
});

test('scan records become action lines without exposing token-like strings or exceeding API limits', () => {
  const tokenLike = 'tok_' + 'a1'.repeat(15); // built at runtime: any 24+ char token-like run must be masked
  const findings = [{id:'a', title:'SQL 인젝션', fixed:true}, {id:'b', title:`노출된 키 ${tokenLike}`, fixed:false}, {id:'c', title:'열린 항목', fixed:false}];
  assert.deepEqual(domain.scanActions(findings, ['b']), ['취약점 수정 후 재검사에서 해결 확인: SQL 인젝션', '취약점 수정 조치(재검사 확인 전): 노출된 키 [가림]']);
  const many = Array.from({length:40}, (_, index) => ({id:String(index), title:`${index} ${'긴 제목'.repeat(100)}`, fixed:true}));
  const lines = domain.scanActions(many, []);
  assert.equal(lines.length, 30);
  assert.ok(lines.every(line => [...line].length <= 500));
  assert.equal(domain.mergeActions('노출된 키 폐기\n', ['노출된 키 폐기', '새 조치']), '노출된 키 폐기\n새 조치');
  assert.doesNotThrow(() => domain.buildIncidentInput(form({actions:domain.mergeActions('', lines)})));
});

test('the "now" shortcut is Korea time regardless of the device time zone', () => {
  assert.equal(domain.koreaNow(new Date('2026-10-31T15:30:45Z')), '2026-11-01T00:30');
});
