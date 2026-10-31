"""실서비스를 순차·제한 반복 검증합니다. 서버/검사기/프론트 코드를 import하지 않습니다."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
import time

from checks import scan_checks, llm_checks, report_checks, rescan_checks
from client import Client, CheckError, repo_url
from discover import discover
from evidence import Evidence, now


def outcome(checks):
    states = {x['status'] for x in checks}
    return 'failed' if 'fail' in states else 'review_required' if 'warn' in states or 'skipped' in states else 'passed'


def mcp_handoff(client, evidence, case, scan, analyses):
    good = [r for r in analyses if r.get('explanation', {}).get('red_verdict') == 'pass'
            and r['explanation'].get('needs_manual_review') is False
            and r['explanation'].get('false_positive_suspect') is False]
    if not good:
        evidence.check(case, '실제 결과 MCP 전달', 'skipped', 'Red 통과·자동 전달 가능한 분석 결과가 없습니다.')
        return
    doc = {'scan': {'repository': case['repository'].removeprefix('https://github.com/'),
        'revision': case['source']['revision'], 'scan_id': scan['scan_id'],
        'scanned_at': scan['result']['scanned_at'],
        'fingerprints': [f['fingerprint'] for f in scan['result']['findings']]}, 'results': good}
    # Token URLs never enter evidence, exceptions or console output. Revoke even if a call fails.
    link = client.request('POST', '/mcp/links', doc, headers={'Origin': client.base})
    path = '/mcp/h/' + link['token']
    try:
        listed = client.rpc(path, 'tools/call', {'name': 'list_findings', 'arguments': {}})
        listed = json.loads(listed['content'][0]['text'])
        if listed['source']['scan_id'] != scan['scan_id'] or listed['source']['revision'] != case['source']['revision']:
            raise CheckError('MCP가 다른 검사 결과를 반환했습니다.')
        prompt_result = client.rpc(path, 'tools/call', {'name': 'get_fix_prompt', 'arguments': {'fingerprint': good[0]['fingerprint']}})
        try:
            prompt_text = prompt_result['content'][0]['text']
            prompt_data = json.loads(prompt_text.split('<local_llm_proposal>\n', 1)[1].rsplit('\n</local_llm_proposal>', 1)[0])
            if (prompt_data['fingerprint'] != good[0]['fingerprint'] or not prompt_data.get('ai_fix_prompt')
                    or prompt_data['source']['revision'] != case['source']['revision']
                    or prompt_data['source']['scan_id'] != scan['scan_id']):
                raise CheckError('MCP 수정 프롬프트의 실제 검사·항목 연결이 다릅니다.')
        except (KeyError, IndexError, TypeError, ValueError):
            raise CheckError('MCP 수정 프롬프트에서 구조화된 실제 결과를 확인할 수 없습니다.') from None
        evidence.check(case, '실제 결과 MCP 전달', 'pass', '검사 ID·커밋 일치 및 실제 수정 프롬프트 수신. 결과별 연결은 검증 후 폐기합니다.')
    finally:
        client.request('POST', '/mcp/links/revoke', {'token': link['token'], 'revoke_token': link['revoke_token']},
                       headers={'Origin': client.base})
    try:
        client.request('GET', path + '/agent.txt', raw=True)
        evidence.check(case, 'MCP 검증 연결 폐기', 'fail', '폐기 후에도 결과 안내에 접근됩니다.')
    except CheckError as exc:
        evidence.check(case, 'MCP 검증 연결 폐기', 'pass' if str(exc).startswith('HTTP 404:') else 'fail',
                       '폐기된 연결의 접근 거부를 확인했습니다.' if str(exc).startswith('HTTP 404:') else str(exc))


def case_run(client, evidence, case, args, model):
    prefix = case['key']
    case['stage'] = 'scan'
    evidence.event(prefix, '실제 검사 접수 및 대기')
    case['scan_job'] = {}
    scan = client.job(prefix + '-scan', '/api/scans', {'repo_url': case['repository']}, args.scan_timeout, case['scan_job'])
    scan_checks(evidence, case, scan)
    eligible = [f for f in scan['findings'] if f.get('status') not in ('code_resolved', 'out_of_scope')]
    # Cover different detector categories before taking a second finding from one category.
    selected = []
    for category in ('dependency', 'code', 'secret', 'config'):
        match = next((f for f in eligible if f['category'] == category), None)
        if match:
            selected.append(match)
    selected += [f for f in eligible if f not in selected]
    if selected:
        offset = args.sample_offset % len(selected)
        selected = selected[offset:] + selected[:offset]
    selected = selected[:args.llm_per_repo]
    analyses = []
    if not selected:
        evidence.check(case, 'GPU Blue·Red 분석', 'skipped', '실제 검사에 분석 대상이 없어 모델을 호출하지 않았습니다. 성공으로 가장하지 않습니다.')
    for index, finding in enumerate(selected):
        case['stage'] = 'llm'
        case.setdefault('llm_jobs', []).append({'fingerprint': finding['fingerprint']})
        evidence.event(prefix, f'GPU Red/Blue 실제 분석 {index+1}/{len(selected)}')
        try:
            batch = client.job(prefix + '-llm-' + str(index), '/api/llm/explain/tasks',
                {'findings': [finding], 'mode': 'red_blue', 'environment': {'os': args.os, 'hosting': args.hosting}},
                args.llm_timeout, case['llm_jobs'][-1])
            analyses.append(llm_checks(evidence, case, finding, batch, model))
        except CheckError as exc:
            evidence.check(case, 'GPU 분석 실패', 'fail', str(exc))
    case['stage'] = 'report'
    payload = {'scan': scan['report_scan'], 'findings': scan['findings'], 'explain_results': analyses}
    report = client.request('POST', '/api/reports/plain?format=json', payload)
    report_checks(evidence, case, scan, analyses, report)
    case['reports'] = [{'label': '실제 점검 리포트 내용', 'path': evidence.report(prefix + '-report', report)}]
    for fmt, expected in (('html', 'text/html'), ('markdown', 'text/markdown')):
        body, mime = client.request('POST', '/api/reports/plain?format=' + fmt, payload, raw=True)
        evidence.check(case, fmt + ' 리포트 출력', 'pass' if expected in mime and scan['report_scan']['site_name'] in body else 'fail',
                       {'content_type': mime, 'characters': len(body)})
    if args.incident_drafts:
        case['stage'] = 'incident_draft'
        # Explicitly synthetic workflow input. NEVER represents an actual incident or sends a filing.
        incident = {'organization': {'name': '검증용 가상 기관', 'service_name': '자동화 검증용'},
                    'discovered_at': now(), 'incident_types': ['data_leak'],
                    'summary': '자동화 검증용 가상 사고. 실제 사고가 아닙니다.',
                    'personal_info': {'leaked': 'suspected', 'affected_count': 1, 'items': ['검증용 가상 항목']}}
        assessment = client.request('POST', '/api/reports/assess', incident)
        evidence.check(case, '사고 평가 API (가상 입력)', 'pass' if isinstance(assessment.get('needs'), list) else 'fail',
                       '실제 사고 여부나 법적 의무를 검증한 것이 아닙니다. 외부 기관 제출은 없습니다.')
        for kind in ('incident-24h', 'privacy-72h'):
            draft = client.request('POST', '/api/reports/' + kind, {'incident': incident, 'findings': scan['findings']})
            evidence.check(case, kind + ' 초안 생성', 'pass' if draft.get('kind') == kind.replace('-', '_') else 'fail',
                           {'synthetic_incident': True, 'missing_fields': len(draft.get('missing', []))})
            case['reports'].append({'label': kind + ' 가상 사고 초안', 'path': evidence.report(prefix + '-' + kind, draft)})
    if args.mcp:
        case['stage'] = 'mcp'
        try:
            mcp_handoff(client, evidence, case, scan, analyses)
        except CheckError as exc:
            evidence.check(case, '실제 결과 MCP 전달', 'fail', str(exc))
    else:
        evidence.check(case, 'MCP 전달', 'skipped', '--mcp를 지정하지 않았습니다.')
    if args.rescan:
        case['stage'] = 'rescan'
        case['rescan_job'] = {}
        current = client.job(prefix + '-rescan', '/api/scans', {'repo_url': case['repository'], 'previous': scan['result']},
                             args.scan_timeout, case['rescan_job'])
        rescan_checks(evidence, case, scan, current)
        case['rescan'] = {'revision': current['result']['target']['commit_sha'], 'comparison': current.get('comparison')}
    else:
        evidence.check(case, '재검사', 'skipped', '--rescan을 지정하지 않았습니다.')


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', required=True)
    p.add_argument('--repos-file', type=Path, default=Path(__file__).with_name('repositories.json'))
    p.add_argument('--repo', action='append', default=[])
    p.add_argument('--discover', type=int, default=0)
    p.add_argument('--github-query', default='user:StartBootstrap language:HTML')
    p.add_argument('--max-repos', type=int, default=3)
    p.add_argument('--repeat', type=int, default=1)
    p.add_argument('--interval', type=int, default=60)
    p.add_argument('--llm-per-repo', type=int, default=1)
    p.add_argument('--sample-offset', type=int, default=0, help='반복 실행마다 LLM 표본을 순환시키는 시작 위치')
    p.add_argument('--scan-timeout', type=int, default=600)
    p.add_argument('--llm-timeout', type=int, default=900)
    p.add_argument('--max-run-seconds', type=int, default=3600)
    p.add_argument('--os', choices=['windows', 'macos', 'linux'], default='linux')
    p.add_argument('--hosting', default='unknown')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--rescan', action='store_true')
    p.add_argument('--mcp', action='store_true')
    p.add_argument('--incident-drafts', action='store_true')
    p.add_argument('--browser', action='store_true')
    p.add_argument('--browser-repo', default='https://github.com/octocat/Spoon-Knife')
    p.add_argument('--server-ssh', help='선택: 운영자 SSH config 별칭. 공개 API 검증에는 필요 없음')
    p.add_argument('--gpu-ssh', help='선택: GPU 사용률 조회용 SSH config 별칭')
    p.add_argument('--ensure-services', action='store_true', help='기존 일반 서버 unit이 꺼져 있으면 start. 재시작/설정 변경 없음')
    args = p.parse_args()
    if not (1 <= args.max_repos <= 20 and 1 <= args.repeat <= 100 and 0 <= args.llm_per_repo <= 5
            and 10 <= args.interval <= 3600 and 60 <= args.max_run_seconds <= 86400):
        p.error('상한: 저장소1~20, 반복1~100, LLM0~5, 간격10~3600초, 실행60~86400초')
    if not (10 <= args.scan_timeout <= 1800 and 10 <= args.llm_timeout <= 3600 and 0 <= args.discover <= 10):
        p.error('검사10~1800초, LLM10~3600초, 검색0~10개')
    repositories = [{'url': url} for url in args.repo] if args.repo else json.loads(args.repos_file.read_text(encoding='utf-8'))
    if args.discover:
        repositories += discover(args.github_query, args.discover)
    urls = list(dict.fromkeys(repo_url(r['url']) for r in repositories))[:args.max_repos]
    if not urls:
        p.error('검사할 저장소가 없습니다.')
    settings = {k: v for k, v in vars(args).items() if k not in ('output', 'repos_file', 'resume', 'repo', 'server_ssh', 'gpu_ssh')}
    settings['repositories'] = urls
    evidence = Evidence(args.output, settings, args.resume)
    client = Client(args.base_url, evidence, deadline=time.monotonic() + args.max_run_seconds)
    from probe import Monitor, ensure_running
    monitor = Monitor(evidence.public, args.server_ssh, args.gpu_ssh)
    if args.server_ssh or args.gpu_ssh:
        monitor.start()
    try:
        if args.ensure_services:
            if not args.server_ssh:
                raise CheckError('--ensure-services에는 --server-ssh가 필요합니다.')
            try:
                ensure_running(args.server_ssh)
            except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                raise CheckError('기존 서비스 시작 실패. VPN·SSH·unit 설정을 확인하세요.') from exc
        health = client.request('GET', '/api/health')
        evidence.check(evidence.data, '백엔드 헬스', 'pass' if health.get('status') == 'ok' else 'fail', health)
        web, mime = client.request('GET', '/', raw=True)
        evidence.check(evidence.data, '공개 프론트 응답', 'pass' if 'text/html' in mime else 'fail', {'content_type': mime, 'characters': len(web)})
        model = None
        try:
            health = client.request('GET', '/api/llm/health')
            model = health.get('model')
            evidence.check(evidence.data, '실제 LLM 연결 헬스', 'pass' if model and health.get('status') == 'ok' else 'fail', health)
        except CheckError as exc:
            evidence.check(evidence.data, '실제 LLM 연결 헬스', 'fail', str(exc))
        if args.mcp:
            try:
                client.rpc('/mcp/service/rpc', 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                    'clientInfo': {'name': '72hours-validation', 'version': '1'}})
                tools = client.rpc('/mcp/service/rpc', 'tools/list', {})['tools']
                names = {t['name'] for t in tools}
                evidence.check(evidence.data, '전체 서비스 MCP 연결', 'pass' if {'start_scan', 'get_analysis', 'generate_report'} <= names else 'fail', sorted(names))
            except CheckError as exc:
                evidence.check(evidence.data, '전체 서비스 MCP 연결', 'fail', str(exc))
        evidence.check(evidence.data, '자동 검증의 범위 밖 기능', 'skipped',
                       '사용자 로그인·결제·실제 공격 재현·사용자 코드 수정은 이 스크립트가 수행하지 않습니다. 신고는 가상 입력으로 초안까지만 확인합니다.')
        for cycle in range(1, args.repeat+1):
            for index, url in enumerate(urls):
                key = f'cycle-{cycle}-repo-{index+1}'
                old = next((c for c in evidence.data['cases'] if c['key'] == key), None)
                if old and old.get('finished_at') and old['status'] in ('passed', 'review_required'):
                    continue
                case = {'key': key, 'repository': url, 'cycle': cycle, 'status': 'running', 'checks': [], 'started_at': now()}
                if old:
                    evidence.data['cases'].remove(old)
                evidence.data['cases'].append(case)
                evidence.save()
                try:
                    case_run(client, evidence, case, args, model)
                except (CheckError, KeyError, TypeError, ValueError) as exc:
                    evidence.check(case, '실행 중단 단계', 'fail', str(exc) if isinstance(exc, CheckError) else '서버 응답 계약 불일치: ' + type(exc).__name__)
                if args.server_ssh and case.get('scan_job', {}).get('error_code') == 'SCAN_ERROR':
                    from probe import ssh
                    try:
                        job_id = case['scan_job']['job_id']
                        case['server_diagnosis'] = json.loads(ssh(args.server_ssh,
                            'python3 apps/72hours/validation/code/server_diagnose.py ' + job_id))
                    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
                        case['server_diagnosis'] = {'code': 'DIAGNOSTIC_UNAVAILABLE',
                            'notice': '서버 진단 조회 실패. 원인을 단정하지 않습니다.'}
                case['status'] = outcome(case['checks'])
                case['finished_at'] = now()
                evidence.event(key, case['status'])
                if time.monotonic() >= client.deadline:
                    raise CheckError('전체 실행 한도에 도달해 남은 저장소를 실행하지 않았습니다.')
            if cycle < args.repeat:
                evidence.event('repeat', f'다음 반복까지 {args.interval}초 대기')
                time.sleep(min(args.interval, max(0, client.deadline-time.monotonic())))
        if args.browser:
            from browser import browser_check
            browser_check(client, evidence, repo_url(args.browser_repo), args.scan_timeout + args.llm_timeout)
        else:
            evidence.check(evidence.data, '브라우저 실제 클릭 흐름', 'skipped', '--browser를 지정하지 않았습니다. API 검증은 UI 검증을 대신하지 않습니다.')
        evidence.data['status'] = outcome(evidence.data['checks'] + [x for c in evidence.data['cases'] for x in c['checks']]
                                          + evidence.data.get('browser', {}).get('checks', []))
    except KeyboardInterrupt:
        evidence.data['status'] = 'interrupted'
        evidence.event('interrupted', '중단했습니다. 이미 접수된 서버 작업은 계속될 수 있습니다. 동일 폴더 --resume으로 조회할 수 있습니다.')
    except (CheckError, ImportError) as exc:
        evidence.data['status'] = 'incomplete'
        evidence.check(evidence.data, '전체 실행', 'fail', str(exc))
    finally:
        monitor.stop()
    evidence.data['finished_at'] = now()
    evidence.save()
    print(json.dumps({'status': evidence.data['status'], 'dashboard': str(evidence.public / 'index.html')}, ensure_ascii=False))
    return 1 if evidence.data['status'] in ('failed', 'incomplete', 'interrupted') else 0


if __name__ == '__main__':
    raise SystemExit(main())
