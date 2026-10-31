"""Expiring capabilities and bounded, durable API dispatch receipts; no code or API keys."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid


class WorkspaceStore:
    def __init__(self, path: Path, ttl=86400, clock=time.time, limit=128, job_limit=256):
        self.path, self.ttl, self.clock = path, ttl, clock
        self.limit, self.job_limit = limit, job_limit
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS workspaces (hash TEXT PRIMARY KEY, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    kind TEXT NOT NULL, request_key TEXT NOT NULL, data TEXT NOT NULL,
                    UNIQUE(owner,kind,request_key),
                    FOREIGN KEY(owner) REFERENCES workspaces(hash) ON DELETE CASCADE);
            ''')
        path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def owner(self, db, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('작업 공간이 없거나 만료되었습니다. create_workspace를 호출하세요.')
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not db.execute('SELECT 1 FROM workspaces WHERE hash=? AND expires>?',
                          (digest, self.clock())).fetchone():
            raise ValueError('작업 공간이 없거나 만료되었습니다. create_workspace를 호출하세요.')
        return digest

    def create(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM workspaces WHERE expires<=?', (self.clock(),))
            if db.execute('SELECT count(*) FROM workspaces').fetchone()[0] >= self.limit:
                raise ValueError('데모 작업 공간 한도에 도달했습니다. 나중에 다시 시도하세요.')
            token = secrets.token_urlsafe(32)
            expiry = self.clock() + self.ttl
            db.execute('INSERT INTO workspaces VALUES (?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), expiry))
        return {'workspace_token': token, 'expires_at_unix': expiry,
                'notice': '이 토큰은 본인 AI 대화에서만 사용하세요. URL·로그·저장소에 넣지 마세요.'}

    def close(self, token):
        with self.db() as db:
            owner = self.owner(db, token)
            db.execute('DELETE FROM workspaces WHERE hash=?', (owner,))
        return {'closed': True, 'notice': '접근 권한을 폐기했습니다. 이미 접수된 서버 작업은 취소되지 않습니다.'}

    def reserve(self, token, kind, key, metadata):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            owner = self.owner(db, token)
            old = db.execute('SELECT id,data FROM jobs WHERE owner=? AND kind=? AND request_key=?',
                             (owner, kind, key)).fetchone()
            if old:
                data = json.loads(old['data'])
                if data['input'] != metadata:
                    raise ValueError('같은 request_id를 다른 입력에 사용할 수 없습니다.')
                return old['id'], data, False
            db.execute('DELETE FROM workspaces WHERE expires<=?', (self.clock(),))
            total = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
            owned = db.execute('SELECT count(*) FROM jobs WHERE owner=?', (owner,)).fetchone()[0]
            if total >= self.job_limit or owned >= 16:
                raise ValueError('데모 작업 한도에 도달했습니다. 작업 공간당 16건입니다.')
            job = uuid.uuid4().hex
            data = {'state': 'dispatching', 'input': metadata}
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)', (job, owner, kind, key, json.dumps(data)))
            return job, data, True

    def get(self, token, job, kind):
        with self.db() as db:
            owner = self.owner(db, token)
            row = db.execute('SELECT data FROM jobs WHERE owner=? AND id=? AND kind=?',
                             (owner, job, kind)).fetchone()
            if not row:
                raise ValueError('이 작업 공간의 작업이 아닙니다.')
            return json.loads(row['data'])

    def update(self, token, job, kind, data):
        with self.db() as db:
            owner = self.owner(db, token)
            db.execute('UPDATE jobs SET data=? WHERE owner=? AND id=? AND kind=?',
                       (json.dumps(data), owner, job, kind))

    def analyses(self, token, scan_id):
        with self.db() as db:
            owner = self.owner(db, token)
            return [(r['id'], json.loads(r['data'])) for r in db.execute(
                "SELECT id,data FROM jobs WHERE owner=? AND kind='analysis'", (owner,))
                if json.loads(r['data'])['input']['scan_id'] == scan_id]
