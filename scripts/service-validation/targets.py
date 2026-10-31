"""검증 대상 저장소 범위. 서비스의 검사 허용 목록(#69, SCAN_ALLOWED_OWNERS)과 같은 소유자만 씁니다.

남의 공개 저장소를 검사해 결과를 공개 화면에 올리면 #69가 막으려는 '남의 취약점 목록 수집'과 같은 모양이 됩니다.
그래서 교육용 취약 앱(OWASP)과 팀원 저장소만 대상으로 하고, 목록 밖은 실행 전에 거절합니다.
운영 서버의 허용 목록이 다르면 SERVICE_VALIDATION_ALLOWED_OWNERS 로 같은 값을 주세요.
"""
import os

from client import repo_url

# deploy/general-server/backend.env.example 의 SCAN_ALLOWED_OWNERS 와 같은 값
DEFAULT_OWNERS = 'OWASP,maebsy,surilog,SeouliteParker,papawolf42,nick19850906-debug'


def allowed_owners():
    raw = os.environ.get('SERVICE_VALIDATION_ALLOWED_OWNERS', DEFAULT_OWNERS)
    return {o.strip().lower() for o in raw.split(',') if o.strip()}


def owner_of(url):
    return repo_url(url).removeprefix('https://github.com/').split('/', 1)[0].lower()


def allowed_repo(url):
    """허용 소유자의 저장소면 정규화한 주소를, 아니면 ValueError."""
    url = repo_url(url)
    if owner_of(url) not in allowed_owners():
        raise ValueError(f'검증 대상은 허용 소유자(OWASP·팀원) 저장소만 씁니다: {url}')
    return url
