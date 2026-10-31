"""단계별 실패를 재현·인계할 수 있는 공개 진단 자료로 만듭니다. 추정과 확인을 구분합니다."""
import hashlib
import json
import re


def quality_failures(quality):
    rows = []
    revision = quality.get('source_revision', '')
    revision = revision if re.fullmatch(r'[0-9a-f]{40}', revision) else None
    for check in quality.get('failed_checks', []):
        historical = check['name'] == '설계의 과거 커밋 비밀키 탐지'
        known = {'설계의 과거 커밋 비밀키 탐지': (87, 'HISTORICAL_SECRET_NOT_DETECTED'),
                 '수정 버전 다운그레이드 금지': (92, 'FIX_VERSION_DOWNGRADE'),
                 '사전 출시 최소 수정 버전': (92, 'FIX_VERSION_PRERELEASE'),
                 'KEV 조회 실패와 정상 부재 구분': (93, 'KEV_UNAVAILABLE_AS_FALSE')}.get(check['name'])
        code = known[1] if known else 'ENGINE_EXPECTATION_FAILED'
        rows.append({'signature': hashlib.sha256(('engine_quality|'+code+'|'+check['name']).encode()).hexdigest()[:16],
            'case': 'engine_quality', 'stage': 'engine_quality', 'check': check['name'],
            'repository': None, 'revision': revision, 'job_id': None,
            'scan_id': quality.get('historical_scan_id') if historical else None,
            'code': code, 'observed': check,
            'cause_status': 'unconfirmed',
            'cause': ('이전 커밋에만 남긴 합성 키의 탐지 기대값과 실제 결과가 다릅니다. '
                      '이 결과만으로 검사 명령의 내부 원인을 확정하지 않습니다.' if historical else
                      '배포 엔진의 정답 사례가 기대값과 다릅니다. 검사기 실행 상태와 변환 추적을 대조해야 합니다.'),
            'evidence': {'artifact': 'engine-quality.json', 'source_revision': revision},
            'issue': 'https://github.com/maebsy/YMCA-hackathon-2026/issues/'+str(known[0]) if known else None,
            'next_action': ({87: '#87에서 현재 파일 검사와 Git 이력 검사의 지원 범위를 확인하고, 이력 검사를 구현하거나 설계 범위를 정정하세요.',
                             92: 'security_engine/normalize.py의 생태계별 버전 비교와 다운그레이드 차단을 수정하고 추천 버전의 취약 여부를 다시 확인하세요.',
                             93: 'backend/app/llm/intel.py의 조회 실패를 unknown으로 구분하고 캐시의 출처·갱신 시각을 보존하세요.'}.get(known[0])
                            if known else 'engine-quality.json의 기대값·실측값·coverage·flow를 대조해 엔진 담당자에게 전달하세요.'),
            'reproduce': {'command': 'python scripts/service-validation/engine_quality.py --source <동일 배포 커밋 경로> --output <새 결과 JSON>',
                          'source_revision': revision, 'check': check['name']},
            'revision_note': '배포 엔진 커밋이며 공개 저장소 커밋이 아닙니다. 독립 합성 사례에는 API job ID가 없습니다.'})
    return rows


def failures(data):
    result = quality_failures(data.get('engine_quality', {}))
    has_quality_failures = bool(result)
    targets = [('service', data)] + [(c['key'], c) for c in data.get('cases', [])]
    if data.get('browser'):
        targets.append(('browser', data['browser']))
    for key, target in targets:
        for check in target.get('checks', []):
            if check['status'] != 'fail':
                continue
            if key == 'service' and has_quality_failures and check['name'] == '엔진 설계 적합성 정답 검증':
                continue  # Expanded above into individual expectations, not a duplicate generic failure.
            stage = check.get('stage') or target.get('stage') or ('scan' if target.get('scan_job', {}).get('status') == 'failed' else key)
            job = target.get('scan_job', {})
            error = str(check['detail'])
            code = job.get('error_code') or ('SCAN_ERROR' if 'SCAN_ERROR' in error else 'CHECK_FAILED')
            diagnosis = target.get('server_diagnosis', {}) if stage == 'scan' or code == 'SCAN_ERROR' else {}
            confirmed = diagnosis.get('code') == 'FINDING_WHAT_TOO_LONG' and diagnosis.get('job_id') == job.get('job_id')
            cause = ('의존성 취약점 설명을 묶는 _package_finding이 FindingInput.what의 2,000자 제한을 초과했습니다.'
                     if confirmed else '현재 증거로 근본 원인을 확정할 수 없습니다. 아래 관측 사실과 다음 확인 절차를 사용하세요.')
            action = ('backend/app/llm/engine_adapter.py의 패키지 묶음 설명에 길이 제한과 원본 covers 보존을 적용하고 같은 저장소를 재검사하세요.'
                      if confirmed else '해당 단계의 응답·작업 ID로 서버 로그를 대조하세요. 검사 실패 후 LLM/리포트가 실행되지 않은 것은 후속 영향입니다.')
            if stage in ('llm', 'report', 'mcp', 'rescan', 'browser') and not confirmed:
                action = {'llm': '모델 health, 해당 LLM job ID, Red 라운드/토큰/응답 계약을 확인하세요.',
                          'report': '실제 검사 ID·커밋·미해결 수와 리포트 내용을 대조하세요.',
                          'mcp': 'MCP 도구 응답과 검사 ID·커밋, 연결 폐기 결과를 확인하세요.',
                          'rescan': '이전 scan ID·기준 커밋과 comparison을 대조하세요.',
                          'browser': '브라우저 캡처와 UI 선택자, 실제 API 응답 여부를 확인하세요.'}[stage]
            signature = hashlib.sha256((target.get('repository', 'service')+'|'+stage+'|'+code+'|'+check['name']).encode()).hexdigest()[:16]
            result.append({'signature': signature, 'case': key, 'stage': stage, 'check': check['name'],
                'repository': target.get('repository'), 'revision': target.get('source', {}).get('revision'),
                'job_id': check.get('job_id') or job.get('job_id'), 'code': code, 'observed': check['detail'],
                'cause_status': 'confirmed' if confirmed else 'unconfirmed', 'cause': cause,
                'evidence': diagnosis, 'issue': 'https://github.com/maebsy/YMCA-hackathon-2026/issues/83' if confirmed else None,
                'next_action': action, 'reproduce': {'method': 'POST', 'path': '/api/scans',
                    'body': {'repo_url': target['repository']}} if target.get('repository') else None,
                'revision_note': '검사 완료 전에 실패했으면 서버의 실제 검사 커밋은 미확인입니다. 현재 GitHub HEAD와 동일하다고 가정하지 않습니다.'})
    return result


def handoff(data, issues):
    lines = ['# 72hours 검증 인계', '', '실행 시작: '+data['started_at'], '상태: '+data['status'],
             '', '관측 실패만 기록합니다. 원인이 확정되지 않은 항목은 추정으로 해결 처리하지 않습니다.', '']
    for item in issues:
        lines += ['## '+item['case']+' / '+item['stage']+' / '+item['code'], '',
                  '- 저장소: '+str(item['repository']), '- 커밋: '+str(item['revision'] or '미확인'),
                  '- 작업 ID: '+str(item['job_id']), '- 엔진 검사 ID: '+str(item.get('scan_id') or '해당 없음'),
                  '- 커밋 해석: '+item['revision_note'], '- 검사: '+item['check'],
                  '- 원인 상태: '+item['cause_status'], '- 원인: '+item['cause'],
                  '- 다음 작업: '+item['next_action'], '- 이슈: '+str(item['issue'] or '미등록'), '',
                  '```json', json.dumps({'observed': item['observed'], 'evidence': item['evidence'],
                                        'reproduce': item['reproduce']}, ensure_ascii=False, indent=2), '```', '']
    if not issues:
        lines += ['관측된 실패 없음. 미실행·부분 분석은 results.json과 화면에서 별도로 확인하세요.']
    return '\n'.join(lines)
