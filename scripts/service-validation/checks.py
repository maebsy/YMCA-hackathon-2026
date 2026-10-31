"""정답을 추측하지 않고 식별자·범위·실제 결과와 리포트의 일치를 확인합니다."""
from collections import Counter
import json
import re

from client import repo_url, CheckError
from evidence import digest, scrub


def strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    return []


def scan_checks(evidence, case, result):
    raw = result.get('result', {})
    target = raw.get('target', {})
    if repo_url(target.get('repo_url', '')).lower() != case['repository'].lower():
        raise CheckError('입력한 저장소와 검사 대상이 다릅니다.')
    revision = target.get('commit_sha', '')
    if not re.fullmatch(r'[a-fA-F0-9]{40}', revision):
        raise CheckError('검사 커밋 SHA가 없습니다.')
    if not re.fullmatch(r'[a-f0-9]{32}', result.get('scan_id', '')):
        raise CheckError('실제 검사 ID가 없습니다.')
    findings = raw.get('findings', [])
    case.update(source={'repository': case['repository'], 'revision': revision, 'scan_id': result['scan_id'],
                        'scanned_at': raw.get('scanned_at')}, summary=result.get('summary', {}),
                engine_finding_count=len(findings), llm_input_groups=len(result.get('findings', [])))
    evidence.check(case, '저장소·커밋·검사 ID 연결', 'pass', case['source'])
    statuses = Counter(f.get('status') for f in findings)
    declared = result.get('summary', {}).get('by_status', {})
    evidence.check(case, '엔진 요약 건수와 원본 항목 수',
                   'pass' if all(declared.get(k, 0) == v for k, v in statuses.items())
                   and sum(declared.values()) == len(findings) else 'fail',
                   {'actual': dict(statuses), 'summary': declared})
    case['engines'] = []
    for tool in ('osv', 'semgrep', 'gitleaks', 'config'):
        c = result.get('coverage', {}).get(tool, {})
        status = c.get('status', 'missing')
        level = 'pass' if status == 'ok' else 'warn' if status in ('no_target', 'skipped') else 'fail'
        data = {k: c.get(k) for k in ('status', 'engine', 'count', 'duration_sec')}
        case['engines'].append({'tool': tool, **data})
        evidence.check(case, tool + ' 실제 검사 실행', level, data)
    known = {f['fingerprint'] for f in findings}
    llm_items = result.get('findings', [])
    covered = set()
    for f in llm_items:
        ids = set(f.get('covers') or [f['fingerprint']])
        if not ids.issubset(known):
            raise CheckError('LLM 입력이 원본 검사의 항목과 연결되지 않습니다.')
        covered.update(ids)
    case['llm_input_covered_findings'] = len(covered)
    evidence.check(case, 'LLM 입력 범위', 'pass' if len(covered) == len(known) else 'warn',
                   {'engine_findings': len(known), 'covered_findings': len(covered), 'groups': len(llm_items),
                    'notice': '묶음 수와 취약점 수는 다릅니다. 제한 때문에 빠진 항목은 미분석입니다.'})


def llm_checks(evidence, case, finding, batch, health_model):
    items = batch.get('results', [])
    if batch.get('mode') != 'red_blue' or len(items) != 1 or items[0].get('fingerprint') != finding['fingerprint']:
        raise CheckError('GPU 응답 모드 또는 fingerprint가 실제 요청과 다릅니다.')
    item = items[0]
    if item.get('status') != 'done' or not isinstance(item.get('explanation'), dict):
        raise CheckError('GPU 분석 결과 실패 또는 생략: ' + str(item.get('error_code') or item.get('status')))
    e = item['explanation']
    rounds = e.get('red_rounds') or []
    record = {k: scrub(e.get(k)) for k in ('fingerprint', 'model', 'prompt_version', 'variant', 'summary',
        'why_risky', 'ai_fix_prompt', 'red_verdict', 'needs_manual_review', 'false_positive_suspect',
        'latency_ms', 'completion_tokens')}
    record['red_rounds'] = [{k: scrub(r.get(k)) for k in ('round', 'verdict', 'issues', 'latency_ms')} for r in rounds]
    record['input'] = {k: finding.get(k) for k in ('fingerprint', 'tool', 'category', 'file_path', 'package_name',
                                                 'installed_version', 'fixed_version')}
    case.setdefault('analyses', []).append(record)
    evidence.check(case, 'GPU 모델·토큰·처리 시간 증거', 'pass' if e.get('model') == health_model == batch.get('model')
                   and e.get('completion_tokens', 0) > 0 and e.get('latency_ms', 0) > 0
                   and e.get('prompt_version') == batch.get('prompt_version') else 'fail',
                   {k: record[k] for k in ('model', 'prompt_version', 'latency_ms', 'completion_tokens')})
    evidence.check(case, 'Blue 설명·수정 제안 수신', 'pass' if e.get('summary') and e.get('why_risky')
                   and e.get('fix_steps') and e.get('ai_fix_prompt') else 'fail',
                   '최종 Blue 산출물의 존재를 확인합니다. API는 Blue의 실시간 진행 로그를 제공하지 않습니다.')
    consistent = bool(rounds) and e.get('variant') == 'D' and e.get('fingerprint') == finding['fingerprint']
    consistent = consistent and rounds[-1].get('verdict') == e.get('red_verdict')
    consistent = consistent and all(r.get('latency_ms', 0) > 0 for r in rounds)
    if e.get('red_verdict') == 'pass':
        consistent = consistent and rounds[-1].get('issues') == []
    evidence.check(case, 'Red 라운드·최종 판정 일치', 'pass' if consistent else 'fail', record['red_rounds'])
    ready = consistent and e.get('red_verdict') == 'pass' and e.get('needs_manual_review') is False
    ready = ready and e.get('false_positive_suspect') is False
    ready = ready and all(e.get(key) for key in ('summary', 'why_risky', 'fix_steps', 'ai_fix_prompt'))
    record['ready'] = ready
    evidence.check(case, '수정 제안 전달 게이트', 'pass' if ready else 'warn',
                   'Red 검토 통과·수동 검토 불필요·오탐 의심 없음' if ready else '자동 수정 대상으로 확정하지 말고 사람 검토 필요')
    prompt = e.get('ai_fix_prompt', '')
    anchors = [finding.get('file_path'), finding.get('package_name')]
    evidence.check(case, '수정 지시의 실제 대상 언급', 'pass' if any(x and x in prompt for x in anchors) else 'warn',
                   '원본 파일 또는 패키지와 수정 지시를 대조했습니다. 수정의 의미적 정확성은 코드 리뷰가 필요합니다.')
    known_cves = set(re.findall(r'CVE-\d{4}-\d{4,}', json.dumps(finding), re.I))
    new_cves = set(re.findall(r'CVE-\d{4}-\d{4,}', prompt, re.I)) - known_cves
    evidence.check(case, '수정 지시의 취약점 번호 근거', 'warn' if new_cves else 'pass',
                   {'unmatched_cves': sorted(new_cves), 'notice': '미일치 번호는 추가 확인 대상이며 자동으로 환각이라고 단정하지 않습니다.'})
    return item


def report_checks(evidence, case, result, explanations, report, is_rescan=False):
    text = '\n'.join(strings(report))
    payload = {'scan': result['report_scan'], 'findings': result['findings'], 'explain_results': explanations}
    evidence.check(case, '리포트 입력의 실제 검사 연결', 'pass',
                   {'scan_id': result['scan_id'], 'commit': result['result']['target']['commit_sha'],
                    'input_sha256': digest(payload), 'finding_groups': len(result['findings']),
                    'explained_groups': len(explanations)})
    evidence.check(case, '리포트 대상 저장소 일치', 'pass' if result['report_scan']['site_name'] in report.get('title', '') else 'fail',
                   {'title': scrub(report.get('title', ''))})
    all_findings = result.get('result', {}).get('findings', result['findings'])
    unresolved = any(f.get('status') != 'code_resolved' and f.get('change') != 'resolved' for f in all_findings)
    incomplete = bool(result['report_scan'].get('not_checked'))
    complete = report.get('status', {}).get('text') == '완료'
    evidence.check(case, '미해결·미검사인데 완료라고 하지 않음', 'fail' if complete and (unresolved or incomplete) else 'pass',
                   {'report_status': report.get('status'), 'unresolved': unresolved, 'not_checked': incomplete})
    evidence.check(case, '재검사 증거 없이 재검사 완료라고 하지 않음',
                   'fail' if not is_rescan and ('재검사로 확인했습니다' in text or '재검사에서도 다시 나오지' in text) else 'pass',
                   {'is_rescan': is_rescan})
    if '매일 자동 검사' in text or '이메일로 알려' in text:
        evidence.check(case, '리포트 운영 기능 주장', 'warn', '자동 검사·이메일 알림 문구가 있습니다. 이 실행은 해당 기능의 운영을 검증하지 않았습니다.')
    for item in explanations:
        summary = item.get('explanation', {}).get('summary', '')
        evidence.check(case, '실제 LLM 설명이 리포트에 포함됨', 'pass' if summary and scrub(summary) in scrub(text) else 'fail',
                       {'fingerprint': item['fingerprint']})
    case['report_status'] = report.get('status')
    case['unanalysed_groups'] = max(0, len(result['findings']) - len(explanations))
    if case['unanalysed_groups']:
        evidence.check(case, '전체 항목 LLM 해석 범위', 'warn', f"{case['unanalysed_groups']}개 묶음은 LLM 미분석입니다. 표본 검증 통과를 전체 분석으로 해석하지 마세요.")


def rescan_checks(evidence, case, previous, current):
    comparison = current.get('comparison') or {}
    expected = previous['result']['target']['commit_sha']
    evidence.check(case, '재검사 기준 ID·커밋 일치', 'pass' if comparison.get('base_scan_id') == previous['scan_id']
                   and comparison.get('base_commit_sha') == expected else 'fail', comparison)
    same = current['result']['target']['commit_sha'] == expected
    evidence.check(case, '재검사 해석', 'pass', {'same_commit': same,
        'notice': '같은 커밋의 반복 검사입니다. 코드 수정 후 해결 검증을 한 것이 아닙니다.' if same else '공개 기본 브랜치 커밋이 변경됐습니다. 원인을 검토하세요.'})
