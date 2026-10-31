"""단계별 실패를 재현·인계할 수 있는 공개 진단 자료로 만듭니다. 추정과 확인을 구분합니다."""
import hashlib
import json


def failures(data):
    result = []
    targets = [('service', data)] + [(c['key'], c) for c in data.get('cases', [])]
    if data.get('browser'):
        targets.append(('browser', data['browser']))
    for key, target in targets:
        for check in target.get('checks', []):
            if check['status'] != 'fail':
                continue
            stage = check.get('stage') or target.get('stage') or key
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
                  '- 작업 ID: '+str(item['job_id']), '- 검사: '+item['check'],
                  '- 원인 상태: '+item['cause_status'], '- 원인: '+item['cause'],
                  '- 다음 작업: '+item['next_action'], '- 이슈: '+str(item['issue'] or '미등록'), '',
                  '```json', json.dumps({'observed': item['observed'], 'evidence': item['evidence'],
                                        'reproduce': item['reproduce']}, ensure_ascii=False, indent=2), '```', '']
    if not issues:
        lines += ['관측된 실패 없음. 미실행·부분 분석은 results.json과 화면에서 별도로 확인하세요.']
    return '\n'.join(lines)
