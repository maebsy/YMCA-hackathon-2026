"""한 번에 점검·고치기 증명 흐름 (#140): audit_repository, audit_status, check_fix, verify_demo, prompts."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from starlette.testclient import TestClient

from live_server import create_live_app
from live_store import LinkStore
from service_api import ServiceAPI, pick_findings
from service_store import WorkspaceStore
from test_handoff import batch

ORIGIN = 'https://mcp.example.com'
REPO = 'https://github.com/demo/example'


def finding(fp, severity, category):
    return {'fingerprint': fp, 'title': f'{fp} title', 'severity': severity, 'tool': 'semgrep',
            'category': category, 'file_path': 'app.js', 'start_line': 3}


class OneShotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = WorkspaceStore(root / 'workspaces.db')
        self.calls, self.pending, self.verify_state = [], False, 'done'
        self.commit = 'a' * 40
        self.review = batch()
        self.engine_findings = []
        self.findings = [finding('dep-1', 'high', 'dependency'), finding('sql-1', 'critical', 'code'),
                         finding('xss-1', 'critical', 'code'), finding('key-1', 'high', 'secret'),
                         finding('cors-1', 'medium', 'code')]

        async def handler(request):
            data = json.loads(request.content) if request.content else None
            path = request.url.path
            self.calls.append((request.method, path, data))
            if request.method == 'POST' and path == '/api/scans':
                return httpx.Response(202, json={'job_id': ('3' if data.get('previous') else '1') * 32, 'status': 'queued'})
            if request.method == 'POST' and path == '/api/llm/explain/tasks':
                fp = data['findings'][0]['fingerprint']
                return httpx.Response(202, json={'job_id': f'{abs(hash(fp)) % 10**32:032x}', 'status': 'queued'})
            if request.method == 'POST' and path == '/api/verify':
                return httpx.Response(202, json={'job_id': '7' * 32, 'status': 'queued', 'reused': False})
            if request.method == 'GET' and path.startswith('/api/verify/'):
                result = {'status': 'verified', 'sandbox': 'docker', 'isolation_confirmed': True, 'message': 'ok',
                          'before_tests': {'ok': True}, 'after_tests': {'ok': True},
                          'attacks': [{'id': 'sqli', 'verdict': 'verified', 'before_evidence': '[3 rows]',
                                       'after_evidence': '[]'}]}
                return httpx.Response(200, json={'status': self.verify_state, 'reused': False,
                                                 'result': result if self.verify_state == 'done' else None})
            if request.method == 'GET' and '/scans/' in path:
                scan = {'scan_id': path[-32:], 'summary': {'open': len(self.findings)}, 'coverage': {'osv': 'ok'},
                        'comparison': {'resolved': 1} if path.endswith('3' * 32) else None,
                        'result': {'target': {'repo_url': REPO, 'commit_sha': 'a' * 40 if path.endswith('1' * 32) else self.commit},
                                   'findings': copy.deepcopy(self.engine_findings)},
                        'report_scan': {'site_name': 'demo'}, 'findings': copy.deepcopy(self.findings)}
                return httpx.Response(200, json={'status': 'running' if self.pending else 'done', 'result': scan})
            if request.method == 'GET' and '/llm/explain/tasks/' in path:
                return httpx.Response(200, json={'status': 'running'})
            return httpx.Response(404)

        client = httpx.AsyncClient(base_url='http://127.0.0.1:8000', transport=httpx.MockTransport(handler))
        self.api = ServiceAPI(self.store, client)
        self.client = self.enterContext(TestClient(create_live_app(LinkStore(root / 'links.db'), ORIGIN,
                                                                   service=self.api), base_url=ORIGIN))

    def call(self, name, error=False, **args):
        response = self.client.post('/mcp/service/rpc', headers={'Accept': 'application/json, text/event-stream'},
                                    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                          'params': {'name': name, 'arguments': args}})
        result = response.json()['result']
        self.assertEqual(result.get('isError', False), error, result)
        return result['content'][0]['text'] if error else json.loads(result['content'][0]['text'])

    def test_pick_prefers_severity_then_distinct_categories(self):
        picked = [f['fingerprint'] for f in pick_findings(self.findings, 3)]
        self.assertEqual(picked, ['sql-1', 'dep-1', 'key-1'])  # critical 코드 → 같은 위험도의 다른 분류(이름순) 먼저, xss-1(코드 중복)은 뒤로
        self.assertEqual(len(pick_findings(self.findings, 5)), 5)
        self.assertEqual(pick_findings(self.findings, 0), [])

    def test_audit_repository_one_call_scans_and_starts_top_analyses(self):
        out = self.call('audit_repository', repository_url=REPO, request_id='one', authorized=True)
        self.assertEqual(out['scan_status'], 'done')
        self.assertTrue(out['workspace_token'] and out['workspace_notice'])  # 작업 공간을 자동으로 만듦
        self.assertEqual([a['fingerprint'] for a in out['analyses']], ['sql-1', 'dep-1', 'key-1'])
        self.assertEqual(out['source']['revision'], self.commit)
        self.assertIn('check_fix', out['next'])
        posts = [c for c in self.calls if c[0] == 'POST']
        self.assertEqual([c[1] for c in posts], ['/api/scans'] + ['/api/llm/explain/tasks'] * 3)

    def test_audit_requires_authorization_and_limits_analyses(self):
        self.assertIn('권한', self.call('audit_repository', error=True, repository_url=REPO, request_id='x'))
        self.assertIn('0~5', self.call('audit_repository', error=True, repository_url=REPO, request_id='y',
                                       authorized=True, max_analyses=9))
        self.assertFalse([c for c in self.calls if c[0] == 'POST'])  # 거절되면 아무것도 접수하지 않음

    def test_unfinished_scan_returns_handoff_to_audit_status(self):
        self.pending = True
        out = asyncio.run(self.api.audit(None, REPO, 'slow', True, wait_seconds=0))
        self.assertEqual(out['scan_status'], 'running')
        self.assertIn('audit_status', out['next'])
        self.assertNotIn('analyses', out)

    def test_audit_status_lists_analyses_of_the_scan(self):
        out = self.call('audit_repository', repository_url=REPO, request_id='one', authorized=True, max_analyses=2)
        status = self.call('audit_status', workspace_token=out['workspace_token'], scan_id=out['scan_id'])
        self.assertEqual(status['summary'], {'open': 5})
        self.assertEqual(len(status['analyses']), 2)
        self.assertTrue(all(a['status'] == 'running' for a in status['analyses']))
        self.assertIn('아직', status['next'])

    def test_check_fix_groups_rescan_results_and_warns_on_same_commit(self):
        first = self.call('audit_repository', repository_url=REPO, request_id='one', authorized=True, max_analyses=0)
        self.engine_findings = [
            {'fingerprint': 'sql-1', 'title': 'SQL', 'severity': 'critical', 'change': 'resolved',
             'status': 'code_resolved', 'location': {'file': 'app.js', 'start_line': 3}},
            {'fingerprint': 'key-1', 'title': 'key', 'severity': 'high', 'change': 'resolved',
             'status': 'runtime_check_needed', 'location': {'file': '.env', 'start_line': 1}},
            {'fingerprint': 'xss-1', 'title': 'XSS', 'severity': 'critical', 'change': 'persisting',
             'status': 'code_issue', 'location': {'file': 'app.js', 'start_line': 9}},
        ]
        same = self.call('check_fix', workspace_token=first['workspace_token'], scan_id=first['scan_id'],
                         request_id='fix-1', authorized=True)
        self.assertIn('push', same['warning'])  # 같은 커밋이면 아직 push 안 된 것
        self.assertEqual([r['fingerprint'] for r in same['resolved']], ['sql-1'])
        self.assertEqual([r['fingerprint'] for r in same['key_reissue_needed']], ['key-1'])
        self.assertEqual([r['fingerprint'] for r in same['persisting']], ['xss-1'])
        rescan = next(c for c in self.calls if c[:2] == ('POST', '/api/scans') and c[2].get('previous'))
        self.assertEqual(rescan[2]['repo_url'], REPO)  # 같은 저장소를 직전 결과와 비교
        self.commit = 'b' * 40
        moved = self.call('check_fix', workspace_token=first['workspace_token'], scan_id=first['scan_id'],
                          request_id='fix-2', authorized=True)
        self.assertNotIn('warning', moved)

    def test_verify_demo_is_demo_only_and_summarizes(self):
        out = self.call('verify_demo', mode='reference')
        self.assertEqual((out['verdict'], out['sandbox'], out['isolation_confirmed']), ('verified', 'docker', True))
        self.assertIn('데모', out['scope'])
        self.assertEqual(out['attacks'][0]['verdict'], 'verified')
        post = next(c for c in self.calls if c[:2] == ('POST', '/api/verify'))
        self.assertEqual(post[2], {'target': 'demo', 'mode': 'reference'})  # 사용자 코드·경로를 보내지 않음
        self.assertIn('mode', self.call('verify_demo', error=True, mode='user-repo'))

    def test_verify_demo_still_running_tells_to_retry(self):
        self.verify_state = 'running'
        out = asyncio.run(self.api.verify_demo('ai', wait_seconds=0))
        self.assertEqual(out['status'], 'running')
        self.assertIn('다시 호출', out['next'])

    def test_prompts_are_listed_and_never_ask_to_print_secrets(self):
        listed = self.client.post('/mcp/service/rpc', headers={'Accept': 'application/json, text/event-stream'},
                                  json={'jsonrpc': '2.0', 'id': 1, 'method': 'prompts/list', 'params': {}}).json()
        names = {p['name'] for p in listed['result']['prompts']}
        self.assertTrue({'security_audit', 'fix_and_verify'} <= names)
        got = self.client.post('/mcp/service/rpc', headers={'Accept': 'application/json, text/event-stream'},
                               json={'jsonrpc': '2.0', 'id': 2, 'method': 'prompts/get',
                                     'params': {'name': 'security_audit', 'arguments': {'repository_url': REPO}}}).json()
        text = got['result']['messages'][0]['content']['text']
        self.assertIn('audit_repository', text)
        self.assertIn('허락', text)
        self.assertIn('비밀값', text)


if __name__ == '__main__':
    unittest.main()
