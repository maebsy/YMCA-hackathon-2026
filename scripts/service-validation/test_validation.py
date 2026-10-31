import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

from client import Client, CheckError, origin
from evidence import Evidence
from checks import report_checks, llm_checks
from probe import Monitor
from serve import handler


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


if __name__ == '__main__':
    unittest.main()
