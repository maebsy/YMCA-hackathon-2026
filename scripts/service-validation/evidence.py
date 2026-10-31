"""공개 산출물은 허용 필드만 기록하고, 원본 코드·토큰·로그는 저장하지 않습니다."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re


def now():
    return datetime.now(timezone.utc).isoformat()


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if not isinstance(value, str):
        return value
    for pattern in (
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
        r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}',
        r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})',
        r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*',
        r'''(?i)(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*(?:"[^"\n]+"|'[^'\n]+'|[^\s,;]+)''',
        r'/mcp/h/[A-Za-z0-9_-]{43}',
    ):
        value = re.sub(pattern, '[REDACTED]', value, flags=re.DOTALL)
    return value


_JOB_ID = re.compile(r'(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])')


def job_ref(job_id):
    return 'job-' + hashlib.sha256(job_id.encode()).hexdigest()[:12]


def public_ids(value):
    """공개 산출물의 작업 ID(32자리)를 참조값으로 바꿉니다.

    GET /api/scans/{job_id} 는 인증 없이 전체 결과를 돌려주므로 ID를 공개하면 결과 전체가 열립니다(#84 리뷰).
    같은 ID는 같은 참조값이 되어 화면에서 서로 대조할 수 있고, 원래 ID는 private/state.json 에만 남습니다.
    """
    if isinstance(value, dict):
        return {k: public_ids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [public_ids(v) for v in value]
    if isinstance(value, str):
        return _JOB_ID.sub(lambda m: job_ref(m.group(0)), value)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, data):
    tmp = path.with_suffix(path.suffix + '.next')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


class Evidence:
    def __init__(self, output, settings, resume=False):
        self.output = Path(output).resolve()
        self.public = self.output / 'public'
        self.private = self.output / 'private'
        self.public.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(exist_ok=True)
        self.private.chmod(0o700)
        self.state_path = self.private / 'state.json'
        self.path = self.public / 'results.json'
        if self.state_path.exists():
            if not resume:
                raise ValueError('기존 실행 폴더입니다. --resume 또는 새 --output을 사용하세요.')
            self.state = json.loads(self.state_path.read_text(encoding='utf-8'))
            if self.state['settings'] != settings:
                raise ValueError('재개할 실행의 주소·입력·한도 설정이 다릅니다.')
            # 재개는 실제 ID가 남은 비공개 사본에서 읽습니다 (예전 실행은 공개 파일만 있음)
            source = self.private / 'results.json'
            self.data = json.loads((source if source.exists() else self.path).read_text(encoding='utf-8'))
        else:
            self.state = {'settings': settings, 'jobs': {}}
            self.data = {'started_at': now(), 'updated_at': now(), 'status': 'running',
                         'settings': settings, 'checks': [], 'cases': [], 'events': [],
                         'notice': '실측 계약 검증입니다. Red 통과는 실제 공격 재현이나 취약점 해결 증명이 아닙니다.'}
        self.save()

    def save(self):
        from diagnostics import failures, handoff
        self.data.setdefault('run_id', digest({'started_at': self.data['started_at'], 'settings': self.state['settings']})[:20])
        self.data['updated_at'] = now()
        self.data['failures'] = scrub(failures(self.data))
        atomic_json(self.state_path, self.state)
        self.state_path.chmod(0o600)
        # 실행 중 데이터(self.data)는 실제 ID를 유지해 서버 진단에 쓰고, 공개 파일에만 참조값을 씁니다
        atomic_json(self.private / 'results.json', self.data)
        public = public_ids(scrub(self.data))
        atomic_json(self.path, public)
        atomic_json(self.public / 'failures.json', public['failures'])
        (self.public / 'handoff.md').write_text(public_ids(scrub(handoff(self.data, self.data['failures']))), encoding='utf-8')
        page = (Path(__file__).parent / 'dashboard.html').read_text(encoding='utf-8')
        # Also opens directly from disk, while HTTP viewers refresh results.json.
        payload = json.dumps(public, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
        (self.public / 'index.html.next').write_text(page.replace('__INITIAL_DATA__', payload), encoding='utf-8')
        (self.public / 'index.html.next').replace(self.public / 'index.html')

    def event(self, stage, message):
        self.data['events'].append({'at': now(), 'stage': stage, 'message': scrub(message)})
        self.data['events'] = self.data['events'][-200:]
        self.save()
        print(f'[{stage}] {message}', flush=True)

    def check(self, target, name, status, detail):
        stage = target.get('stage', 'service')
        job = (target.get('llm_jobs') or [{}])[-1] if stage == 'llm' else target.get('rescan_job' if stage == 'rescan' else 'scan_job', {})
        target.setdefault('checks', []).append({'name': name, 'status': status, 'detail': scrub(detail),
                                               'stage': stage, 'job_id': job.get('job_id')})
        self.save()

    def report(self, name, report):
        safe = public_ids(scrub(report))
        atomic_json(self.public / (name + '.json'), safe)
        text = html.escape(json.dumps(safe, ensure_ascii=False, indent=2))
        page = '<!doctype html><meta charset="utf-8"><title>실제 리포트 응답</title><style>body{max-width:1000px;margin:40px auto;font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>실제 서비스 리포트</h1><p>서버 JSON 응답을 비밀값 가림 후 표시합니다. 코드 원문은 포함하지 않습니다.</p><pre>' + text + '</pre>'
        (self.public / (name + '.html')).write_text(page, encoding='utf-8')
        return name + '.html'
