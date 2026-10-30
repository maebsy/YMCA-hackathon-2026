"""스캐너 원본 JSON → 공통 형식 변환 (스캐너 설치 없이 돈다)."""
import json
from pathlib import Path

from conftest import fake_stripe_key

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
