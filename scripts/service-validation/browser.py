"""독립 브라우저에서 실제 입력·클릭·네트워크 응답을 확인합니다. API mock을 사용하지 않습니다."""
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from client import CheckError


def browser_check(client, evidence, repository, timeout):
    from playwright.sync_api import sync_playwright, Error as BrowserError
    # run.ps1 installs into a workspace-local browser cache, not a user's browser profile.
    cache = Path.cwd() / 'outputs/validation-runtime/browsers'
    if cache.exists() and 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(cache.resolve())
    data = {'repository': repository, 'checks': [], 'screenshots': []}
    evidence.data['browser'] = data
    captured, errors = {}, []
    limit = min(client.deadline, time.monotonic() + timeout)
    def remaining():
        return max(1000, int((limit-time.monotonic())*1000))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='ko-KR')
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(type(error).__name__))
        def observe(response):
            path = urlsplit(response.url).path
            if not response.url.startswith(client.base + '/api/'):
                return
            try:
                if path.startswith('/api/scans/') and response.request.method == 'GET' and response.ok:
                    job = response.json()
                    if job.get('status') == 'done':
                        captured['scan'] = job['result']
                elif path == '/api/reports/plain' and response.ok:
                    captured['report_input'] = response.request.post_data_json
                    captured['report_text'] = response.text()
            except Exception:
                errors.append('ResponseObservationError')
        page.on('response', observe)
        try:
            evidence.event('browser', '새 브라우저에서 저장소 주소 입력 및 실제 검사 버튼 클릭')
            page.goto(client.base, wait_until='domcontentloaded', timeout=30000)
            field = page.get_by_placeholder('https://github.com/owner/repo', exact=True)
            field.fill(repository, timeout=15000)
            page.screenshot(path=str(evidence.public/'browser-input.png'))
            data['screenshots'].append('browser-input.png')
            with page.expect_response(lambda r: urlsplit(r.url).path == '/api/scans' and r.request.method == 'POST', timeout=30000) as submit:
                page.get_by_role('button', name=re.compile('검사 시작')).click()
            evidence.check(data, '브라우저 실제 검사 POST', 'pass' if submit.value.status == 202 else 'fail',
                           {'http_status': submit.value.status, 'repository': repository})
            while 'scan' not in captured and time.monotonic() < limit:
                page.wait_for_timeout(1000)
            if 'scan' not in captured:
                raise CheckError('브라우저가 실제 검사 완료 응답을 받지 못했습니다.')
            scan = captured['scan']
            evidence.check(data, '브라우저 검사 대상·커밋', 'pass' if scan['result']['target']['repo_url'].rstrip('/') == repository else 'fail',
                           {'scan_id': scan['scan_id'], 'revision': scan['result']['target']['commit_sha']})
            # The UI re-enables this button after its own automatic LLM sequence finishes.
            page.get_by_role('button', name=re.compile('검사 시작')).wait_for(state='visible', timeout=remaining())
            from playwright.sync_api import expect
            expect(page.get_by_role('button', name=re.compile('검사 시작'))).to_be_enabled(timeout=remaining())
            page.get_by_role('button', name=re.compile('완료 리포트|리포트')).first.click(timeout=15000)
            with page.expect_response(lambda r: urlsplit(r.url).path == '/api/reports/plain', timeout=30000):
                page.get_by_role('button', name='리포트 만들기', exact=True).click(timeout=15000)
            frame = page.frame_locator('iframe[title="실제 검사 리포트"]')
            expect(frame.locator('body')).to_contain_text(scan['report_scan']['site_name'], timeout=15000)
            payload = captured.get('report_input', {})
            evidence.check(data, '실제 결과로 리포트 버튼 실행', 'pass' if payload.get('scan') == scan['report_scan']
                           and payload.get('findings') == scan['findings'] else 'fail',
                           {'report_finding_groups': len(payload.get('findings', [])),
                            'report_analysis_groups': len(payload.get('explain_results', [])), 'mocked': False})
            data['analysis_groups'] = len(payload.get('explain_results', []))
            from checks import report_checks
            report = client.request('POST', '/api/reports/plain?format=json', payload)
            report_checks(evidence, data, scan, payload.get('explain_results', []), report)
            page.locator('iframe[title="실제 검사 리포트"]').screenshot(path=str(evidence.public/'browser-report.png'))
            data['screenshots'].append('browser-report.png')
            evidence.check(data, '실제 리포트 화면 표시', 'pass', '실제 API HTML 응답이 sandbox iframe에 표시되는 것을 확인했습니다.')
            evidence.check(data, '브라우저 JavaScript 오류', 'fail' if errors else 'pass', {'error_types': errors})
        except (BrowserError, CheckError, AssertionError, KeyError, TypeError, ValueError) as exc:
            evidence.check(data, '브라우저 사용자 흐름', 'fail', str(exc) if isinstance(exc, CheckError) else 'UI 검증 실패: 화면 선택자·응답 계약·서비스 상태를 확인하세요.')
            page.screenshot(path=str(evidence.public/'browser-failure.png'))
            data['screenshots'].append('browser-failure.png')
        finally:
            context.close()
            browser.close()
            evidence.save()
