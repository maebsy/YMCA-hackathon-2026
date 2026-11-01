"""Service MCP uses the existing backend contract, never the engine or GPU directly."""
import asyncio
import hashlib
import json
import re
import time

import httpx

from handoff import Snapshot, _reason, redact

# 한 번에 점검(#140): MCP 호출 하나가 너무 오래 걸리지 않게 기다리는 시간을 제한하고, 넘으면 audit_status 로 잇는다
MAX_WAIT_SECONDS = 90
POLL_SECONDS = 3
MAX_AUTO_ANALYSES = 5
SEVERITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'unknown': 4}
FINDING_FIELDS = ('fingerprint', 'title', 'severity', 'category', 'tool', 'file_path', 'start_line')


def pick_findings(findings, count):
    """해석할 항목: 위험도 높은 순, 같은 위험도면 분류(코드·비밀값·설정·의존성)가 겹치지 않게 먼저 고른다."""
    ordered = sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.get('severity'), 9), f.get('fingerprint', '')))
    picked, seen = [], set()
    for f in ordered:
        if len(picked) < count and f.get('category') not in seen:
            picked.append(f)
            seen.add(f.get('category'))
    for f in ordered:
        if len(picked) < count and f not in picked:
            picked.append(f)
    return picked


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


class Gone(ValueError):
    """서버가 404로 결과가 없거나 만료되었다고 확인해 준 경우 (일시 오류와 구분)."""


class ServiceAPI:
    def __init__(self, store, client):
        self.store, self.client = store, client
        # 진행 중인 실검증 영수증(mode별). 백엔드는 끝난 결과만 재사용하므로, 재호출이 새 작업을 접수하지 않게 보존한다.
        self.verify_running, self.verify_lock = {}, asyncio.Lock()

    async def request(self, method, path, body=None):
        # Paths are constructed exclusively here; no caller can select a network destination.
        try:
            async with self.client.stream(method, path, json=body) as response:
                if response.status_code in (401, 403):
                    raise ValueError('서버 인증 또는 검사 정책이 이 요청을 허용하지 않습니다. 운영자에게 문의하세요.')
                if response.status_code == 404:
                    raise Gone('서버 결과가 만료되었거나 없습니다. 새 검사가 필요합니다.')
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

    async def start_analysis(self, token, scan_id, fingerprint):
        result, _ = await self.scan_result(token, scan_id)
        finding = next((f for f in result['findings'] if f['fingerprint'] == fingerprint), None)
        if finding is None:
            raise ValueError('이 검사의 LLM 입력 항목이 아닙니다.')
        metadata = {'scan_id': scan_id, 'fingerprint': fingerprint}
        key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return await self.dispatch(token, 'analysis', key, metadata, '/api/llm/explain/tasks',
            {'findings': [finding], 'mode': 'red_blue'})

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

    # ── 한 번에 점검·고치기 증명 흐름 (#140) ──

    async def wait(self, token, job, kind, seconds, sleep=asyncio.sleep, clock=time.monotonic):
        """작업이 끝나거나(done·failed) 접수가 불확실하거나 시간이 다 될 때까지 상태를 확인한다."""
        seconds = max(0, min(int(seconds), MAX_WAIT_SECONDS))
        deadline = clock() + seconds
        while True:
            data, _ = await self.poll(token, job, kind)
            if data['state'] in ('done', 'failed', 'not_confirmed') or clock() >= deadline:
                return data
            await sleep(POLL_SECONDS)

    async def audit(self, token, url, request_id, authorized, max_analyses=3, wait_seconds=MAX_WAIT_SECONDS):
        """검사 시작 → (최대 90초) 완료 대기 → 위험도 상위 항목의 GPU 해석 자동 시작 → 요약과 다음 할 일."""
        if not 0 <= int(max_analyses) <= MAX_AUTO_ANALYSES:
            raise ValueError(f'max_analyses는 0~{MAX_AUTO_ANALYSES}입니다.')
        created = None
        if not token:
            created = self.store.create()
            token = created['workspace_token']
        receipt = await self.start_scan(token, url, request_id, authorized)
        scan_id = receipt['scan_id']
        data = await self.wait(token, scan_id, 'scan', wait_seconds)
        out = {'workspace_token': token, 'scan_id': scan_id, 'scan_status': data['state']}
        if created:
            out['workspace_notice'] = created['notice']
        if data['state'] != 'done':
            out['next'] = ('검사가 아직 끝나지 않았습니다. 잠시 뒤 audit_status(workspace_token, scan_id)로 이어서 확인하세요.'
                           if data['state'] in ('queued', 'running') else data.get('notice') or '검사가 실패했습니다.')
            return out
        result, source = await self.scan_result(token, scan_id)
        analyses = []
        for f in pick_findings(result['findings'], int(max_analyses)):
            started = await self.start_analysis(token, scan_id, f['fingerprint'])
            analyses.append({'fingerprint': f['fingerprint'], 'title': clean(f.get('title')),
                             'severity': f.get('severity'), **started})
        out.update(source=source, summary=clean(result.get('summary')),
                   top_findings=[clean({k: f.get(k) for k in FINDING_FIELDS})
                                 for f in pick_findings(result['findings'], 10)],
                   analyses=analyses,
                   next=('GPU 해석은 1~3분 걸립니다. audit_status로 준비된 수정 지시(get_fix_prompt)를 확인하세요. '
                         '코드는 사용자가 허락한 경우에만 고치고, 고친 뒤 push 하면 check_fix로 해결 여부를 확인합니다.'))
        return out

    async def audit_status(self, token, scan_id):
        """검사 요약, 이 검사에서 시작한 해석들의 상태와 준비된 수정 지시를 한 번에."""
        scan = await self.get_scan(token, scan_id)
        out = {'scan_id': scan_id, 'scan_status': scan['status']}
        if 'summary' in scan:
            out.update(source=scan['source'], summary=scan['summary'], comparison=scan.get('comparison'))
        analyses = []
        for job, _ in self.store.analyses(token, scan_id):
            item = await self.get_analysis(token, job)
            entry = {'analysis_id': job, 'status': item['status']}
            for f in item.get('findings') or []:
                entry.update(fingerprint=f.get('fingerprint'), ready=f.get('ready'), reason=f.get('reason'))
            analyses.append(entry)
        out['analyses'] = analyses
        ready = [a['analysis_id'] for a in analyses if a.get('ready')]
        out['next'] = (f'수정 지시 준비됨: get_fix_prompt(analysis_id)로 받으세요 ({len(ready)}건).' if ready
                       else '아직 준비된 수정 지시가 없습니다. 해석이 끝나면 다시 확인하세요.')
        return out

    async def check_fix(self, token, scan_id, request_id, authorized, wait_seconds=MAX_WAIT_SECONDS):
        """같은 저장소를 직전 검사와 비교해 다시 검사하고, 해결·계속·새로·키 재발급 필요를 정리한다."""
        _, previous = await self.scan_result(token, scan_id)
        receipt = await self.start_scan(token, f"https://github.com/{previous['repository']}", request_id,
                                        authorized, scan_id)
        rescan_id = receipt['scan_id']
        data = await self.wait(token, rescan_id, 'scan', wait_seconds)
        out = {'previous_scan_id': scan_id, 'rescan_id': rescan_id, 'scan_status': data['state']}
        if data['state'] != 'done':
            out['next'] = '재검사가 아직 끝나지 않았습니다. audit_status(workspace_token, rescan_id)로 이어서 확인하세요.'
            return out
        result, source = await self.scan_result(token, rescan_id)
        groups = {'resolved': [], 'persisting': [], 'new': [], 'key_reissue_needed': []}
        for f in result['result'].get('findings') or []:
            loc = f.get('location') or {}
            row = clean({'fingerprint': f.get('fingerprint'), 'title': f.get('title'), 'severity': f.get('severity'),
                         'file': loc.get('file'), 'line': loc.get('start_line')})
            if f.get('status') == 'runtime_check_needed':
                groups['key_reissue_needed'].append(row)
            elif f.get('change') == 'resolved' or f.get('status') == 'code_resolved':
                groups['resolved'].append(row)
            elif f.get('change') in ('new', 'persisting'):
                groups[f['change']].append(row)
        out.update(source=source, previous_revision=previous['revision'], comparison=clean(result.get('comparison')),
                   **{k: v[:30] for k, v in groups.items()},
                   notice=('해결은 엔진이 다시 찾지 못했다는 뜻입니다. 키는 코드에서 지워도 발급처에서 폐기·재발급해야 합니다.'))
        if source['revision'] == previous['revision']:
            out['warning'] = '재검사한 커밋이 직전 검사와 같습니다. 고친 코드를 push 했는지 확인하세요.'
        return out

    async def verify_demo(self, mode='reference', wait_seconds=MAX_WAIT_SECONDS * 2, verify_job_id='',
                          sleep=asyncio.sleep, clock=time.monotonic):
        """실검증: 격리 샌드박스에서 수정 전 공격 성공 → 수정 후 차단 + 기능 테스트 통과를 실행으로 확인 (데모 과녁 전용)."""
        if mode not in ('reference', 'ai'):
            raise ValueError("mode는 reference(사람이 쓴 기준 수정본) 또는 ai(Red·Blue가 만든 공격·수정본)입니다.")
        if verify_job_id:
            if not re.fullmatch(r'[a-f0-9]{32}', verify_job_id):
                raise ValueError('verify_job_id 형식이 올바르지 않습니다.')
            job = verify_job_id  # 이어서 보기: 조회만 하고 새로 접수하지 않음
        else:
            job = await self.verify_job(mode)
        deadline = clock() + max(0, min(int(wait_seconds), MAX_WAIT_SECONDS * 2))
        while True:
            state = await self.request('GET', f'/api/verify/{job}')
            if state.get('status') in ('done', 'failed') or clock() >= deadline:
                break
            await sleep(POLL_SECONDS)
        out = {'verify_job_id': job, 'mode': mode, 'status': state.get('status'), 'reused': state.get('reused'),
               'scope': '데모 과녁(demo-vulnerable-site) 전용입니다. 사용자 저장소 실제검증은 아직 지원하지 않습니다.'}
        r = state.get('result') or {}
        if r:
            out.update(verdict=r.get('status'), sandbox=r.get('sandbox'), isolation_confirmed=r.get('isolation_confirmed'),
                       message=clean(r.get('message')), before_tests=r.get('before_tests'),
                       after_tests=r.get('after_tests'),
                       attacks=[clean({'id': a.get('id'), 'verdict': a.get('verdict'),
                                       'before': (a.get('before_evidence') or '')[:160],
                                       'after': (a.get('after_evidence') or '')[:160]}) for a in r.get('attacks') or []])
        if state.get('status') not in ('done', 'failed'):
            out['next'] = (f'실제검증이 아직 진행 중입니다. 잠시 뒤 verify_demo(verify_job_id="{job}")로 이어서 확인하세요. '
                           '같은 mode로 다시 불러도 새로 접수하지 않고 이 작업을 이어 봅니다.')
        return out

    async def verify_job(self, mode):
        """진행 중인 같은 mode 작업이 있으면 그 영수증을 쓰고, 없을 때만 POST로 접수한다."""
        async with self.verify_lock:
            job = self.verify_running.get(mode)
            if job:
                try:
                    state = await self.request('GET', f'/api/verify/{job}')
                except Gone:
                    state = {}  # 404: 만료가 확인된 영수증만 버린다
                except ValueError as exc:
                    # 503·타임아웃 같은 일시 오류: 작업은 살아 있을 수 있으니 영수증을 지키고 재접수하지 않는다
                    raise ValueError(f'진행 중인 실제검증({job}) 상태를 확인하지 못했습니다. 잠시 뒤 '
                                     f'verify_demo(verify_job_id="{job}")로 다시 확인하세요. 새로 접수하지 않았습니다.') from exc
                if state.get('status') in ('queued', 'running'):
                    return job
                self.verify_running.pop(mode, None)
            started = await self.request('POST', '/api/verify', {'target': 'demo', 'mode': mode})
            job = started.get('job_id', '')
            if not re.fullmatch(r'[a-f0-9]{32}', job):
                raise ValueError('실제검증 작업 식별자를 확인할 수 없습니다.')
            if started.get('status') in ('queued', 'running'):
                self.verify_running[mode] = job
            return job
