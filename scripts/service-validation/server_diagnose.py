"""서버에서 실행: 지정 job의 로그를 대조하고 허용된 진단 필드만 출력합니다."""
import argparse
import json
import re
import subprocess


def diagnose(records, job_id):
    selected, started = [], None
    for record in records:
        message = record.get('MESSAGE', '')
        stamp = int(record.get('__REALTIME_TIMESTAMP', '0'))
        if 'scan '+job_id+' failed' in message:
            selected, started = [message], stamp
        elif started is not None:
            if stamp-started > 2_000_000 or re.search(r'scan [a-f0-9]{32} failed', message):
                break
            selected.append(message)
    text = '\n'.join(selected)
    confirmed = all(marker in text for marker in ('_package_finding', 'FindingInput', 'string_too_long'))
    confirmed = confirmed and bool(re.search(r'(?m)^what\s*$', text)) and '2000' in text
    return {'job_id': job_id, 'matched_job_log': started is not None,
            'code': 'FINDING_WHAT_TOO_LONG' if confirmed else 'CAUSE_NOT_CONFIRMED',
            'field': 'FindingInput.what' if confirmed else None,
            'maximum_characters': 2000 if confirmed else None,
            'location': 'backend/app/llm/engine_adapter.py::_package_finding' if confirmed else None,
            'journal_timestamp_us': started,
            'notice': 'job ID가 일치하는 로그와 제한된 예외 표식만 대조했습니다. 원문 로그·코드·입력값은 공개하지 않습니다.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('job_id')
    args = p.parse_args()
    if not re.fullmatch(r'[a-f0-9]{32}', args.job_id):
        p.error('유효한 job ID가 필요합니다.')
    output = subprocess.run(['journalctl', '--user', '-u', '72hours-backend', '--since', '1 day ago',
                             '-n', '3000', '--no-pager', '-o', 'json'], capture_output=True, text=True, timeout=15, check=True)
    print(json.dumps(diagnose([json.loads(line) for line in output.stdout.splitlines()], args.job_id), ensure_ascii=True))
