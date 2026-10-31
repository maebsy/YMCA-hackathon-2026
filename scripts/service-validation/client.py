"""공개 서비스 호출. 접수 POST는 재시도하지 않고 receipt를 기록합니다."""
import json
import os
import re
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request


class CheckError(RuntimeError):
    pass


class PolicyRejected(CheckError):
    """서비스가 정책(검사 대상 허용 목록 등)으로 거절함. 서비스 장애가 아니므로 실패로 세지 않습니다."""


def origin(value):
    url = urlsplit(value)
    if (not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')
            or not (url.scheme == 'https' or (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')))):
        raise ValueError('HTTPS 서비스 원점 또는 로컬 http://127.0.0.1:PORT만 지정하세요.')
    return value.rstrip('/')


def repo_url(value):
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?', value):
        raise ValueError('공개 GitHub owner/repo URL이 필요합니다.')
    parts = value.rstrip('/').split('/')[-2:]
    if any(x in ('.', '..') for x in parts):
        raise ValueError('올바르지 않은 저장소 주소입니다.')
    return value.rstrip('/').removesuffix('.git')


def _error_code(exc):
    """오류 응답 본문의 detail.code만 읽습니다 (본문 자체는 기록하지 않음)."""
    try:
        detail = json.loads(exc.read(64 * 1024).decode('utf-8')).get('detail')
        return detail.get('code') if isinstance(detail, dict) else None
    except (OSError, ValueError, AttributeError):
        return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base, evidence, timeout=30, poll=5, deadline=None):
        self.base, self.evidence = origin(base), evidence
        self.timeout, self.interval = timeout, poll
        self.deadline = deadline or time.monotonic() + 3600
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None, headers=None, raw=False, cleanup=False):
        """cleanup=True 는 정리(연결 폐기 등) 요청: 전체 시간 상한이 지나도 짧은 제한으로 한 번은 보냅니다."""
        if not path.startswith('/') or path.startswith('//'):
            raise CheckError('API 경로가 올바르지 않습니다.')
        if time.monotonic() >= self.deadline and not cleanup:
            raise CheckError('실행 전체 시간 상한을 초과했습니다.')
        request_headers = {'Accept': 'application/json', 'User-Agent': '72hours-service-validation/1'}
        if body is not None:
            request_headers['Content-Type'] = 'application/json'
        token = os.environ.get('SERVICE_VALIDATION_API_TOKEN')
        if token and path.startswith('/api/'):
            request_headers['Authorization'] = 'Bearer ' + token
        request_headers.update(headers or {})
        request = urllib.request.Request(self.base + path, method=method, headers=request_headers,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
        try:
            wait = 10 if cleanup else min(self.timeout, max(1, self.deadline-time.monotonic()))
            with self.opener.open(request, timeout=wait) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise CheckError('응답이 8 MiB 한도를 초과했습니다.')
                text = body.decode('utf-8')
                return (text, response.headers.get('Content-Type', '')) if raw else json.loads(text)
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and _error_code(exc) == 'SCAN_TARGET_NOT_ALLOWED':
                raise PolicyRejected('HTTP 403 SCAN_TARGET_NOT_ALLOWED: 서비스의 검사 대상 허용 목록 밖입니다. '
                                     '서비스 장애가 아니며 우회하지 않습니다.') from None
            if exc.code in (401, 403):
                raise CheckError(f'HTTP {exc.code}: 인증 또는 검사 대상 정책이 거부했습니다. 우회하지 않습니다.') from None
            raise CheckError(f'HTTP {exc.code}: 요청 실패. 접수 요청은 자동 재시도하지 않습니다.') from None
        except (OSError, ValueError) as exc:
            raise CheckError(f'{type(exc).__name__}: 응답 확인 실패. 접수 여부가 불명확할 수 있습니다.') from None

    def job(self, key, path, payload, timeout, target):
        jobs = self.evidence.state['jobs']
        if key not in jobs:
            jobs[key] = {'state': 'dispatching'}
            self.evidence.save()
            # If interrupted here, resume deliberately refuses a duplicate submission.
            try:
                result = self.request('POST', path, payload)
            except PolicyRejected:
                del jobs[key]  # 정책 거절은 접수되지 않은 것이 확실하므로 '불명확' 상태로 남기지 않습니다
                self.evidence.save()
                raise
            job_id = result.get('job_id', '')
            if not re.fullmatch(r'[a-f0-9]{32}', job_id):
                raise CheckError('접수 응답에 유효한 job_id가 없습니다.')
            jobs[key] = {'state': 'queued', 'job_id': job_id}
            self.evidence.save()
        receipt = jobs[key]
        if not receipt.get('job_id'):
            raise CheckError('이전 접수 여부가 불명확합니다. 운영자가 확인하기 전 자동 재접수하지 않습니다.')
        target['job_id'] = receipt['job_id']
        started, limit = time.monotonic(), min(self.deadline, time.monotonic() + timeout)
        previous = None
        while time.monotonic() < limit:
            result = self.request('GET', path + '/' + receipt['job_id'])
            status = result.get('status')
            if status not in ('queued', 'running', 'done', 'failed'):
                raise CheckError('알 수 없는 작업 상태입니다.')
            receipt['state'] = status
            target.update(status=status, observed_seconds=round(time.monotonic()-started, 1))
            if status != previous:
                self.evidence.event(key, status)
                previous = status
            else:
                self.evidence.save()
            if status == 'done':
                if not isinstance(result.get('result'), dict):
                    raise CheckError('완료 응답에 결과가 없습니다.')
                return result['result']
            if status == 'failed':
                code = (result.get('error') or {}).get('code', 'JOB_FAILED')
                target['error_code'] = str(code)[:80]
                raise CheckError('서버 작업 실패: ' + str(code)[:80])
            time.sleep(min(self.interval, max(0, limit-time.monotonic())))
        target['status'] = 'timeout'
        raise CheckError('완료 대기 시간 초과. 서버 작업은 계속될 수 있으며 --resume으로 같은 ID를 조회하세요.')

    def rpc(self, endpoint, method, params):
        result = self.request('POST', endpoint, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params},
                              headers={'Accept': 'application/json, text/event-stream'})
        if 'error' in result or 'result' not in result or result['result'].get('isError'):
            raise CheckError('MCP 프로토콜 또는 도구 호출 실패')
        return result['result']
