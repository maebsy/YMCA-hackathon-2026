"""보안엔진 테스트 공통 준비물.

주의: 저장소의 pre-commit 훅과 CI(gitleaks)가 비밀값 모양 문자열을 막기 때문에,
가짜 비밀값은 소스에 통째로 쓰지 않고 실행할 때 조립한다.
"""
import random
import string
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def fake_stripe_key() -> str:
    rnd = random.Random(42)
    body = "".join(rnd.choice(string.ascii_letters + string.digits) for _ in range(24))
    return "sk" + "_live_" + body


@pytest.fixture
def vibe_site(tmp_path: Path) -> Path:
    """바이브코딩으로 만든 작은 사이트 (위험한 코드 + 비밀값 + 오래된 lodash)."""
    site = tmp_path / "site"
    (site / "app").mkdir(parents=True)
    (site / "api").mkdir()
    (site / "app" / "page.tsx").write_text(
        "'use client';\n"
        "import { createClient } from '@supabase/supabase-js';\n"
        "const sb = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY);\n"
        "export default function P({ html }) { return <div dangerouslySetInnerHTML={{ __html: html }} />; }\n",
        encoding="utf-8",
    )
    (site / "api" / "server.js").write_text(
        "app.get('/u', (req, res) => {\n"
        "  db.query(\"SELECT * FROM users WHERE id = \" + req.query.id);\n"
        "  const r = eval(req.query.expr); // nosemgrep\n"
        "});\n",
        encoding="utf-8",
    )
    (site / "api" / "config.js").write_text(
        f'const stripeKey = "{fake_stripe_key()}";\nmodule.exports = {{ stripeKey }};\n',
        encoding="utf-8",
    )
    (site / "package-lock.json").write_text(
        '{"name":"demo","version":"1.0.0","lockfileVersion":3,"requires":true,"packages":{'
        '"":{"name":"demo","version":"1.0.0","dependencies":{"lodash":"4.17.15"}},'
        '"node_modules/lodash":{"version":"4.17.15"}}}\n',
        encoding="utf-8",
    )
    return site
