"""배포된 엔진을 독립 임시 사례로 검사합니다. 서비스/검사 대상 앱을 수정하거나 실행하지 않습니다."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile


def annotations(root):
    labels = []
    for path in sorted(root.iterdir()):
        if path.suffix not in ('.js', '.tsx', '.py', '.sql', '.rules'):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            match = re.search(r'(?:^\s*(?://|#))\s*(ruleid|ok):\s*([\w,-]+)', line)
            if match:
                for rule in match[2].split(','):
                    labels.append({'file': path.name, 'line': number+1, 'rule': 'vibe-coding/'+rule,
                                   'expected': match[1] == 'ruleid'})
    return labels


def evaluate_labels(labels, findings):
    rows = []
    for label in labels:
        detected = any(f['rule_id'] == label['rule'] and f['location']['file'] == label['file']
                       and f['location'].get('start_line', 0) <= label['line'] <= (f['location'].get('end_line') or 0)
                       for f in findings)
        outcome = ('TP' if detected else 'FN') if label['expected'] else ('FP' if detected else 'TN')
        rows.append({**label, 'detected': detected, 'outcome': outcome})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    sys.path[:0] = [str(source), str(source/'backend')]
    # Load only scanner executable paths, never API credentials or the fingerprint secret.
    config = Path.home()/'.config/72hours/backend.env'
    if config.exists():
        for line in config.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key in ('SECURITY_ENGINE_OSV_BIN', 'SECURITY_ENGINE_SEMGREP_BIN', 'SECURITY_ENGINE_GITLEAKS_BIN'):
                os.environ[key] = value.strip().strip('"').strip("'")
    from security_engine import scan, build_llm_input, ScanOptions
    from app.llm.engine_adapter import from_engine_payload
    from app.reports.schemas import PlainReportRequest
    from app.reports.plain import build_plain_report
    from app.routers.scans import _report_scan
    from evidence import atomic_json
    started = datetime.now(timezone.utc).isoformat()
    data = {'started_at': started, 'source_revision': source.name, 'checks': [], 'rule_cases': [],
            'snapshots': {}, 'scope': '배포된 실제 검사기 + 합성 정답 사례. 일반 저장소 전체 정확도나 실제 공격 성공률의 추정치가 아닙니다.'}
    def check(name, expected, actual, passed, basis, group='contract'):
        data['checks'].append({'name': name, 'expected': expected, 'actual': actual,
                               'status': 'pass' if passed else 'fail', 'basis': basis, 'group': group})
        atomic_json(args.output, data)
    def save_snapshot(name, result):
        data['snapshots'][name] = {'scan_id': result['scan_id'], 'coverage':
            {k: {field: v.get(field) for field in ('status', 'engine', 'version', 'count', 'registry_used')} for k, v in result['coverage'].items()},
            'summary': result['summary'], 'findings': [{k: f.get(k) for k in
                ('fingerprint', 'tool', 'category', 'rule_id', 'severity', 'status', 'change', 'location', 'flags', 'package', 'aliases')} for f in result['findings']]}
    def pipeline(name, result):
        payload = build_llm_input(result, max_items=50)
        try:
            converted = from_engine_payload(payload)
            known = {f['fingerprint'] for f in result['findings']}
            covered = [identity for f in converted for identity in (f.covers or [f.fingerprint])]
            check(name+' 엔진→LLM 어댑터 식별자 보존', '누락/중복/외부 ID 없음 (50건 이하 사례)',
                  {'engine': len(known), 'covered': len(covered), 'groups': len(converted)},
                  set(covered) == known and len(covered) == len(set(covered)), 'security_engine/README.md §3-1, backend/app/llm/engine_adapter.py')
            report = build_plain_report(PlainReportRequest(scan=_report_scan(result, payload, 'https://github.com/fixture/design-oracle'),
                                                          findings=converted, explain_results=[]), datetime.now(timezone.utc)).model_dump(mode='json')
            blob = json.dumps(report, ensure_ascii=False)
            trace = []
            for original in result['findings']:
                group = next((f for f in converted if original['fingerprint'] in (f.covers or [f.fingerprint])), None)
                trace.append({'fingerprint': original['fingerprint'], 'rule': original['rule_id'],
                    'file': original['location']['file'], 'severity': original['severity'], 'state': original['status'],
                    'llm_group': group.fingerprint if group else None,
                    'report_title': group.title if group else None,
                    'report_present': bool(group and group.title in blob)})
            data.setdefault('flow', {})[name] = {'engine_findings': len(result['findings']),
                'llm_items': len(payload['items']), 'adapter_groups': len(converted),
                'truncated': payload['truncated'], 'trace': trace}
            check(name+' 원본 항목→묶음→리포트 추적', '모든 원본 항목이 LLM 묶음과 리포트 제목에 연결됨',
                  {'total': len(trace), 'linked':sum(row['report_present'] for row in trace)},
                  all(row['report_present'] for row in trace), '원본 fingerprint → covers → 실제 리포트 내용')
            check(name+' 비밀값 제거', '합성 비밀값이 결과·LLM 입력·리포트에 없음', '원문 미노출 여부',
                  secret not in json.dumps(result) + json.dumps(payload) + blob, 'security_engine/README.md §4')
            unsafe = any(f['status'] in ('code_issue', 'runtime_check_needed', 'out_of_scope') for f in result['findings'])
            check(name+' 미해결/미검사 리포트', '남은 문제나 미검사 영역이 있으면 완료 금지', report['status'],
                  not ((unsafe or payload['not_checked']) and report['status']['text'] == '완료'), 'docs/system-flow.md: 재검사 통과 후 완료')
            data.setdefault('reports', {})[name] = report
            return payload
        except Exception as exc:
            check(name+' 엔진→리포트 변환', '실제 결과를 변환할 수 있음', type(exc).__name__, False,
                  'backend/app/llm/engine_adapter.py → app/reports/plain.py')
            return payload
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rules = source/'security_engine/rules'
    data['rules_sha256'] = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(rules.glob('*.yml')))).hexdigest()
    rng = random.Random(42)
    secret = 'sk'+'_live_'+''.join(rng.choice(string.ascii_letters+string.digits) for _ in range(24))
    with tempfile.TemporaryDirectory(prefix='engine-oracle-') as directory:
        root = Path(directory)
        samples = root/'rules'
        samples.mkdir()
        for path in rules.iterdir():
            if path.suffix in ('.js', '.tsx', '.py', '.sql', '.rules'):
                shutil.copyfile(path, samples/path.name)
        labels = annotations(samples)
        tested = scan(samples, options=ScanOptions(tools=('semgrep',), timeout_sec=180))
        save_snapshot('rule_corpus', tested)
        rows = evaluate_labels(labels, tested['findings'])
        data['rule_cases'] = rows
        counts = Counter(r['outcome'] for r in rows)
        data['labeled_metrics'] = dict(counts)
        check('우리 규칙의 양성·음성 정답 대조', 'FN=0, FP=0, 표식 사례 및 검사기 정상 실행', dict(counts),
              bool(labels) and tested['coverage']['semgrep']['status'] == 'ok' and not counts['FN'] and not counts['FP'],
              '배포본 rules/*의 ruleid/ok 표식; 규칙 회귀 사례이므로 실세계 정확도로 일반화 불가', 'detection')
        check('서비스 코드 검사 규칙 범위', '우리 규칙만 사용, registry 사용 안 함',
              {'rules': sorted({f['rule_id'] for f in tested['findings']}), 'registry_used': tested['coverage']['semgrep']['registry_used']},
              tested['coverage']['semgrep']['registry_used'] is False and all(f['rule_id'].startswith('vibe-coding/') for f in tested['findings']),
              'security_engine/README.md §5', 'detection')
        site = root/'site'
        site.mkdir()
        def put(name, text):
            path = site/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        unsafe_sql = 'app.get("/u", (req, res) => {\n db.query("SELECT * FROM users WHERE id = " + req.query.id);\n eval(req.query.expr); // nosemgrep\n});\n'
        put('api.js', unsafe_sql)
        put('secret.js', 'const stripeKey = "'+secret+'"; // gitleaks:allow\n')
        put('.env', 'DEMO_MARKER=synthetic_value_only\n')
        put('public/backup.sql', '-- synthetic empty backup\n')
        put('safe.js', 'db.query("SELECT * FROM users WHERE id = ?", [id]);\n')
        def lockfile(version):
            put('package.json', json.dumps({'name':'design-oracle','version':'1.0.0','dependencies':{'lodash':version}}))
            put('package-lock.json', json.dumps({'name': 'design-oracle', 'version': '1.0.0', 'lockfileVersion': 3,
                'requires': True, 'packages': {'': {'name': 'design-oracle','version':'1.0.0','dependencies': {'lodash': version}},
                'node_modules/lodash': {'version': version, 'resolved': 'https://registry.npmjs.org/lodash/-/lodash-'+version+'.tgz'}}}))
        lockfile('4.17.15')
        options = ScanOptions(timeout_sec=180)
        first = scan(site, options=options)
        save_snapshot('vulnerable', first)
        fs = first['findings']
        cve = [f for f in fs if 'CVE-2021-23337' in [f['rule_id'], *f.get('aliases', [])]]
        check('OSV 알려진 취약 버전', 'lodash 4.17.15에서 CVE-2021-23337 탐지',
              {'matches': len(cve), 'coverage': first['coverage']['osv']['status']},
              bool(cve) and first['coverage']['osv']['status'] == 'ok', 'https://osv.dev/vulnerability/GHSA-35jh-r3h4-6jhm', 'detection')
        secrets = [f for f in fs if f['tool'] == 'gitleaks']
        sql = [f for f in fs if f['rule_id'].endswith('sql-string-concat')]
        check('합성 비밀키·SQL 양성 및 안전한 SQL 음성', 'secret.js와 api.js 탐지, safe.js SQL 경고 없음',
              {'secret_matches': len(secrets), 'sql_files': [f['location']['file'] for f in sql]},
              bool(secrets) and any(f['location']['file'] == 'api.js' for f in sql) and not any(f['location']['file'] == 'safe.js' for f in sql),
              '독립 합성 사례: 문자열 SQL → 매개변수 SQL, 실행하지 않는 합성 키', 'detection')
        expected_config = {'config/env-file-committed', 'config/db-file-public'}
        check('자체 설정 검사', sorted(expected_config), sorted({f['rule_id'] for f in fs if f['tool']=='config'}),
              expected_config <= {f['rule_id'] for f in fs}, 'security_engine/README.md §5-1', 'detection')
        expected_categories = {'osv': 'dependency', 'semgrep': 'code', 'gitleaks': 'secret', 'config': 'config'}
        check('도구별 분류·중복 제거', expected_categories,
              {'findings':len(fs),'unique_ids':len({f['fingerprint'] for f in fs})},
              all(expected_categories[f['tool']] == f['category'] for f in fs) and len(fs)==len({f['fingerprint'] for f in fs}),
              'security_engine/README.md §3')
        check('요약 집계 보존', '원본의 상태·분류·위험도 집계와 일치', first['summary'],
              all(first['summary']['by_category'].get(k)==v for k,v in Counter(f['category'] for f in fs).items())
              and all(first['summary']['by_severity'].get(k)==v for k,v in Counter(f['severity'] for f in fs).items()),
              'security_engine/README.md §3')
        evals = [f for f in fs if f['rule_id'].endswith('js-eval-dynamic')]
        check('규칙 위험도·CWE 정규화', 'SQL critical/CWE-89, eval high/CWE-95',
              [{'rule': f['rule_id'], 'severity': f['severity'], 'cwe': f.get('cwe')} for f in sql+evals],
              bool(sql) and bool(evals) and all(f['severity']=='critical' and 'CWE-89' in f.get('cwe',[]) for f in sql)
              and all(f['severity']=='high' and 'CWE-95' in f.get('cwe',[]) for f in evals),
              'rules/vibe-coding.yml의 engine_severity/CWE 계약')
        check('억제 주석을 무시하고 주의 표시', 'nosemgrep 및 gitleaks:allow에도 탐지하고 suppressed_by_comment 표시',
              {'eval_flags':[f['flags'] for f in evals], 'secret_flags':[f['flags'] for f in secrets]},
              bool(evals) and bool(secrets) and all('suppressed_by_comment' in f['flags'] for f in evals+secrets),
              'security_engine/README.md §4')
        pipeline('vulnerable', first)
        put('api.js', '// line shifted\n'+unsafe_sql.replace('"SELECT * FROM users WHERE id = " + req.query.id', '"SELECT * FROM users WHERE id = ?", [req.query.id]'))
        put('secret.js', 'const stripeKey = process.env.STRIPE_KEY;\n')
        lockfile('4.17.21')
        second = scan(site, previous=first, options=options)
        save_snapshot('fixed', second)
        by_id = {f['fingerprint']:f for f in second['findings']}
        check('코드 수정 재검사', 'SQL은 code_resolved / 줄이 이동한 eval은 같은 ID의 code_issue',
              {'sql':[by_id.get(f['fingerprint'],{}).get('status') for f in sql], 'eval':[by_id.get(f['fingerprint'],{}).get('status') for f in evals]},
              bool(sql) and bool(evals) and all(by_id.get(f['fingerprint'],{}).get('status')=='code_resolved' for f in sql)
              and all(by_id.get(f['fingerprint'],{}).get('status')=='code_issue' for f in evals), 'security_engine/README.md: 4가지 상태·fingerprint', 'rescan')
        check('비밀키 삭제 후 운영 확인', '삭제해도 runtime_check_needed + rotate_secret',
              [by_id.get(f['fingerprint'],{}).get('status') for f in secrets],
              bool(secrets) and all(by_id.get(f['fingerprint'],{}).get('status')=='runtime_check_needed'
                                   and 'rotate_secret' in by_id[f['fingerprint']]['flags'] for f in secrets),
              'security_engine/README.md: 키 폐기·재발급 필요', 'rescan')
        check('OSV 수정 버전 재검사', '4.17.21에서는 특정 CVE가 code_resolved; 다른 신규 CVE의 부재를 주장하지 않음',
              [by_id.get(f['fingerprint'],{}).get('status') for f in cve],
              bool(cve) and all(by_id.get(f['fingerprint'],{}).get('status')=='code_resolved' for f in cve),
              'https://osv.dev/vulnerability/GHSA-35jh-r3h4-6jhm', 'rescan')
        pipeline('fixed', second)
        unavailable = scan(site, previous=first, options=ScanOptions(tools=('config',), timeout_sec=180))
        save_snapshot('tools_skipped', unavailable)
        lost = [f for f in unavailable['findings'] if f['tool'] != 'config']
        check('검사하지 못한 문제를 해결 처리하지 않음', '미실행 도구의 이전 문제는 out_of_scope / unverifiable',
              dict(Counter(f['status'] for f in lost)), bool(lost) and all(f['status']=='out_of_scope' and f['change']=='unverifiable' for f in lost),
              'security_engine/README.md: 도구 실패는 해결 아님', 'rescan')
        pipeline('tools_skipped', unavailable)
        # Design explicitly mentions old commits. Test a removed synthetic key with NO previous scan supplied.
        history = root/'history'
        history.mkdir()
        def git(*args):
            subprocess.run(['git', '-C', str(history), *args], check=True, capture_output=True, timeout=20)
        git('init', '-q')
        (history/'secret.js').write_text('const stripeKey = "'+secret+'";\n')
        git('add', '.')
        git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','synthetic fixture')
        (history/'secret.js').write_text('const stripeKey = process.env.STRIPE_KEY;\n')
        git('add', '.')
        git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','remove synthetic secret')
        past = scan(history, options=ScanOptions(tools=('gitleaks',), timeout_sec=180))
        save_snapshot('historical_secret', past)
        check('설계의 과거 커밋 비밀키 탐지', '현재 파일에서 삭제돼도 이전 커밋에 남은 합성 키를 찾음',
              {'findings': len(past['findings']), 'coverage': past['coverage']['gitleaks']['status']},
              any(f['tool']=='gitleaks' for f in past['findings']),
              'docs/system-flow.md §3: 비밀키(과거 커밋 포함). 현재 파일 검사와 기록 검사는 별개임', 'design_gap')
    from data_quality import check_data_contracts, collect_freshness
    from security_engine.normalize import pick_fix_version
    from app.llm.intel import HttpThreatIntel
    import httpx
    check_data_contracts(check, pick_fix_version, HttpThreatIntel, httpx.MockTransport, httpx.Response)
    data['source_freshness'] = collect_freshness()
    data['freshness_notice'] = '외부 원본을 지금 조회한 결과입니다. 기존 검사/LLM 캐시가 이 버전을 사용했다는 증명은 아닙니다. unavailable은 최신 여부 미확인입니다.'
    data['finished_at'] = datetime.now(timezone.utc).isoformat()
    data['status'] = 'failed' if any(c['status']=='fail' for c in data['checks']) else 'passed'
    atomic_json(args.output, data)
    print(json.dumps({'status': data['status'], 'checks': len(data['checks']), 'labeled_metrics': data['labeled_metrics']}))
    return int(data['status']=='failed')


if __name__ == '__main__':
    raise SystemExit(main())
