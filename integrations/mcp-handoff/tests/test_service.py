"""Full protocol workflow, backend-derived inputs, isolation and retry safety."""
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
from service_api import ServiceAPI
from service_store import WorkspaceStore
from test_handoff import batch

ORIGIN = 'https://mcp.example.com'


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.clock = [1000.0]
        self.store = WorkspaceStore(root / 'workspaces.db', clock=lambda: self.clock[0])
        self.calls, self.fail, self.pending = [], None, False
        self.review = batch()
        self.scan = {'scan_id': '9' * 32, 'summary': {'total': 1}, 'coverage': {'osv': 'ok'},
            'result': {'target': {'repo_url': 'https://github.com/demo/example', 'commit_sha': 'a' * 40},
                       'findings': [{'secret': 'RAW_ENGINE_SENTINEL'}]},
            'report_scan': {'site_name': 'demo', 'scanned_at': '2026-10-31T00:00:00Z'},
            'findings': [{'fingerprint': 'demo-sql-001', 'title': 'SQL injection', 'severity': 'high',
                          'tool': 'semgrep', 'category': 'code', 'snippet': 'SNIPPET_SENTINEL'}]}
        async def handler(request):
            data = json.loads(request.content) if request.content else None
            self.calls.append((request.method, request.url.path, data))
            if self.fail == 'timeout' and request.method == 'POST':
                raise httpx.ReadTimeout('secret upstream error')
            if isinstance(self.fail, int):
                return httpx.Response(self.fail, json={'detail': 'DO_NOT_LEAK_ERROR'})
            if request.method == 'POST' and request.url.path == '/api/scans':
                await asyncio.sleep(.01)
                return httpx.Response(202, json={'job_id': '1' * 32, 'status': 'queued'})
            if request.method == 'POST' and request.url.path == '/api/llm/explain/tasks':
                return httpx.Response(202, json={'job_id': '2' * 32, 'status': 'queued'})
            if request.method == 'GET':
                return httpx.Response(200, json={'status': 'running' if self.pending else 'done',
                    'result': copy.deepcopy(self.scan if '/scans/' in request.url.path else self.review)})
            return httpx.Response(200, json={'title': 'Actual API report', 'sections': []})
        client = httpx.AsyncClient(base_url='http://127.0.0.1:8000', transport=httpx.MockTransport(handler))
        self.api = ServiceAPI(self.store, client)
        self.client = self.enterContext(TestClient(create_live_app(LinkStore(root / 'links.db'), ORIGIN,
            service=self.api), base_url=ORIGIN))
        self.token = self.call('create_workspace')['workspace_token']

    def rpc(self, method, params):
        return self.client.post('/mcp/service/rpc', headers={'Accept': 'application/json, text/event-stream'},
            json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})

    def call(self, name, error=False, **args):
        result = self.rpc('tools/call', {'name': name, 'arguments': args}).json()['result']
        self.assertEqual(result.get('isError', False), error, result)
        text = result['content'][0]['text']
        if error or name == 'get_fix_prompt':
            return text
        return json.loads(text)

    def start(self, **changes):
        args = dict(workspace_token=self.token, repository_url='https://github.com/demo/example',
                    request_id='first', authorized=True)
        args.update(changes)
        return self.call('start_scan', **args)

    def analyse(self, scan):
        return self.call('start_analysis', workspace_token=self.token, scan_id=scan,
                         fingerprint='demo-sql-001', os='linux', hosting='self_hosted')

    def test_end_to_end_protocol_actual_api_payload_and_report(self):
        response = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                          'clientInfo': {'name': 'test', 'version': '1'}})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('mcp-session-id', response.headers)
        scan = self.start()['scan_id']
        listing = self.call('get_scan', workspace_token=self.token, scan_id=scan)
        self.assertEqual(listing['source']['revision'], 'a' * 40)
        self.assertNotIn('SENTINEL', json.dumps(listing))
        analysis = self.analyse(scan)['analysis_id']
        submitted = next(data for method, path, data in self.calls if method == 'POST' and 'explain' in path)
        self.assertEqual(submitted['findings'], self.scan['findings'])
        self.assertEqual(submitted['mode'], 'red_blue')
        status = self.call('get_analysis', workspace_token=self.token, analysis_id=analysis)
        self.assertTrue(status['findings'][0]['ready'])
        prompt = self.call('get_fix_prompt', workspace_token=self.token, analysis_id=analysis)
        self.assertIn('backend_api_scan_and_analysis', prompt)
        self.assertIn('a' * 40, prompt)
        self.assertNotIn('운영자가 지정했으며', prompt)
        report = self.call('generate_report', workspace_token=self.token, scan_id=scan)
        self.assertEqual(report['analysis_count'], 1)
        self.assertEqual(report['report']['title'], 'Actual API report')
        self.call('rescan', workspace_token=self.token, previous_scan_id=scan, request_id='rescan', authorized=True)
        self.assertEqual(self.calls[-1][2]['previous'], self.scan['result'])
        self.call('incident_report', workspace_token=self.token, scan_id=scan, kind='incident-24h',
                  incident={'discovered_at': '2026-10-31T00:00:00Z'})
        self.assertEqual(self.calls[-1][1], '/api/reports/incident-24h')

    def test_isolation_expiry_revocation_and_no_capability_storage(self):
        scan = self.start()['scan_id']
        other = self.call('create_workspace')['workspace_token']
        before = len(self.calls)
        self.call('get_scan', error=True, workspace_token=other, scan_id=scan)
        self.assertEqual(len(self.calls), before)
        self.assertNotIn(self.token.encode(), self.store.path.read_bytes())
        self.assertNotIn(b'SENTINEL', self.store.path.read_bytes())
        self.call('close_workspace', workspace_token=self.token)
        self.call('get_scan', error=True, workspace_token=self.token, scan_id=scan)
        self.clock[0] += 86401
        self.call('get_scan', error=True, workspace_token=other, scan_id=scan)

    def test_idempotency_including_concurrent_dispatch(self):
        scan = self.start()['scan_id']
        self.assertEqual(self.start()['scan_id'], scan)
        analysis = self.analyse(scan)['analysis_id']
        self.assertEqual(self.analyse(scan)['analysis_id'], analysis)
        self.assertEqual(len([x for x in self.calls if x[0] == 'POST']), 2)
        self.start(error=True, repository_url='https://github.com/other/repo')
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: self.start(request_id='concurrent'), range(4)))
        self.assertEqual(len({r['scan_id'] for r in receipts}), 1)
        self.assertEqual(len([x for x in self.calls if x[0] == 'POST']), 3)

    def test_uncertain_submit_never_retried_and_auth_policy_respected(self):
        self.fail = 'timeout'
        first = self.start()
        self.assertEqual(first['status'], 'not_confirmed')
        self.assertEqual(self.start(), first)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('secret upstream', str(first))
        for status in (401, 403, 429, 404, 500):
            self.fail = status
            result = self.start(request_id=f'error-{status}')
            self.assertEqual(result['status'], 'not_confirmed')
            self.assertNotIn('DO_NOT_LEAK_ERROR', str(result))

    def test_bad_target_unknown_finding_and_red_gate(self):
        for url in ('http://127.0.0.1', 'https://github.com/x/y?q=1', 'https://github.com/x/../',
                    'https://github.com@evil.example/x/y'):
            self.start(error=True, repository_url=url)
        self.start(error=True, authorized=False)
        self.assertEqual(self.calls, [])
        scan = self.start()['scan_id']
        self.call('start_analysis', error=True, workspace_token=self.token, scan_id=scan,
                  fingerprint='not-in-scan', os='linux')
        analysis = self.analyse(scan)['analysis_id']
        self.review['results'][0]['explanation']['needs_manual_review'] = True
        self.call('get_fix_prompt', error=True, workspace_token=self.token, analysis_id=analysis)
        self.scan['result']['target']['repo_url'] = 'https://github.com/other/repo'
        self.call('get_scan', error=True, workspace_token=self.token, scan_id=scan)

    def test_pending_report_disclosure_and_bounds(self):
        scan = self.start()['scan_id']
        analysis = self.analyse(scan)['analysis_id']
        self.pending = True
        result = self.call('get_analysis', workspace_token=self.token, analysis_id=analysis)
        self.assertEqual(result['status'], 'running')
        self.assertNotIn('findings', result)
        self.call('get_fix_prompt', error=True, workspace_token=self.token, analysis_id=analysis)
        self.pending = False
        self.store.job_limit = 2
        self.start(error=True, request_id='over-limit')

    def test_hub_config_tools_and_host_boundary(self):
        hub = self.client.get('/mcp/service')
        self.assertEqual(hub.status_code, 200)
        self.assertIn('cursor://', hub.text)
        self.assertIn('vscode:mcp/install?', hub.text)
        self.assertNotIn('{{', hub.text)
        config = self.client.get('/mcp/service/config.json').json()
        self.assertEqual(config['mcpServers']['72hours-service']['url'], ORIGIN + '/mcp/service/rpc')
        self.assertIn('default branch', self.client.get('/mcp/service/agent.txt').text)
        tool_list = self.rpc('tools/list', {}).json()['result']['tools']
        self.assertEqual(len(tool_list), 15)  # 기존 11개 + 한 번에 점검·고치기 증명 4개 (#140)
        self.assertTrue({'audit_repository', 'audit_status', 'check_fix', 'verify_demo'} <= {t['name'] for t in tool_list})
        tools = {t['name']: t for t in tool_list}
        self.assertFalse(tools['start_scan']['annotations']['readOnlyHint'])
        response = self.client.post('/mcp/service/rpc', headers={'Origin': 'https://evil.example'}, json={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/mcp/connect').status_code, 200)


if __name__ == '__main__':
    unittest.main()
