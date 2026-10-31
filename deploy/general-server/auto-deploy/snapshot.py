"""Snapshot the existing SQLite DB without opening or migrating application tables."""
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import inspect, text

load_dotenv(Path.home()/".config/72hours/backend.env", override=True)
sys.path.insert(0, str(Path.cwd()))
from app.db import engine  # noqa: E402

destination = Path(sys.argv[1])
with engine.connect() as conn:
    for table in ("scan_job", "llm_job"):
        if table in inspect(engine).get_table_names():
            if conn.scalar(text(f"SELECT count(*) FROM {table} WHERE status IN ('queued','running')")):
                raise SystemExit("Active durable jobs; refusing cutover")
if engine.dialect.name == "sqlite":
    database = Path(engine.url.database).resolve(strict=True)
    if database.is_relative_to(Path.cwd().parent):
        raise SystemExit("SQLite must be configured outside release directories before deployment")
    with sqlite3.connect("file:" + quote(str(database)) + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination/"database.sqlite") as target:
            source.backup(target)
(destination/"metadata.json").write_text(json.dumps({"database": engine.dialect.name,
    "note": "Rollback restores code only. Never automatically restore the database over new user data."}))
