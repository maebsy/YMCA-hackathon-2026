"""스캐너 원본 JSON → 공통 형식 변환 (스캐너 설치 없이 돈다)."""
import copy
import json
from pathlib import Path

import pytest

from conftest import fake_stripe_key

from security_engine import fingerprint as fp
from security_engine.models import FLAG_ROTATE_SECRET, FLAG_SUPPRESSED_COMMENT
from security_engine.normalize import (
    mask_secret,
    pick_fix_version,
    rel_path,
    severity_from_cvss,
)
from security_engine.runners import gitleaks, osv, semgrep

# osv-scanner v2 실제 출력 모양 (offline DB로 lodash 4.17.15를 검사한 결과를 줄임)
OSV_OUTPUT = {
    "results": [{
        "source": {"path": "/abs/site/package-lock.json", "type": "lockfile"},
        "packages": [{
            "package": {"name": "lodash", "version": "4.17.15", "ecosystem": "npm"},
            "groups": [
                {"ids": ["GHSA-35jh-r3h4-6jhm"], "aliases": ["CVE-2021-23337", "GHSA-35jh-r3h4-6jhm"],
                 "max_severity": "7.2"},
                {"ids": ["GHSA-p6mc-m468-83gw"], "aliases": ["CVE-2020-8203", "GHSA-p6mc-m468-83gw"],
                 "max_severity": "7.4"},
            ],
            "vulnerabilities": [
                {"id": "GHSA-35jh-r3h4-6jhm", "aliases": ["CVE-2021-23337"], "summary": "Command Injection in lodash",
                 "affected": [{"package": {"ecosystem": "npm", "name": "lodash"},
                               "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}]}],
                 "database_specific": {"severity": "HIGH", "cwe_ids": ["CWE-77", "CWE-94"]},
                 "references": [{"type": "ADVISORY", "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-23337"}]},
                {"id": "GHSA-p6mc-m468-83gw", "aliases": ["CVE-2020-8203"], "summary": "Prototype Pollution in lodash",
                 "affected": [{"package": {"ecosystem": "npm", "name": "lodash"},
                               "ranges": [{"type": "SEMVER", "events": [{"introduced": "3.7.0"}, {"fixed": "4.17.19"}]}]}],
                 "database_specific": {"cwe_ids": ["CWE-1321"]}},
            ],
        }],
    }]
}


def test_osv_parse_groups_and_fix_versions():
    root = Path("/abs/site")
    fs = osv.parse(OSV_OUTPUT, root)
    assert len(fs) == 2
    by_id = {f["rule_id"]: f for f in fs}
    a = by_id["CVE-2021-23337"]  # 지문용 대표 ID는 CVE
    assert a["severity"] == "high"
    assert a["location"]["file"] == "package-lock.json"
    assert a["package"]["fixed_versions"] == ["4.17.21"]
    assert a["remediation"]["target_version"] == "4.17.21"
    assert "GHSA-35jh-r3h4-6jhm" in a["aliases"]
    b = by_id["CVE-2020-8203"]
    assert b["severity"] == "high"  # 라벨이 없으면 groups.max_severity(7.4)로
    assert a["fingerprint"] != b["fingerprint"]


def test_osv_fingerprint_ignores_version():
    """같은 취약점이면 버전을 조금 올렸어도(아직 취약) 같은 문제로 본다."""
    root = Path("/abs/site")
    before = osv.parse(OSV_OUTPUT, root)
    import copy
    bumped = copy.deepcopy(OSV_OUTPUT)
    bumped["results"][0]["packages"][0]["package"]["version"] = "4.17.16"
    after = osv.parse(bumped, root)
    assert {f["fingerprint"] for f in before} == {f["fingerprint"] for f in after}


def test_semgrep_parse_reads_code_and_detects_nosemgrep(tmp_path):
    (tmp_path / "a.js").write_text("x = 1;\nconst r = eval(q); // nosemgrep\n", encoding="utf-8")
    data = {"results": [{
        "check_id": "home.me.repo.security_engine.rules.js-eval-dynamic",
        "path": "a.js",
        "start": {"line": 2, "col": 11, "offset": 17}, "end": {"line": 2, "col": 18, "offset": 24},
        "extra": {"message": "eval()에 고정 문자열이 아닌 값을 넣고 있습니다. 더보기", "severity": "ERROR",
                  "metadata": {"engine_severity": "high", "cwe": "CWE-95"}, "lines": "requires login"},
    }], "errors": []}
    [f] = semgrep.parse(data, tmp_path)
    assert f["rule_id"] == "vibe-coding/js-eval-dynamic"
    assert f["severity"] == "high"
    assert f["cwe"] == ["CWE-95"]
    assert "eval(q)" in f["evidence"]["snippet"]  # 'requires login' 대신 파일에서 직접 읽음
    assert FLAG_SUPPRESSED_COMMENT in f["flags"]
    assert f["title"].startswith("eval()")


def test_semgrep_fingerprint_survives_line_shift(tmp_path):
    def run(code, line, off):
        # write_bytes: Windows에서 write_text는 \n을 \r\n으로 바꿔 offset이 달라짐
        (tmp_path / "b.js").write_bytes(code.encode("utf-8"))
        data = {"results": [{"check_id": "x.rules.js-eval-dynamic", "path": "b.js",
                             "start": {"line": line, "offset": off}, "end": {"line": line, "offset": off + 7},
                             "extra": {"message": "m", "severity": "ERROR", "metadata": {}}}]}
        return semgrep.parse(data, tmp_path)[0]["fingerprint"]

    first = run("eval(q)\n", 1, 0)
    code = "// new line\n\neval(q)\n"
    shifted = run(code, 3, code.index("eval"))
    assert first == shifted


def test_gitleaks_parse_masks_everything(tmp_path):
    secret = fake_stripe_key()
    (tmp_path / "c.js").write_text(f'const k = "{secret}";\n', encoding="utf-8")
    items = [{"RuleID": "stripe-access-token", "Description": "Stripe key", "File": "c.js",
              "StartLine": 1, "EndLine": 1, "Secret": secret, "Match": secret, "Entropy": 4.7}]
    fs, secrets = gitleaks.parse(items, tmp_path)
    [f] = fs
    assert secrets == [secret]
    assert secret not in repr(f)
    assert f["evidence"]["masked_secret"] == mask_secret(secret)
    assert f["severity"] == "critical"
    assert FLAG_ROTATE_SECRET in f["flags"]


def test_helpers():
    assert pick_fix_version("4.17.15", ["4.17.19", "4.17.21"]) == "4.17.19"
    assert pick_fix_version("4.17.20", ["4.17.19", "4.17.21"]) == "4.17.21"
    assert pick_fix_version("1.0.0", []) is None
    assert severity_from_cvss("9.8") == "critical"
    assert severity_from_cvss(None) is None
    assert rel_path("sub\\x.js".replace("\\", "/"), Path("/r")) == "sub/x.js"
    assert mask_secret("short") == "********"


def test_gitleaks_masks_multiline_private_key_with_crlf(tmp_path):
    """Windows(\r\n) 파일의 여러 줄 개인키도 본문까지 전부 가려야 한다 (NodeGoat 실검사에서 발견한 버그)."""
    import random
    import string

    rnd = random.Random(7)
    body = ["".join(rnd.choice(string.ascii_letters + string.digits + "+/") for _ in range(64)) for _ in range(3)]
    head, foot = "-----BEGIN RSA " + "PRIVATE KEY-----", "-----END RSA " + "PRIVATE KEY-----"
    key_crlf = "\r\n".join([head, *body, foot])
    (tmp_path / "server.key").write_bytes((key_crlf + "\r\n").encode())
    items = [{"RuleID": "private-key", "Description": "Private Key", "File": "server.key",
              "StartLine": 1, "EndLine": 5, "Secret": key_crlf, "Match": key_crlf}]
    fs, _ = gitleaks.parse(items, tmp_path)
    dumped = repr(fs)
    for line in body:
        assert line not in dumped
        assert line[:20] not in dumped


def _fake_pem(seed: int, newline: str) -> str:
    import random
    import string

    rnd = random.Random(seed)
    body = ["".join(rnd.choice(string.ascii_letters + string.digits + "+/") for _ in range(64)) for _ in range(3)]
    head, foot = "-----BEGIN RSA " + "PRIVATE KEY-----", "-----END RSA " + "PRIVATE KEY-----"
    return newline.join([head, *body, foot])


def _pem_fingerprint(tmp_path, key: str, name: str) -> str:
    (tmp_path / name).write_bytes((key + "\n").encode())
    items = [{"RuleID": "private-key", "Description": "Private Key", "File": name,
              "StartLine": 1, "EndLine": 5, "Secret": key, "Match": key}]
    [f] = gitleaks.parse(items, tmp_path)[0]
    assert key not in repr(f)
    return f["fingerprint"]


def test_gitleaks_fingerprint_ignores_line_endings(tmp_path):
    """같은 개인키는 Windows(\\r\\n)·Linux(\\n)·구형 Mac(\\r) 줄바꿈과 관계없이 같은 지문이어야 한다 (#58)."""
    lf = _pem_fingerprint(tmp_path, _fake_pem(7, "\n"), "k.key")
    assert _pem_fingerprint(tmp_path, _fake_pem(7, "\r\n"), "k.key") == lf
    assert _pem_fingerprint(tmp_path, _fake_pem(7, "\r"), "k.key") == lf


def test_gitleaks_fingerprint_still_tells_different_secrets_apart(tmp_path):
    """줄바꿈만 통일하므로 실제 값이 바뀌면 다른 지문이다. 기존 \\n 결과의 지문도 바뀌지 않는다 (#58)."""
    a = _pem_fingerprint(tmp_path, _fake_pem(7, "\r\n"), "k.key")
    b = _pem_fingerprint(tmp_path, _fake_pem(8, "\r\n"), "k.key")
    assert a != b
    key = _fake_pem(7, "\n")
    old = fp.make("gitleaks", "private-key", "k.key", fp.secret_hash(key))  # 이 변경 전 계산 방식
    assert _pem_fingerprint(tmp_path, key, "k.key") == old
    # 한 줄짜리 키 안의 공백 같은 내용은 그대로 구분한다
    one = _pem_fingerprint(tmp_path, "sk_live_" + "A" * 24, "c.txt")
    assert _pem_fingerprint(tmp_path, "sk_live_" + "A" * 23 + " ", "c.txt") != one


def test_gitleaks_public_key_is_downgraded_not_hidden(tmp_path):
    """검색 전용 키·reCAPTCHA siteKey는 원래 공개되는 키 → 숨기지 않고 low + likely_public_key (블로그 실검사에서 발견)."""
    key = "9d50" + "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    (tmp_path / "_config.yml").write_text(
        f"algolia:\n  search_only_api_key: {key}\n  admin_api_key: {key}\n", encoding="utf-8")
    items = [{"RuleID": "generic-api-key", "File": "_config.yml", "StartLine": n, "EndLine": n,
              "Secret": key, "Match": key} for n in (2, 3)]
    fs, _ = gitleaks.parse(items, tmp_path)
    public, admin = sorted(fs, key=lambda f: f["location"]["start_line"])
    assert public["severity"] == "low" and "likely_public_key" in public["flags"]
    assert "rotate_secret" not in public["flags"]
    assert admin["severity"] == "high" and "rotate_secret" in admin["flags"]   # 관리자 키는 그대로 위험


def test_semgrep_secret_rule_masks_literal(tmp_path):
    """PR #21 리뷰: Gitleaks가 못 잡은 하드코딩 JWT 키도 semgrep 결과에서 원문이 사라져야 한다."""
    key = "c0rp-signing-" + "Key-2026-xY"  # 저장소 비밀값 검사에 걸리지 않게 나눠 씀
    line = f'const t = jwt.sign({{ id: user.id }}, "{key}");\n'
    (tmp_path / "auth.js").write_text(line, encoding="utf-8")
    start, end = line.index("jwt"), line.index(");") + 1
    data = {"results": [{
        "check_id": "rules.jwt-hardcoded-secret", "path": "auth.js",
        "start": {"line": 1, "offset": start}, "end": {"line": 1, "offset": end},
        "extra": {"message": f"hardcoded {key}", "severity": "ERROR",
                  "metadata": {"cwe": "CWE-798: Use of Hard-coded Credentials"}},
    }]}
    secrets: list[str] = []
    out = semgrep.parse(data, tmp_path, secrets_out=secrets)
    assert secrets == [key]
    assert key not in json.dumps(out, ensure_ascii=False)
    assert FLAG_ROTATE_SECRET in out[0]["flags"]
    assert "c0rp********" in out[0]["evidence"]["snippet"]


def test_clone_only_accepts_github(monkeypatch):
    """PR #21 리뷰: 내부 주소(SSRF)·위장 호스트는 clone 전에 막는다."""
    import pytest

    from security_engine.git import _ALLOWED_URL, CloneError, clone_repo
    for ok in ("https://github.com/user/user.github.io", "https://github.com/o/r.git", "https://github.com/o/r/"):
        assert _ALLOWED_URL.match(ok), ok
    for bad in ("https://169.254.169.254/latest/meta-data", "https://localhost:8000/a/b",
                "https://github.com.evil.io/o/r", "http://github.com/o/r", "https://github.com/o/r/tree/main",
                "https://gitlab.com/o/r"):
        assert not _ALLOWED_URL.match(bad), bad
        with pytest.raises(CloneError):
            clone_repo(bad)


def test_clone_keeps_repository_line_endings(monkeypatch, tmp_path):
    """검사 서버의 core.autocrlf 설정이 줄바꿈을 바꾸지 못하게 clone 때 끈다 (#58)."""
    import subprocess

    import pytest

    from security_engine import git
    seen = []

    def fake_git(args, cwd=None, timeout=180):
        seen.append(args)
        return subprocess.CompletedProcess(args, 1, "", "stop here")

    monkeypatch.setattr(git, "_git", fake_git)
    with pytest.raises(git.CloneError):
        git.clone_repo("https://github.com/o/r", dest=tmp_path / "repo")
    args = seen[0]
    assert ["-c", "core.autocrlf=false"] == args[args.index("core.autocrlf=false") - 1:args.index("core.autocrlf=false") + 1]
    assert args.index("core.autocrlf=false") < args.index("clone")


# ── #92: 수정 버전 선택 (생태계별 비교, 비교 불가면 추천 보류) ──
def test_pick_fix_version_never_suggests_a_downgrade():
    from security_engine.normalize import pick_fix_version as pick

    assert pick("2.0.0", ["1.9.0"], "npm") is None  # 이슈 재현: 예전에는 1.9.0
    assert pick("2.0.0", ["1.9.0", "2.0.0"], "npm") is None  # 같은 버전도 '올리기'가 아님
    assert pick("2.0.0", ["1.9.0", "2.0.1"], "npm") == "2.0.1"
    assert pick(None, ["1.2.0", "1.10.0"], "npm") == "1.10.0"  # 현재 버전을 모르면 가장 높은 후보


def test_pick_fix_version_handles_semver_prereleases():
    from security_engine.normalize import pick_fix_version as pick

    assert pick("1.2.3-beta.1", ["1.2.3", "1.2.4"], "npm") == "1.2.3"  # 이슈 재현: 예전에는 1.2.4
    assert pick("1.2.3", ["1.2.3-rc.1", "1.2.4"], "npm") == "1.2.4"  # 사전 출시는 정식보다 낮음
    assert pick("1.0.0-alpha", ["1.0.0-alpha.1", "1.0.0"], "npm") == "1.0.0-alpha.1"
    assert pick("v1.4.0", ["v1.4.1"], "Go") == "v1.4.1"  # Go 모듈의 v 접두어


def test_semver_post_suffix_and_alphanumeric_ids_are_not_upgrades():
    """#101 리뷰 재현: SemVer에서 하이픈 꼬리표는 모두 사전 출시이고, 영숫자 식별자는 ASCII 순서로 비교한다."""
    from security_engine.normalize import pick_fix_version as pick

    assert pick("1.0.0", ["1.0.0-post1"], "npm") is None  # 1.0.0-post1 < 1.0.0 (SemVer §9)
    assert pick("1.0.0-alpha2", ["1.0.0-alpha10"], "npm") is None  # 'alpha10' < 'alpha2' (SemVer §11)
    assert pick("1.0.0-alpha10", ["1.0.0-alpha2"], "npm") == "1.0.0-alpha2"
    assert pick("1.0.0-Beta", ["1.0.0-alpha"], "npm") == "1.0.0-alpha"  # 대소문자 구분: 'B'(66) < 'a'(97)


def test_unparseable_versions_are_never_recommended():
    from security_engine.normalize import pick_fix_version as pick

    assert pick("1!1.0", ["2.0"], "PyPI") is None  # epoch 1이 더 높음: 2.0은 다운그레이드
    assert pick("1!1.0", ["1!1.1"], "PyPI") == "1!1.1"
    assert pick("not-a-version", ["1.2.3"], "npm") is None  # 현재 버전을 못 읽으면 보류
    assert pick("1.2.3", ["a1b2c3d4e5f6", "1.2.4"], "npm") == "1.2.4"  # 커밋 해시 후보는 빼고 고름
    assert pick("1.2.3", ["a1b2c3d4e5f6"], "npm") is None
    assert pick("2.0", ["2.1-weird"], "Maven") is None  # 모르는 Maven 한정자는 비교하지 않음
    assert pick("1.0.0", ["1.0.1.pre"], "RubyGems") is None  # 규칙을 모르는 꼬리표는 추측하지 않음
    assert pick("1.0.0", ["1.0.1"], "RubyGems") == "1.0.1"  # 숫자만이면 비교 가능


def _key(ecosystem):
    """정렬용 키. 비교 불가(None)면 테스트가 바로 실패하게 해 Optional을 좁힌다."""
    from security_engine.normalize import version_key

    def key(v: str) -> tuple:
        k = version_key(v, ecosystem)
        assert k is not None, (v, ecosystem)
        return k
    return key


def test_version_key_follows_semver_precedence():
    from security_engine.normalize import version_key

    # SemVer 2.0.0 명세 11번의 예시 순서
    chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
             "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
    assert sorted(reversed(chain), key=_key("npm")) == chain
    assert version_key("1.0.0+build.5", "npm") == version_key("1.0.0", "npm")  # 빌드 정보는 순서에 영향 없음
    assert version_key("1.2", "npm") is None  # SemVer는 세 자리가 필요
    assert _key(None)("1.2") == _key(None)("1.2.0") < _key(None)("1.10")


def test_version_key_follows_pep440_and_maven():
    from security_engine.normalize import version_key

    pypi = ["1.0.dev0", "1.0a1", "1.0b2", "1.0rc1", "1.0", "1.0.post1", "1.0.1", "1!0.1"]
    assert sorted(reversed(pypi), key=_key("PyPI")) == pypi
    maven = ["2.0-alpha1", "2.0-beta-2", "2.0-RC1", "2.0-SNAPSHOT", "2.0", "2.0-sp1", "2.0.1"]
    assert sorted(reversed(maven), key=_key("Maven")) == maven


def _osv_reintroduced(version: str, fixed: str, eco: str = "npm") -> dict:
    """과거에 고쳐졌다가 현재 버전에서 다시 생긴 취약점 (introduced 0 → fixed → introduced 현재)."""
    out = copy.deepcopy(OSV_OUTPUT)
    pkg = out["results"][0]["packages"][0]
    pkg["package"].update(version=version, ecosystem=eco)
    pkg["groups"] = pkg["groups"][:1]
    vuln = pkg["vulnerabilities"][0]
    vuln["affected"][0]["package"]["ecosystem"] = eco
    vuln["affected"][0]["ranges"] = [{"type": "SEMVER", "events": [
        {"introduced": "0"}, {"fixed": fixed}, {"introduced": version}]}]
    pkg["vulnerabilities"] = [vuln]
    return out


@pytest.mark.parametrize(("version", "fixed"), [("1.0.0", "1.0.0-post1"), ("1.0.0-alpha2", "1.0.0-alpha10")])
def test_osv_parse_does_not_turn_lower_fixed_into_upgrade(version, fixed):
    [f] = osv.parse(_osv_reintroduced(version, fixed), Path("/abs/site"))

    assert f["package"]["fixed_versions"] == [fixed]  # 원본 정보는 그대로 남김
    assert f["remediation"] == {"kind": "no_fix_available", "target_version": None, "autofix": None}


def test_dependency_plan_ignores_targets_it_cannot_compare():
    from security_engine.engine import _dependency_upgrades

    def dep(fp, target):
        return {"tool": "osv", "status": "code_issue", "fingerprint": fp, "severity": "high",
                "package": {"ecosystem": "npm", "name": "lib", "version": "1.0.0"},
                "location": {"file": "package-lock.json"},
                "remediation": {"target_version": target}}

    [plan] = _dependency_upgrades([dep("a", "1.0.1"), dep("b", "1.0.0-rc.9"), dep("c", "not-semver")])
    assert plan["target_version"] == "1.0.1"  # 1.0.0-rc.9는 더 낮고, not-semver는 비교하지 않음
    assert plan["fixes"] == ["a", "b"] and plan["unfixable"] == ["c"]


def test_maven_short_qualifiers_require_an_adjacent_digit():
    from security_engine.normalize import version_key

    for short, full in (("a", "alpha"), ("b", "beta"), ("m", "milestone")):
        for alias in (short, short.upper()):
            for prefix in ("1.0-", "1.0.", "1.0"):
                assert version_key(prefix + alias + "1", "Maven") == version_key(prefix + full + "1", "Maven")
                for suffix in ("", "-1", ".1"):
                    version = prefix + alias + suffix
                    assert version_key(version, "Maven") is None
                    assert pick_fix_version(version, ["1.0"], "Maven") is None
                    assert pick_fix_version("1.0", [version], "Maven") is None
                    assert pick_fix_version(None, [version], "Maven") is None
            assert pick_fix_version("1.0-" + alias + "1", ["1.0"], "Maven") == "1.0"
        assert version_key("1.0-" + full + "-1", "Maven") == version_key("1.0-" + full + "1", "Maven")


def test_osv_parse_does_not_downgrade_unknown_maven_short_qualifiers():
    for qualifier in ("a", "b", "m", "A", "B", "M"):
        for suffix in ("", "-1", ".1"):
            [finding] = osv.parse(_osv_reintroduced("1.0-" + qualifier + suffix, "1.0", "Maven"), Path("/abs/site"))
            assert finding["package"]["fixed_versions"] == ["1.0"]
            assert finding["remediation"] == {"kind": "no_fix_available", "target_version": None, "autofix": None}


def test_osv_parse_keeps_upgrades_for_numbered_maven_short_qualifiers():
    for qualifier in ("a", "b", "m"):
        [finding] = osv.parse(_osv_reintroduced("1.0-" + qualifier + "1", "1.0", "Maven"), Path("/abs/site"))
        assert finding["remediation"]["kind"] == "upgrade_dependency"
        assert finding["remediation"]["target_version"] == "1.0"


# ── #101 재리뷰: Maven 정식 별칭 뒤 숫자·점 구분은 (순위, 정수)로 비교할 수 없어 보류 ──
MAVEN_UNSAFE = [("1.0-final1", "1.0-sp1"), ("1.0-ga1", "1.0-sp1"), ("1.0-release1", "1.0-sp1"),
                ("1.0-alpha.1", "1.0-alpha2"), ("1.0.alpha-1", "1.0-alpha2")]


@pytest.mark.parametrize(("current", "fixed"), MAVEN_UNSAFE)
def test_maven_forms_we_cannot_order_are_not_recommended(current, fixed):
    from security_engine.normalize import version_key

    # Apache Maven ComparableVersion 기준으로는 모두 current > fixed (낮은 후보)
    assert version_key(current, "Maven") is None
    assert pick_fix_version(current, [fixed], "Maven") is None
    assert pick_fix_version(fixed, [current], "Maven") is None  # 역방향도 추측하지 않음


@pytest.mark.parametrize(("current", "fixed"), MAVEN_UNSAFE)
def test_osv_parse_and_package_plan_do_not_downgrade_maven(current, fixed):
    from security_engine.engine import _dependency_upgrades

    [f] = osv.parse(_osv_reintroduced(current, fixed, "Maven"), Path("/abs/site"))
    assert f["remediation"]["kind"] == "no_fix_available" and f["remediation"]["target_version"] is None
    f["status"] = "code_issue"
    [plan] = _dependency_upgrades([f])
    assert plan["target_version"] is None


def test_maven_supported_forms_still_compare():
    from security_engine.normalize import pick_fix_version as pick

    assert pick("1.0-alpha2", ["1.0-alpha10"], "Maven") == "1.0-alpha10"  # 숫자가 바로 붙으면 정수 비교
    assert pick("1.0-rc1", ["1.0", "1.0-sp1"], "Maven") == "1.0"
    assert pick("1.0-final", ["1.0-sp1"], "Maven") == "1.0-sp1"  # 숫자 없는 정식 별칭은 정식과 같음


@pytest.mark.parametrize("qualifier", ["alpha", "beta", "milestone", "rc", "cr", "sp"])
def test_maven_dot_qualifier_with_hyphen_number_is_not_comparable(qualifier):
    from security_engine.normalize import version_key

    unsupported = f"1.0.1.{qualifier}-2"
    supported = f"1.0.1-{qualifier}1"
    assert version_key(unsupported, "Maven") is None
    assert pick_fix_version(supported, [unsupported], "Maven") is None
    assert pick_fix_version(unsupported, [supported], "Maven") is None
    assert pick_fix_version(None, [unsupported], "Maven") is None
    # 숫자가 바로 붙는 점 한정자와 하이픈 한정자는 기존 Maven 비교를 유지한다.
    key = _key("Maven")
    assert key(f"1.0.1.{qualifier}1") == key(supported) == key(f"1.0.1-{qualifier}-1")


def test_upgrade_hint_tells_lower_fix_apart_from_uncomparable():
    from security_engine.llm_input import _fix_hint

    def hint(version, fixed, eco):
        f = {"tool": "osv", "package": {"name": "lib", "ecosystem": eco, "version": version, "fixed_versions": fixed},
             "location": {"file": "package-lock.json"},
             "remediation": {"kind": "no_fix_available", "target_version": None}}
        return _fix_hint(f)["text"]

    assert "다시 생긴" in hint("2.0.0", ["1.9.0"], "npm")  # 모두 비교됐고 전부 낮음
    assert "비교하지 못해" in hint("1.0-final1", ["1.0-sp1"], "Maven")  # 비교 불가
    assert "아직 고친 버전이 없음" in hint("1.0.0", [], "npm")  # 후보 자체가 없음
