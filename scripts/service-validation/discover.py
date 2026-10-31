"""GitHub 공개 웹 소스 후보 수집. 대상 앱을 실행하거나 배포 사이트를 공격하지 않습니다."""
import json
import os
from urllib.parse import urlencode
import urllib.request

from client import NoRedirect, repo_url, CheckError
from targets import allowed_owners


def github(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': '72hours-validation/1'}
    token = os.environ.get('SERVICE_VALIDATION_GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('https://api.github.com' + path, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise CheckError('GitHub 메타데이터가 너무 큽니다.')
            return json.loads(raw)
    except OSError as exc:
        raise CheckError(f'GitHub 후보 조회 실패: HTTP {getattr(exc, "code", "network")}. 검색 제한 시 저장소 목록 파일을 쓰세요.') from None


def discover(query, count):
    if not 1 <= count <= 10:
        raise ValueError('자동 수집은 한 번에 1~10개입니다.')
    owners = allowed_owners()
    # 검색어에 무엇을 넣어도 허용 소유자(OWASP·팀원) 저장소만 후보가 됩니다 (#69)
    scope = ' '.join('user:' + o for o in sorted(owners))
    query = f'{query} {scope} is:public fork:false archived:false size:<10000'
    result = github('/search/repositories?' + urlencode({'q': query, 'sort': 'stars', 'per_page': min(30, count*3)}))
    selected = []
    for item in result.get('items', []):
        if item.get('private') or item.get('archived') or item.get('size', 0) >= 10000:
            continue
        if (item.get('owner') or {}).get('login', '').lower() not in owners:
            continue
        files = github('/repos/' + item['full_name'] + '/contents')
        names = {f.get('name', '').lower() for f in files if f.get('type') in ('file', 'dir')}
        web = item.get('has_pages') or 'index.html' in names or 'src' in names and 'package.json' in names
        if not web:
            continue
        selected.append({'url': repo_url(item['html_url']), 'reason': 'GitHub 공개 웹 소스 메타데이터 확인',
                         'web_markers': sorted(names & {'index.html', 'src', 'package.json'}),
                         'has_pages': item.get('has_pages', False), 'license': (item.get('license') or {}).get('spdx_id')})
        if len(selected) >= count:
            break
    if not selected:
        raise CheckError('검색 결과에서 공개 웹 소스 후보를 찾지 못했습니다.')
    return selected
