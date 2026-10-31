"""수정 버전·위협 정보의 독립 계약 사례와 외부 원본의 제한된 최신성 메타데이터."""
import asyncio
from datetime import datetime, timezone
import json
import urllib.error
import urllib.request


def check_data_contracts(check, pick_version, intel_factory, transport_factory, response_factory):
    for name, current, fixed, expected in (
        ('수정 버전 다운그레이드 금지', '2.0.0', ['1.9.0'], None),
        ('사전 출시 최소 수정 버전', '1.2.3-beta.1', ['1.2.3', '1.2.4'], '1.2.3'),
    ):
        selected = pick_version(current, fixed)
        check(name, {'selected': expected}, {'current': current, 'fixed': fixed, 'selected': selected},
              selected == expected, 'security_engine/normalize.py: 현재보다 높은 최소 수정 버전; SemVer 2.0 §11', 'remediation')

    async def failed_lookup():
        # Inject HTTP failure only into a new independent client, never the service network.
        client = intel_factory(transport=transport_factory(lambda request: response_factory(503)))
        try:
            result = await client.lookup(['CVE-2021-23337'])
            record = result.get('CVE-2021-23337')
            return record.model_dump() if record is not None else None
        finally:
            await client.aclose()
    record = asyncio.run(failed_lookup())
    unknown = record is None or record.get('kev') is None
    check('KEV 조회 실패와 정상 부재 구분', '최초 HTTP 503이면 KEV unknown/null 또는 레코드 미제공',
          {'synthetic_http_status': 503, 'record': record}, unknown,
          'backend/app/llm/intel.py: 받지 못한 정보는 모름. 실제 서버 장애를 뜻하지 않음', 'threat_intel')


def source_metadata(name, data):
    if not isinstance(data, dict):
        raise ValueError('source metadata must be an object')
    if name == 'OSV 표본':
        result = {'id': data.get('id'), 'modified': data.get('modified'), 'published': data.get('published')}
        required = ('id', 'modified')
    elif name == 'CISA KEV':
        result = {'version': data.get('catalogVersion'), 'released': data.get('dateReleased'), 'count': data.get('count')}
        required = ('version', 'released')
    elif name == 'FIRST EPSS 표본':
        rows = data.get('data')
        if (not isinstance(rows, list) or not rows
                or not all(isinstance(row, dict) and isinstance(row.get('date'), str) and row['date'] for row in rows)):
            raise ValueError('source date is unavailable')
        return {'dates': sorted({row['date'] for row in rows})}
    else:
        result = {'version': data.get('tag_name'), 'released': data.get('published_at')}
        required = ('version', 'released')
    if not all(isinstance(result[k], str) and result[k] for k in required):
        raise ValueError('required source metadata is missing')
    return result


def collect_freshness():
    sources = [('OSV 표본', 'https://api.osv.dev/v1/vulns/GHSA-35jh-r3h4-6jhm'),
               ('CISA KEV', 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'),
               ('FIRST EPSS 표본', 'https://api.first.org/data/v1/epss?cve=CVE-2021-23337')]
    sources += [(repo, 'https://api.github.com/repos/'+repo+'/releases/latest') for repo in
                ('google/osv-scanner', 'opengrep/opengrep', 'gitleaks/gitleaks')]
    rows = []
    for name, url in sources:
        row = {'name': name, 'url': url, 'queried_at': datetime.now(timezone.utc).isoformat()}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': '72hours-validation/1'})
            with urllib.request.urlopen(request, timeout=6) as response:
                row['http_status'] = response.status
                body = response.read(8*1024*1024+1)
                if len(body) > 8*1024*1024:
                    raise ValueError('response limit')
                row.update(status='received', metadata=source_metadata(name, json.loads(body)))
        except urllib.error.HTTPError as exc:
            row.update(status='unavailable', http_status=exc.code, error_type='HTTPError')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row.update(status='unavailable', error_type=type(exc).__name__)
        rows.append(row)
    return rows
