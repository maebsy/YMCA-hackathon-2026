"""Apply SQL to a fresh random DB on an explicit disposable loopback PostgreSQL only."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (ROOT / "docs/db-schema.sql").read_text(encoding="utf-8")
TABLES = {"plan", "profile", "project", "scan", "tool_run", "finding", "explanation"}


@pytest.fixture(params=["fresh", "upgrade"])
def db(request):
    url = os.environ.get("DB_SCHEMA_TEST_URL")
    if not url:
        pytest.skip("Set DB_SCHEMA_TEST_URL to disposable loopback Postgres")
    config = conninfo_to_dict(url)
    assert config.get("host") in ("localhost", "127.0.0.1") and config.get("dbname") == "postgres"
    name = "ymca_schema_test_" + uuid4().hex
    owner = uuid4()
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(make_conninfo(url, dbname=name), autocommit=True) as conn:
                conn.execute("CREATE SCHEMA auth")
                conn.execute("CREATE TABLE auth.users(id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb)")
                conn.execute("INSERT INTO auth.users VALUES (%s,'test@example.invalid','{\"user_name\":\"Existing user\"}')", (owner,))
                if request.param == "upgrade":
                    conn.execute((ROOT / "tests/db/legacy-schema.sql").read_text(encoding="utf-8"))
                conn.execute(SCHEMA)
                conn.execute(SCHEMA)
                yield conn, owner
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def test_core_tables_and_rls(db):
    conn, _ = db
    rows = conn.execute("SELECT relname,relrowsecurity FROM pg_class JOIN pg_namespace ON relnamespace=pg_namespace.oid WHERE nspname='public' AND relkind='r'").fetchall()
    assert {name for name, _ in rows} == TABLES
    assert all(enabled for _, enabled in rows)


def test_existing_and_new_user_profile(db):
    conn, owner = db
    assert conn.execute("SELECT display_name,plan_code FROM profile WHERE id=%s", (owner,)).fetchone() == ("Existing user", "demo")
    other = uuid4()
    conn.execute("INSERT INTO auth.users VALUES (%s,'new@example.invalid','{\"full_name\":\"New user\"}')", (other,))
    assert conn.execute("SELECT display_name,plan_code FROM profile WHERE id=%s", (other,)).fetchone() == ("New user", "demo")


def test_reapply_preserves_profile_and_plan_settings(db):
    conn, owner = db
    conn.execute("UPDATE profile SET display_name='Edited' WHERE id=%s", (owner,))
    conn.execute("UPDATE plan SET max_projects=3,max_scans_per_day=10 WHERE code='demo'")
    conn.execute(SCHEMA)
    assert conn.execute("SELECT display_name FROM profile WHERE id=%s", (owner,)).fetchone()[0] == "Edited"
    assert conn.execute("SELECT monthly_price,max_projects,max_scans_per_day FROM plan").fetchone() == (0, 3, 10)


def test_plan_only_accepts_free_demo_and_positive_limits(db):
    conn, _ = db
    for statement in ("UPDATE plan SET monthly_price=1", "UPDATE plan SET max_projects=0", "INSERT INTO plan(code) VALUES ('paid')"):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(statement)


def project_and_scan(conn, owner):
    project = conn.execute("INSERT INTO project(owner_id,name,repo_url) VALUES (%s,'Example','https://github.com/example/app') RETURNING id", (owner,)).fetchone()[0]
    scan = conn.execute("INSERT INTO scan(project_id,status) VALUES (%s,'explaining') RETURNING id", (project,)).fetchone()[0]
    return project, scan


def test_project_identity_and_concurrent_scan_constraint(db):
    conn, owner = db
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO project(name,repo_url) VALUES ('No owner','https://github.com/example/app')")
    project, scan = project_and_scan(conn, owner)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO scan(project_id) VALUES (%s)", (project,))
    conn.execute("UPDATE scan SET status='done' WHERE id=%s", (scan,))
    conn.execute("INSERT INTO scan(project_id) VALUES (%s)", (project,))


def test_engine_and_red_blue_contract_and_cascade(db):
    conn, owner = db
    _, scan = project_and_scan(conn, owner)
    for tool in ("osv", "semgrep", "gitleaks", "config"):
        conn.execute("INSERT INTO tool_run(scan_id,tool,status,coverage) VALUES (%s,%s,'skipped','{\"registry_used\":false,\"state\":\"out_of_scope\"}')", (scan, tool))
    finding = conn.execute("""INSERT INTO finding(scan_id,fingerprint,tool,category,rule_id,title,severity,raw,explain_status,llm_context)
        VALUES (%s,'fp','config','config','test.rule','Config example','unknown','{}','skipped','{"status":"out_of_scope","change":"unverifiable"}') RETURNING id""", (scan,)).fetchone()[0]
    conn.execute("""INSERT INTO explanation(finding_id,variant,summary,why_risky,priority,ai_fix_prompt,model,red_verdict,red_rounds,needs_manual_review,completion_tokens,covers)
        VALUES (%s,'D','Summary','Reason','soon','Fix prompt','fake','pass','[{"round":1,"verdict":"pass","issues":[]}]',false,1,'["fp"]')""", (finding,))
    assert conn.execute("SELECT red_verdict,needs_manual_review,covers FROM explanation").fetchone() == ("pass", False, ["fp"])
    conn.execute("DELETE FROM auth.users WHERE id=%s", (owner,))
    for table in TABLES - {"plan"}:
        assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 0


def test_rls_blocks_even_explicitly_granted_client(db):
    conn, _ = db
    role = "schema_client_" + uuid4().hex
    # Role/grants and all effects are rolled back; no shared role is left behind.
    conn.execute("BEGIN")
    try:
        conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        for table in TABLES:
            assert conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO plan(code) VALUES ('demo')")
    finally:
        conn.execute("ROLLBACK")
