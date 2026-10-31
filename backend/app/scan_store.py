"""Durable scan responses; PostgreSQL also stores the reviewed service relations."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re

from sqlalchemy import (BigInteger, CheckConstraint, Column, DateTime, JSON, MetaData,
                        String, Table, Text, Uuid, func, select, update)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import InvalidRequestError, NoSuchTableError


class ScanSchemaRequired(RuntimeError):
    """The explicit service schema is missing or too old for scan ingestion."""

LEASE_SECONDS = 120
metadata = MetaData()
scan_job = Table(
    "scan_job", metadata,
    Column("id", String(32), primary_key=True),
    Column("owner_id", Uuid),
    Column("repo_url", Text, nullable=False),
    Column("status", String(10), nullable=False),
    Column("scan_id", BigInteger),
    Column("result", JSON().with_variant(JSONB, "postgresql")),
    Column("error", JSON().with_variant(JSONB, "postgresql")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("lease_until", DateTime(timezone=True), nullable=False),
    CheckConstraint("status in ('queued','running','done','failed')"),
)


class ScanStore:
    def __init__(self, engine):
        self.engine = engine
        self.tables = None
        # PostgreSQL now() is frozen at transaction start, including while waiting
        # for another writer's lock. Leases need the actual time after that wait.
        self.now = (func.clock_timestamp() if engine.dialect.name == "postgresql" else
                    func.strftime("%Y-%m-%d %H:%M:%f", "now", type_=DateTime(timezone=True)))
        if engine.dialect.name == "postgresql":
            service = MetaData()
            try:
                service.reflect(bind=engine, only=["project", "scan", "tool_run", "finding", "scan_job"])
            except (InvalidRequestError, NoSuchTableError) as exc:
                raise ScanSchemaRequired("Apply db-schema.sql and migrations/052-scan-persistence.sql before starting scans") from exc
            self.tables = service.tables
            required = {
                "project": {"id", "owner_id", "claim_token_hash", "name", "repo_url"},
                "scan": {"id", "project_id", "status", "commit_sha", "summary", "started_at", "finished_at"},
                "tool_run": {"scan_id", "tool", "status", "coverage", "version", "duration_ms", "finding_count", "error"},
                "finding": {"scan_id", "fingerprint", "tool", "category", "rule_id", "title", "severity", "file_path",
                            "start_line", "end_line", "package_name", "package_ecosystem", "installed_version",
                            "fixed_version", "refs", "snippet", "raw", "llm_context"},
                "scan_job": set(scan_job.c.keys()),
            }
            if any(not columns.issubset(self.tables[name].c.keys()) for name, columns in required.items()):
                raise ScanSchemaRequired("Apply db-schema.sql and migrations/052-scan-persistence.sql")
        elif engine.dialect.name == "sqlite":
            # Local demo DB only. PostgreSQL schema changes are explicit SQL migrations.
            metadata.create_all(engine)
        else:
            raise RuntimeError("Scan persistence supports PostgreSQL or local SQLite")

    def create(self, job_id, repo_url, owner_id=None):
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            lease = conn.scalar(select(self.now)) + timedelta(seconds=LEASE_SECONDS)
            conn.execute(scan_job.insert().values(id=job_id, repo_url=repo_url, owner_id=owner_id,
                                                 status="queued", created_at=now, updated_at=now, lease_until=lease))

    def get(self, job_id, owner_id=None):
        with self.engine.begin() as conn:
            # DB time and a lease predicate keep another API process's live jobs intact.
            conn.execute(update(scan_job).where(
                scan_job.c.id == job_id, scan_job.c.owner_id == owner_id,
                scan_job.c.status.in_(["queued", "running"]), scan_job.c.lease_until <= self.now,
            ).values(status="failed", updated_at=self.now, error={
                "code": "SCAN_INTERRUPTED", "message": "검사 서버가 중단되었습니다. 다시 검사해 주세요.",
            }))
            row = conn.execute(select(scan_job).where(
                scan_job.c.id == job_id, scan_job.c.owner_id == owner_id,
            )).mappings().first()
            if row is None:
                return None
            return {"job_id": row["id"], "status": row["status"], "repo_url": row["repo_url"],
                    "result": row["result"], "error": row["error"]}

    def previous_result(self, engine_scan_id, repo_url, owner_id=None):
        """Only stored scanner data may cross the rescan trust boundary.

        Anonymous engine UUIDs are capabilities, like the existing job UUID.
        Authenticated results additionally require the same verified owner.
        """
        with self.engine.connect() as conn:
            snapshot = conn.scalar(select(scan_job.c.result).where(
                scan_job.c.owner_id == owner_id, scan_job.c.repo_url == repo_url,
                scan_job.c.status.in_(["done", "failed"]),
                scan_job.c.result["result"]["scan_id"].as_string() == engine_scan_id,
            ).order_by(scan_job.c.created_at.desc(), scan_job.c.id).limit(1))
            return snapshot["result"] if snapshot is not None else None

    def running(self, job_id):
        with self.engine.begin() as conn:
            return conn.execute(update(scan_job).where(
                scan_job.c.id == job_id, scan_job.c.status == "queued",
                scan_job.c.lease_until > self.now,
            ).values(status="running", updated_at=datetime.now(timezone.utc))).rowcount == 1

    def heartbeat(self, job_id):
        with self.engine.begin() as conn:
            lease = conn.scalar(select(self.now)) + timedelta(seconds=LEASE_SECONDS)
            return conn.execute(update(scan_job).where(
                scan_job.c.id == job_id, scan_job.c.status.in_(["queued", "running"]),
                scan_job.c.lease_until > self.now,
            ).values(lease_until=lease, updated_at=self.now)).rowcount == 1

    def fail(self, job_id, error):
        with self.engine.begin() as conn:
            conn.execute(update(scan_job).where(
                scan_job.c.id == job_id, scan_job.c.status.in_(["queued", "running"]),
            ).values(status="failed", error=error, updated_at=datetime.now(timezone.utc)))

    def complete(self, job_id, response):
        """All findings, coverage, snapshot and worker-ready status commit together."""
        with self.engine.begin() as conn:
            query = select(scan_job).where(scan_job.c.id == job_id)
            if self.tables is not None:
                query = query.with_for_update()
            job = conn.execute(query).mappings().one()
            if job["status"] in ("done", "failed"):
                return  # Retried completion cannot duplicate findings or overwrite immutable input.
            if not conn.scalar(select(scan_job.c.id).where(
                scan_job.c.id == job_id, scan_job.c.lease_until > self.now,
            )):
                raise ValueError("Scan worker lease expired")
            result = response["result"]
            if result.get("schema_version") != "1.0" or not isinstance(result.get("findings"), list):
                raise ValueError("Expected an engine scan_result, not llm-input")
            if result.get("status") not in ("complete", "partial", "failed"):
                raise ValueError("Invalid engine status")
            if (result.get("target") or {}).get("repo_url") != job["repo_url"]:
                raise ValueError("Engine target mismatch")
            # Persist all findings, independently of the API's top-50 explanation preview.
            from security_engine import build_llm_input
            payload = build_llm_input(result, max_items=len(result["findings"]))
            # Engine JSON is the storage contract. Bounded FindingInput validation belongs
            # to the LLM worker and must never discard a valid, potentially long finding.
            by_id = {item["id"]: item for item in payload["items"]}
            if len(by_id) != len(result["findings"]):
                raise ValueError("Duplicate or missing finding identity")
            snapshot = dict(response)
            scan_id = None
            if self.tables is not None:
                scan_id = self._save_relations(conn, job, result, by_id)
                snapshot["db_scan_id"] = scan_id
            failed = result["status"] == "failed"
            completed = conn.execute(update(scan_job).where(
                scan_job.c.id == job_id, scan_job.c.status.in_(["queued", "running"]),
                scan_job.c.lease_until > self.now,
            ).values(
                status="failed" if failed else "done", result=snapshot, scan_id=scan_id,
                error={"code": "ENGINE_FAILED", "message": "검사 도구가 모두 실패했습니다."} if failed else None,
                updated_at=datetime.now(timezone.utc),
            ))
            if completed.rowcount != 1:
                # SQLite has no SELECT FOR UPDATE. Re-check atomically so a late
                # writer cannot replace a failure or another completed snapshot.
                raise ValueError("Scan worker lease expired or job already finished")

    def _save_relations(self, conn, job, result, by_id):
        project, scan, tool_run, finding = (self.tables[name] for name in ("project", "scan", "tool_run", "finding"))
        now = datetime.now(timezone.utc)
        # An anonymous job UUID is its existing read capability; store only its hash on project.
        project_id = conn.scalar(project.insert().values(
            owner_id=job["owner_id"],
            claim_token_hash=sha256(job["id"].encode()).hexdigest() if job["owner_id"] is None else None,
            name=job["repo_url"].rstrip("/").split("/")[-1][:100], repo_url=job["repo_url"],
        ).returning(project.c.id))
        scan_id = conn.scalar(scan.insert().values(
            project_id=project_id, status="normalizing", commit_sha=result["target"].get("commit_sha"),
            summary=result["summary"], started_at=job["created_at"],
        ).returning(scan.c.id))
        states = {"ok": "done", "error": "failed", "skipped": "skipped",
                  "no_target": "skipped", "not_installed": "skipped"}
        for tool, coverage in result["coverage"].items():
            conn.execute(tool_run.insert().values(
                scan_id=scan_id, tool=tool, status=states[coverage["status"]], coverage=coverage,
                version=coverage.get("version"), duration_ms=round(coverage.get("duration_sec", 0) * 1000),
                finding_count=coverage.get("count"), error=coverage.get("message") or None,
            ))
        for raw in result["findings"]:
            adapted = by_id[raw["fingerprint"]]
            location, package = raw.get("location") or {}, raw.get("package") or {}
            hint = adapted["fix_hint"]
            values = {key: raw[key] for key in ("fingerprint", "tool", "category", "rule_id", "title", "severity")}
            values.update(file_path=location.get("file"), start_line=location.get("start_line"),
                          end_line=location.get("end_line"), package_name=package.get("name"),
                          package_ecosystem=package.get("ecosystem"), installed_version=package.get("version"),
                          fixed_version=hint.get("target_version"), snippet=adapted.get("code") or None)
            # LLM input deliberately shortens references; DB retains the full engine list.
            ids = [raw["rule_id"], *raw.get("aliases", [])]
            values["refs"] = {"cve": sorted({item for item in ids if re.fullmatch(r"CVE-\d{4}-\d+", item, re.I)}),
                              "cwe": raw.get("cwe", []), "urls": raw.get("references", [])}
            # Preserve the full already-masked normalized finding even without --include-raw.
            # No additional tool invocation or unredacted source is read here.
            context = {key: adapted.get(key) for key in ("what", "flags", "fix_hint", "status", "change")}
            conn.execute(finding.insert().values(scan_id=scan_id, raw=raw, llm_context=context, **values))
        status = "failed" if result["status"] == "failed" else (
            "explaining" if job["owner_id"] is not None and by_id else "done")
        conn.execute(update(scan).where(scan.c.id == scan_id).values(
            status=status, finished_at=now if status in ("done", "failed") else None,
        ))
        return scan_id
