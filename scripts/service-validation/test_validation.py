import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, AsyncMock, patch

from client import Client, CheckError, origin
from evidence import Evidence
from checks import report_checks, llm_checks
from probe import Monitor
from serve import handler
from serve import history
from server_diagnose import diagnose
from diagnostics import failures
from campaign import lock
from engine_quality import evaluate_labels
from quality_probe import summary
from data_quality import check_data_contracts, source_metadata, collect_freshness
import subprocess
import sys


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.e = Evidence(self.tmp.name, {'test': True})

    def test_uncertain_post_never_resubmitted(self):
        c = Client('https://example.com', self.e)
        c.request = Mock(side_effect=CheckError('connection lost'))
        with self.assertRaises(CheckError):
            c.job('scan', '/api/scans', {}, 10, {})
        resumed = Client('https://example.com', Evidence(self.tmp.name, {'test': True}, True))
        resumed.request = Mock()
        with self.assertRaisesRegex(CheckError, '불명확'):
            resumed.job('scan', '/api/scans', {}, 10, {})
        resumed.request.assert_not_called()

    def test_receipt_resume_only_polls(self):
        self.e.state['jobs']['scan'] = {'job_id': 'a'*32}
        c = Client('https://example.com', self.e)
        c.request = Mock(return_value={'status': 'done', 'result': {'real': True}})
        self.assertEqual(c.job('scan', '/api/scans', {}, 10, {}), {'real': True})
        c.request.assert_called_once_with('GET', '/api/scans/' + 'a'*32)

    def test_public_escapes_scripts_and_tokens(self):
        self.e.data['notice'] = '</script><script>alert(1)</script> Bearer abc.def'
        self.e.save()
        page = (self.e.public/'index.html').read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert', page)
        self.assertNotIn('Bearer abc.def', page)
        self.assertIn('[REDACTED]', page)

    def test_scope_changes_cannot_resume(self):
        with self.assertRaises(ValueError):
            Evidence(self.tmp.name, {'test': False}, True)

    def test_wrong_report_and_false_completion_fail(self):
        case = {}
        result = {'scan_id': 'a'*32, 'report_scan': {'site_name': 'owner/repo', 'not_checked': ['osv']},
                  'findings': [{'status': 'open'}], 'result': {'target': {'commit_sha': 'b'*40}}}
        report_checks(self.e, case, result, [], {'title': 'other/repo', 'status': {'text': '완료'},
                      'body': '재검사로 확인했습니다'})
        self.assertEqual(sum(x['status'] == 'fail' for x in case['checks']), 3)

    def test_red_pass_with_issues_is_not_ready(self):
        case = {}
        explanation = dict(fingerprint='fp', model='model', prompt_version='v1', variant='D',
            completion_tokens=100, latency_ms=500, summary='summary', why_risky='why',
            fix_steps=['fix'], ai_fix_prompt='fix package', red_verdict='pass', needs_manual_review=False,
            false_positive_suspect=False, red_rounds=[{'verdict': 'pass', 'issues': ['unresolved'], 'latency_ms': 100}])
        llm_checks(self.e, case, {'fingerprint': 'fp', 'package_name': 'package'},
            {'mode': 'red_blue', 'model': 'model', 'prompt_version': 'v1', 'results':
             [{'fingerprint': 'fp', 'status': 'done', 'explanation': explanation}]}, 'model')
        self.assertFalse(case['analyses'][0]['ready'])
        self.assertTrue(any(x['status'] == 'fail' for x in case['checks']))

    def test_readonly_server_never_serves_private_or_traversal(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.e.public))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port)
        for path in ('/validation/../private/state.json', '/validation/%2e%2e/private/state.json', '/validation/'):
            if path.endswith('/validation/'):
                with urllib.request.urlopen(base+path) as r:
                    self.assertEqual(r.status, 200)
            else:
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(base+path)
                self.assertEqual(raised.exception.code, 404)
        with urllib.request.urlopen(base+'/validation') as r:
            self.assertEqual(r.url, base+'/validation/')
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(urllib.request.Request(base+'/validation/', data=b'{}'))
        self.assertEqual(raised.exception.code, 501)

    def test_monitor_without_ssh_can_stop(self):
        Monitor(self.e.public).stop()

    def test_origin_credentials_rejected(self):
        for value in ('https://user:password@example.com', 'http://example.com', 'https://example.com/private'):
            with self.assertRaises(ValueError):
                origin(value)

    def test_diagnosis_requires_matching_job_and_full_evidence(self):
        job = 'a'*32
        records = [{'MESSAGE': 'scan '+job+' failed', '__REALTIME_TIMESTAMP': '1000000'},
                   {'MESSAGE': 'in _package_finding\nValidationError FindingInput\nwhat\n2000 [type=string_too_long]', '__REALTIME_TIMESTAMP': '1000001'}]
        self.assertEqual(diagnose(records, job)['code'], 'FINDING_WHAT_TOO_LONG')
        self.assertEqual(diagnose(records, 'b'*32)['code'], 'CAUSE_NOT_CONFIRMED')
        records[1]['__REALTIME_TIMESTAMP'] = '5000000'
        self.assertEqual(diagnose(records, job)['code'], 'CAUSE_NOT_CONFIRMED')

    def test_wrong_job_cannot_confirm_cause_and_no_raw_log_leaks(self):
        case = {'key': 'x', 'repository': 'https://github.com/a/b', 'stage': 'scan',
                'scan_job': {'job_id': 'a'*32, 'error_code': 'SCAN_ERROR'},
                'server_diagnosis': {'job_id': 'b'*32, 'code': 'FINDING_WHAT_TOO_LONG'},
                'checks': [{'name': 'scan', 'status': 'fail', 'detail': 'SCAN_ERROR'}]}
        data = {'cases': [case], 'checks': []}
        self.assertEqual(failures(data)[0]['cause_status'], 'unconfirmed')
        case['server_diagnosis']['job_id'] = 'a'*32
        self.assertEqual(failures(data)[0]['cause_status'], 'confirmed')

    def test_archive_deduplicates_republication_and_rejects_unsafe_names(self):
        archives = Path(self.tmp.name)/'releases'
        for name in ('1000000000000000001', '1000000000000000002', 'private'):
            folder = archives/name
            folder.mkdir(parents=True)
            (folder/'results.json').write_text(json.dumps(self.e.data), encoding='utf-8')
            (folder/'index.html').write_text('ok')
        rows = history(archives)['runs']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], '1000000000000000002')

    def test_campaign_excludes_concurrent_process(self):
        path = Path(self.tmp.name)/'campaign.lock'
        code = 'import sys; from pathlib import Path; from campaign import lock; ctx=lock(Path(sys.argv[1])); ctx.__enter__()'
        with lock(path):
            result = subprocess.run([sys.executable, '-c', code, str(path)], cwd=Path(__file__).parent,
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)

    def test_failures_export_survives_without_server_access(self):
        self.e.data['cases'] = [{'key': 'x', 'stage': 'scan', 'repository': 'https://github.com/a/b',
            'scan_job': {'job_id': 'a'*32}, 'checks': [{'name': 'scan', 'status': 'fail', 'detail': 'SCAN_ERROR'}]}]
        self.e.save()
        public = json.loads((self.e.public/'failures.json').read_text(encoding='utf-8'))
        self.assertEqual(public[0]['cause_status'], 'unconfirmed')
        self.assertIn('POST', (self.e.public/'handoff.md').read_text(encoding='utf-8'))

    def test_oracle_detects_false_positive_and_false_negative(self):
        labels = [{'file':'app.js','line':2,'rule':'vibe-coding/sql','expected':True},
                  {'file':'safe.js','line':5,'rule':'vibe-coding/sql','expected':False}]
        detected = [{'rule_id':'vibe-coding/sql','location':{'file':'safe.js','start_line':5,'end_line':5}}]
        self.assertEqual([r['outcome'] for r in evaluate_labels(labels, detected)], ['FN', 'FP'])

    def test_oracle_does_not_accept_wrong_rule_or_other_file(self):
        labels = [{'file':'app.js','line':2,'rule':'vibe-coding/sql','expected':True}]
        detected = [{'rule_id':'vibe-coding/sql','location':{'file':'other.js','start_line':2,'end_line':2}},
                    {'rule_id':'vibe-coding/eval','location':{'file':'app.js','start_line':2,'end_line':2}}]
        self.assertEqual(evaluate_labels(labels, detected)[0]['outcome'], 'FN')

    def test_engine_failure_archive_keeps_expectations_revision_and_issue(self):
        quality = summary({'status': 'failed', 'source_revision': 'a'*40, 'labeled_metrics': {'TP': 28},
            'snapshots': {'historical_secret': {'scan_id': 'history-scan'}},
            'checks': [{'name': '설계의 과거 커밋 비밀키 탐지', 'status': 'fail',
                        'expected': 'detect old key', 'actual': {'findings': 0, 'coverage': 'ok'},
                        'basis': 'design', 'group': 'design_gap'}]})
        self.e.data['engine_quality'] = quality
        self.e.check(self.e.data, '엔진 설계 적합성 정답 검증', 'fail', quality)
        rows = json.loads((self.e.public/'failures.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['revision'], 'a'*40)
        self.assertEqual(rows[0]['scan_id'], 'history-scan')
        self.assertTrue(rows[0]['issue'].endswith('/87'))
        self.assertEqual(rows[0]['cause_status'], 'unconfirmed')
        self.assertEqual(rows[0]['observed']['actual']['findings'], 0)
        self.assertIn('engine_quality.py', (self.e.public/'handoff.md').read_text(encoding='utf-8'))

    def test_engine_other_failure_never_assigned_to_known_history_issue(self):
        row = failures({'engine_quality': {'source_revision': 'unknown', 'failed_checks': [
            {'name': 'OSV 알려진 취약 버전', 'expected': 'CVE found', 'actual': 'timeout'}]}})[0]
        self.assertIsNone(row['issue'])
        self.assertIsNone(row['revision'])
        self.assertEqual(row['cause_status'], 'unconfirmed')

    def test_engine_collection_failure_keeps_generic_failure_without_old_evidence(self):
        rows = failures({'checks': [{'name': '엔진 설계 적합성 정답 검증', 'status': 'fail', 'detail': 'SSH unavailable'}]})
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['issue'])

    def test_data_oracle_rejects_downgrade_prerelease_error_and_false_kev(self):
        client = Mock(lookup=AsyncMock(return_value={'CVE-2021-23337': Mock(model_dump=lambda: {'kev': False})}),
                      aclose=AsyncMock())
        checks = []
        check_data_contracts(lambda *args: checks.append(args), Mock(side_effect=['1.9.0', '1.2.4']),
                             Mock(return_value=client), Mock(), Mock())
        self.assertEqual([c[3] for c in checks], [False, False, False])
        client.aclose.assert_awaited_once()
        rows = failures({'engine_quality': {'failed_checks': [{'name': c[0]} for c in checks]}})
        self.assertEqual([r['issue'].rsplit('/', 1)[1] for r in rows], ['92', '92', '93'])

    def test_data_oracle_accepts_safe_versions_and_unknown_kev(self):
        client = Mock(lookup=AsyncMock(return_value={}), aclose=AsyncMock())
        checks = []
        check_data_contracts(lambda *args: checks.append(args), Mock(side_effect=[None, '1.2.3']),
                             Mock(return_value=client), Mock(), Mock())
        self.assertEqual([c[3] for c in checks], [True, True, True])

    def test_freshness_never_exports_raw_feed_or_marks_network_failure_received(self):
        row = source_metadata('OSV 표본', {'id': 'test', 'modified': 'date', 'details': 'raw source'})
        self.assertNotIn('details', row)
        with patch('data_quality.urllib.request.urlopen', side_effect=OSError('private transport data')):
            rows = collect_freshness()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r['status'] == 'unavailable' for r in rows))
        self.assertNotIn('private transport data', json.dumps(rows))


if __name__ == '__main__':
    unittest.main()
