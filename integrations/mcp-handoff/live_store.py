"""Minimal browser exports, isolated by expiring read/revoke capabilities."""
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import time

from handoff import HandoffError, Snapshot, redact

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
MAX_BODY = 160 * 1024


def digest(token):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise LookupError("연결이 없거나 만료·폐기되었습니다.")
    return hashlib.sha256(token.encode()).hexdigest()


def normalize(document):
    """Never accept source code, raw errors or arbitrary client provenance as storage fields."""
    if not isinstance(document, dict) or not isinstance(document.get("scan"), dict):
        raise HandoffError("실제 웹 검사 결과가 필요합니다.")
    scan = document["scan"]
    repository, revision = scan.get("repository"), scan.get("revision")
    if not isinstance(repository, str) or not isinstance(revision, str):
        raise HandoffError("검사 저장소와 커밋을 확인할 수 없습니다.")
    scan_id = scan.get("scan_id")
    if not isinstance(scan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", scan_id):
        raise HandoffError("실제 scan ID가 필요합니다.")
    scanned_at = scan.get("scanned_at")
    try:
        date = datetime.fromisoformat(scanned_at.replace("Z", "+00:00"))
        if date.tzinfo is None or date.timestamp() > time.time() + 300:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HandoffError("검사 시각이 올바르지 않습니다.") from None
    fingerprints = scan.get("fingerprints")
    if (not isinstance(fingerprints, list) or not 1 <= len(fingerprints) <= 5000
            or any(not isinstance(fp, str) or not 1 <= len(fp) <= 200 for fp in fingerprints)):
        raise HandoffError("검사 항목 식별자가 필요합니다.")
    known = set(fingerprints)
    results = document.get("results")
    if not isinstance(results, list) or not 1 <= len(results) <= 50:
        raise HandoffError("LLM 결과가 없습니다. 웹에서 해석이 끝난 뒤 연결해 주세요.")
    minimal = []
    for result in results:
        if not isinstance(result, dict):
            raise HandoffError("잘못된 해석 결과입니다.")
        fp, covers = result.get("fingerprint"), result.get("covers", [])
        if (not isinstance(fp, str) or not isinstance(covers, list)
                or any(not isinstance(item, str) or item not in known for item in covers)
                or (fp not in known and not (fp.startswith("pkg:") and covers))):
            raise HandoffError("해석 결과가 선택한 검사 항목과 일치하지 않습니다.")
        entry = {"fingerprint": fp, "status": result.get("status")}
        explanation = result.get("explanation")
        if isinstance(explanation, dict):
            fields = ("fingerprint", "variant", "red_verdict", "needs_manual_review", "false_positive_suspect",
                      "ai_fix_prompt", "model", "prompt_version")
            entry["explanation"] = {key: redact(explanation[key]) if isinstance(explanation.get(key), str)
                                     else explanation.get(key) for key in fields}
            rounds = explanation.get("red_rounds")
            if isinstance(rounds, list) and rounds and isinstance(rounds[-1], dict):
                last = rounds[-1]
                entry["explanation"]["red_rounds"] = [{"verdict": last.get("verdict"),
                    "issues": [] if last.get("issues") == [] else ["review_required"]}]
        minimal.append(entry)
    # Reuse the exact stdio delivery gates. The temporary file contains only redacted allowlisted fields.
    with tempfile.TemporaryDirectory(prefix="72hours-handoff-") as directory:
        path = Path(directory) / "snapshot.json"
        path.write_text(json.dumps({"mode": "red_blue", "results": minimal}), encoding="utf-8")
        snapshot = Snapshot(path, repository, revision)
    if not any(entry["ready"] for entry in snapshot.entries.values()):
        raise HandoffError("전달 가능한 Red 통과 결과가 없습니다. 해석 완료 또는 수동 확인이 필요합니다.")
    snapshot.provenance.update(scan_id=scan_id, scanned_at=date.isoformat(),
        binding="browser_export_not_server_verified", delivery="user_selected_web_scan")
    return snapshot


class LinkStore:
    def __init__(self, path, ttl=86400, limit=256, clock=time.time):
        self.path, self.ttl, self.limit, self.clock = Path(path), ttl, limit, clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS handoff (read_hash TEXT PRIMARY KEY, revoke_hash TEXT NOT NULL, expires REAL NOT NULL, snapshot TEXT NOT NULL)")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA secure_delete=ON")
            with db:
                yield db
        finally:
            db.close()

    def create(self, snapshot):
        read, revoke = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = self.clock() + self.ttl
        snapshot.provenance["expires_at"] = datetime.fromtimestamp(expires, timezone.utc).isoformat()
        payload = json.dumps({"entries": snapshot.entries, "source": snapshot.provenance}, ensure_ascii=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM handoff WHERE expires <= ?", (self.clock(),))
            if db.execute("SELECT count(*) FROM handoff").fetchone()[0] >= self.limit:
                raise OverflowError("연결 보관 한도에 도달했습니다. 기존 연결을 폐기하고 다시 시도해 주세요.")
            db.execute("INSERT INTO handoff VALUES (?, ?, ?, ?)", (digest(read), digest(revoke), expires, payload))
        return {"token": read, "revoke_token": revoke, "expires_at": snapshot.provenance["expires_at"],
                **snapshot.list_findings()}

    def get(self, token):
        hashed = digest(token)
        with self.connect() as db:
            db.execute("DELETE FROM handoff WHERE expires <= ?", (self.clock(),))
            row = db.execute("SELECT snapshot FROM handoff WHERE read_hash = ?", (hashed,)).fetchone()
        if row is None:
            raise LookupError("연결이 없거나 만료·폐기되었습니다.")
        data = json.loads(row[0])
        snapshot = Snapshot.__new__(Snapshot)
        snapshot.entries, snapshot.provenance = data["entries"], data["source"]
        return snapshot

    def revoke(self, token, revoke_token):
        with self.connect() as db:
            removed = db.execute("DELETE FROM handoff WHERE read_hash = ? AND revoke_hash = ?",
                                 (digest(token), digest(revoke_token))).rowcount
        if not removed:
            raise LookupError("폐기할 연결이 없거나 권한이 없습니다.")
