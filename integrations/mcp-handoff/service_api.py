"""Service MCP uses the existing backend contract, never the engine or GPU directly."""
import hashlib
import json
import re

import httpx

from handoff import Snapshot, _reason, redact


def clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def repository_url(value):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?', value)
    if not match or any(p in ('.', '..') for p in match.groups()):
        raise ValueError('공개 GitHub 저장소의 https://github.com/owner/repo 주소가 필요합니다.')
    return f'https://github.com/{match[1]}/{match[2].removesuffix(".git")}'


class ServiceAPI:
    def __init__(self, store, client):
        self.store, self.client = store, client

    async def request(self, method, path, body=None):
        # Paths are constructed exclusively here; no caller can select a network destination.
        try:
            async with self.client.stream(method, path, json=body) as response:
                if response.status_code in (401, 403):
                    raise ValueError('서버 인증 또는 검사 정책이 이 요청을 허용하지 않습니다. 운영자에게 문의하세요.')
                if response.status_code == 404:
                    raise ValueError('서버 결과가 만료되었거나 없습니다. 새 검사가 필요합니다.')
                if response.status_code == 429:
                    raise ValueError('서버 대기열이 가득 찼습니다. 잠시 후 다시 시도하세요.')
                if response.status_code >= 400:
                    raise ValueError(f'서버가 요청을 처리하지 못했습니다 (HTTP {response.status_code}). 입력과 서버 상태를 확인하세요.')
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 8 * 1024 * 1024:
                        raise ValueError('서버 결과가 전달 한도를 초과했습니다.')
                return json.loads(raw)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ValueError('서버 응답을 확인할 수 없습니다. POST 작업을 자동으로 재접수하지 마세요.') from exc

    @staticmethod
    def receipt(job, data, kind):
        return {f'{kind}_id': job, 'status': data['state'], 'poll_after_seconds': 10,
                'notice': data.get('notice')}

    async def dispatch(self, token, kind, key, metadata, path, body):
        job, data, fresh = self.store.reserve(token, kind, key, metadata)
        if fresh:
            try:
                result = await self.request('POST', path, body)
                upstream = result.get('job_id', '')
                if not re.fullmatch(r'[a-f0-9]{32}', upstream):
                    raise ValueError('서버 작업 식별자를 확인할 수 없습니다.')
                data.update(upstream=upstream, state='queued')
            except ValueError as exc:
                # Durable uncertain state deliberately prevents retrying a possibly accepted GPU task.
                data.update(state='not_confirmed', notice=str(exc))
            self.store.update(token, job, kind, data)
        return self.receipt(job, data, kind)

    async def poll(self, token, job, kind):
        data = self.store.get(token, job, kind)
        if 'upstream' not in data:
            return data, None
        prefix = '/api/scans/' if kind == 'scan' else '/api/llm/explain/tasks/'
        result = await self.request('GET', prefix + data['upstream'])
        state = result.get('status')
        if state not in ('queued', 'running', 'done', 'failed'):
            raise ValueError('서버 작업 상태가 올바르지 않습니다.')
        data['state'] = state
        if state == 'failed':
            data['notice'] = '서버 작업이 실패했습니다. 원본 오류에는 민감정보가 있을 수 있어 전달하지 않습니다.'
        self.store.update(token, job, kind, data)
        return data, result.get('result') if state == 'done' else None

    async def scan_result(self, token, scan_id):
        data, result = await self.poll(token, scan_id, 'scan')
        if result is None:
            raise ValueError('검사가 완료되지 않았습니다. get_scan으로 상태를 확인하세요.')
        target = result['result']['target']
        repo = repository_url(target['repo_url'])
        if repo.lower() != data['input']['repository_url'].lower():
            raise ValueError('접수한 저장소와 결과의 저장소가 다릅니다.')
        revision = target['commit_sha']
        if not re.fullmatch(r'[a-fA-F0-9]{40}', revision):
            raise ValueError('검사 커밋을 확인할 수 없습니다.')
        source = {'repository': repo.removeprefix('https://github.com/'), 'revision': revision,
                  'scan_id': result['scan_id'], 'binding': 'backend_api_scan_and_analysis'}
        return result, source

    async def start_scan(self, token, url, request_id, authorized, previous_scan_id=None):
        if authorized is not True:
            raise ValueError('사용자가 검사 권한을 가진 저장소인지 먼저 확인하세요.')
        url = repository_url(url)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request_id):
            raise ValueError('request_id는 영문·숫자·밑줄·하이픈 1~64자입니다.')
        previous = None
        if previous_scan_id:
            result, source = await self.scan_result(token, previous_scan_id)
            if source['repository'].lower() != url.removeprefix('https://github.com/').lower():
                raise ValueError('같은 저장소만 재검사할 수 있습니다.')
            previous = result['result']
        return await self.dispatch(token, 'scan', request_id,
            {'repository_url': url, 'previous_scan_id': previous_scan_id}, '/api/scans',
            {'repo_url': url, 'previous': previous})

    async def get_scan(self, token, scan_id):
        data, result = await self.poll(token, scan_id, 'scan')
        out = self.receipt(scan_id, data, 'scan')
        if result is not None:
            result, source = await self.scan_result(token, scan_id)
            fields = ('fingerprint', 'title', 'severity', 'category', 'tool', 'file_path', 'start_line')
            out.update(source=source, summary=clean(result.get('summary')), coverage=clean(result.get('coverage')),
                       comparison=clean(result.get('comparison')),
                       findings=[clean({k: f.get(k) for k in fields}) for f in result['findings']],
                       notice='LLM 입력 가능한 최대 50건입니다. 전체 수는 summary를 확인하세요. 웹 결과 파일은 필요 없습니다.')
        return out

    async def start_analysis(self, token, scan_id, fingerprint, os, hosting):
        if os not in ('windows', 'macos', 'linux') or hosting not in (
                'vercel', 'netlify', 'cloudflare', 'supabase', 'render', 'railway', 'self_hosted', 'unknown'):
            raise ValueError('지원하는 os 및 hosting 값을 지정하세요.')
        result, _ = await self.scan_result(token, scan_id)
        finding = next((f for f in result['findings'] if f['fingerprint'] == fingerprint), None)
        if finding is None:
            raise ValueError('이 검사의 LLM 입력 항목이 아닙니다.')
        metadata = {'scan_id': scan_id, 'fingerprint': fingerprint, 'os': os, 'hosting': hosting}
        key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return await self.dispatch(token, 'analysis', key, metadata, '/api/llm/explain/tasks',
            {'findings': [finding], 'mode': 'red_blue', 'environment': {'os': os, 'hosting': hosting}})

    async def analysis_snapshot(self, token, analysis_id):
        data, result = await self.poll(token, analysis_id, 'analysis')
        if result is None:
            return data, None, None
        _, source = await self.scan_result(token, data['input']['scan_id'])
        items = result.get('results')
        if result.get('mode') != 'red_blue' or not isinstance(items, list) or len(items) != 1:
            raise ValueError('LLM 응답이 요청한 단일 Red/Blue 분석과 다릅니다.')
        item = items[0]
        if item.get('fingerprint') != data['input']['fingerprint']:
            raise ValueError('LLM 결과의 검사 항목이 다릅니다.')
        reason = _reason(item)
        entry = {'fingerprint': item['fingerprint'], 'ready': reason is None, 'reason': reason}
        if reason is None:
            entry['proposal'] = {k: redact(item['explanation'][k]) for k in ('ai_fix_prompt', 'model', 'prompt_version')}
        snapshot = Snapshot.__new__(Snapshot)
        snapshot.entries = {entry['fingerprint']: entry}
        snapshot.provenance = source
        return data, snapshot, items

    async def get_analysis(self, token, analysis_id):
        data, snapshot, _ = await self.analysis_snapshot(token, analysis_id)
        out = self.receipt(analysis_id, data, 'analysis')
        if snapshot:
            out.update(snapshot.list_findings())
        return out

    async def fix_prompt(self, token, analysis_id):
        _, snapshot, _ = await self.analysis_snapshot(token, analysis_id)
        if not snapshot:
            raise ValueError('아직 GPU 분석이 완료되지 않았습니다. get_analysis로 확인하세요.')
        prompt = snapshot.fix_prompt(next(iter(snapshot.entries)))
        return prompt.replace('이 두 값은 운영자가 지정했으며 MCP가 출처를 인증하지는 않습니다.',
                              '이 두 값은 MCP가 접수한 서버 검사 응답에서 확인했습니다.')

    async def report(self, token, scan_id):
        result, source = await self.scan_result(token, scan_id)
        explanations, pending = [], 0
        for job, _ in self.store.analyses(token, scan_id):
            data, _, items = await self.analysis_snapshot(token, job)
            if items:
                explanations.extend(items)
            else:
                pending += 1
        report = await self.request('POST', '/api/reports/plain?format=json',
            {'scan': result['report_scan'], 'findings': result['findings'], 'explain_results': explanations})
        return {'source': source, 'analysis_count': len(explanations), 'incomplete_analysis_count': pending,
                'report': clean(report), 'notice': '리포트는 전체 취약점 해결이나 미분석 항목의 안전을 증명하지 않습니다.'}

    async def incident(self, token, scan_id, kind, incident):
        result, source = await self.scan_result(token, scan_id)
        if kind not in ('assess', 'incident-24h', 'privacy-72h'):
            raise ValueError('kind는 assess, incident-24h, privacy-72h 중 하나입니다.')
        if len(json.dumps(incident)) > 24000:
            raise ValueError('사고 정보가 너무 큽니다.')
        body = incident if kind == 'assess' else {'incident': incident, 'findings': result['findings']}
        report = await self.request('POST', f'/api/reports/{kind}?format=json', body)
        return {'source': source, 'draft_only': True, 'result': clean(report),
                'notice': '사용자가 확인한 사고 사실만 입력하세요. 외부 기관에 제출되지 않습니다.'}
