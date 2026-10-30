"""PostgreSQL queue using existing #7 tables; schema changes are explicit migrations only."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import MetaData, and_, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.llm.schemas import ExplainResult, FindingInput

MAX_ATTEMPTS = 3


class NotFound(Exception):
    pass


class ScanNotReady(Exception):
    pass


class JobStore:
    def __init__(self, engine):
        if engine.dialect.name != "postgresql":
            raise RuntimeError("LLM jobs require PostgreSQL and the reviewed #7/#26 migrations")
        self.engine = engine
        metadata = MetaData()
        metadata.reflect(bind=engine, only=["project", "scan", "finding", "explanation", "llm_job"])
        self.project, self.scan, self.finding, self.explanation, self.job = (
            metadata.tables[name] for name in ("project", "scan", "finding", "explanation", "llm_job")
        )
        for table, required in (
            (self.finding, {"llm_context", "explain_status"}),
            (self.explanation, {"red_verdict", "red_rounds", "needs_manual_review", "completion_tokens"}),
            (self.job, {"lease_token", "lease_until", "attempts", "result"}),
        ):
            if not required.issubset(table.c.keys()):
                raise RuntimeError("Apply the reviewed #26 migration before enabling LLM jobs")

    def _owned_scan(self, conn, scan_id, user_id, lock=False):
        query = select(self.scan).join(self.project).where(
            self.scan.c.id == scan_id, self.project.c.owner_id == user_id,
        )
        if lock:
            query = query.with_for_update(of=self.scan)
        row = conn.execute(query).mappings().first()
        if row is None:
            raise NotFound
        return row

    def _enqueue(self, conn, scan_id):
        # No browser text, model choice, prompt, source URL or ownership field is accepted.
        ids = conn.scalars(select(self.finding.c.id).where(
            self.finding.c.scan_id == scan_id, self.finding.c.explain_status == "none",
        ).order_by(self.finding.c.id).limit(50)).all()
        added = []
        for finding_id in ids:
            new_id = conn.scalar(insert(self.job).values(
                id=uuid4(), finding_id=finding_id,
            ).on_conflict_do_nothing(index_elements=["finding_id"]).returning(self.job.c.id))
            if new_id is not None:
                conn.execute(update(self.finding).where(self.finding.c.id == finding_id).values(explain_status="pending"))
                added.append(str(new_id))
        return added

    def enqueue(self, scan_id, user_id):
        with self.engine.begin() as conn:
            scan = self._owned_scan(conn, scan_id, user_id, lock=True)
            if scan["status"] not in ("explaining", "done"):
                raise ScanNotReady
            return self._enqueue(conn, scan_id)

    def enqueue_ready(self):
        """Pick up committed scanner results once the orchestrator marks the scan explaining."""
        with self.engine.begin() as conn:
            scan_id = conn.scalar(select(self.scan.c.id).join(self.project).where(
                self.scan.c.status == "explaining", self.project.c.owner_id.is_not(None),
                exists(select(self.finding.c.id).where(
                    self.finding.c.scan_id == self.scan.c.id, self.finding.c.explain_status == "none",
                )),
            ).order_by(self.scan.c.id).limit(1).with_for_update(skip_locked=True, of=self.scan))
            return self._enqueue(conn, scan_id) if scan_id is not None else []

    def list_results(self, scan_id, user_id, after_id, limit):
        with self.engine.begin() as conn:
            self._owned_scan(conn, scan_id, user_id)
            rows = conn.execute(select(
                self.finding.c.id.label("finding_id"), self.finding.c.fingerprint,
                self.finding.c.explain_status, self.job.c.id.label("job_id"),
                self.job.c.status.label("job_status"), self.job.c.attempts,
                self.job.c.result, self.job.c.error_code,
            ).outerjoin(self.job, self.finding.c.id == self.job.c.finding_id).where(
                self.finding.c.scan_id == scan_id, self.finding.c.id > after_id,
            ).order_by(self.finding.c.id).limit(limit + 1)).mappings().all()
            page = [dict(row) for row in rows[:limit]]
            return {"scan_id": scan_id, "items": page,
                    "next_after_id": page[-1]["finding_id"] if len(rows) > limit else None}

    def claim(self, lease_s):
        with self.engine.begin() as conn:
            # A process crash may consume an attempt; never leave exhausted leases pending forever.
            expired = conn.execute(select(self.job).where(
                self.job.c.status == "running", self.job.c.lease_until <= func.now(),
                self.job.c.attempts >= MAX_ATTEMPTS,
            ).limit(50).with_for_update(skip_locked=True)).mappings().all()
            for row in expired:
                self._fail(conn, row["id"], row["finding_id"], "WORKER_LOST")
            query = select(self.job).where(
                or_(self.job.c.status == "queued", and_(
                    self.job.c.status == "running", self.job.c.lease_until <= func.now(),
                )), self.job.c.attempts < MAX_ATTEMPTS,
            ).order_by(self.job.c.created_at, self.job.c.id).limit(1).with_for_update(skip_locked=True)
            row = conn.execute(query).mappings().first()
            if row is None:
                return None
            token = uuid4()
            now = conn.scalar(select(func.now()))
            conn.execute(update(self.job).where(self.job.c.id == row["id"]).values(
                status="running", lease_until=now + timedelta(seconds=lease_s),
                attempts=row["attempts"] + 1, updated_at=now,
                lease_token=token,
            ))
            finding = conn.execute(select(self.finding).where(
                self.finding.c.id == row["finding_id"],
            )).mappings().one()
            # Context is scanner-owned. It may supplement, but cannot overwrite DB identity/location.
            context = finding["llm_context"]
            invalid_context = not isinstance(context, dict)
            data = {key: value for key, value in ({} if invalid_context else context).items()
                    if key in FindingInput.model_fields}
            data.update({key: value for key, value in finding.items() if key in FindingInput.model_fields})
            return {"id": row["id"], "token": token, "finding_id": row["finding_id"],
                    "input": data, "invalid_context": invalid_context}

    def _fence(self, job_id, token):
        return and_(self.job.c.id == job_id, self.job.c.lease_token == token,
                    self.job.c.status == "running", self.job.c.lease_until > func.now())

    def heartbeat(self, job_id, token, lease_s):
        with self.engine.begin() as conn:
            now = conn.scalar(select(func.now()))
            return conn.execute(update(self.job).where(self._fence(job_id, token)).values(
                lease_until=now + timedelta(seconds=lease_s), updated_at=now,
            )).rowcount == 1

    def _finish_scan(self, conn, finding_id):
        scan_id = conn.scalar(select(self.finding.c.scan_id).where(self.finding.c.id == finding_id))
        # Serialize completion with other workers/enqueue; the scanner owns all other scan states.
        conn.execute(select(self.scan.c.id).where(self.scan.c.id == scan_id).with_for_update()).first()
        conn.execute(update(self.scan).where(
            self.scan.c.id == scan_id, self.scan.c.status == "explaining",
            ~exists(select(self.finding.c.id).where(
                self.finding.c.scan_id == scan_id, self.finding.c.explain_status.in_(["none", "pending"]),
            )),
        ).values(status="done", finished_at=func.now()))

    def _fail(self, conn, job_id, finding_id, code):
        conn.execute(update(self.job).where(self.job.c.id == job_id).values(
            status="failed", error_code=code, result=None, lease_token=None, lease_until=None, updated_at=func.now(),
        ))
        conn.execute(update(self.finding).where(self.finding.c.id == finding_id).values(explain_status="failed"))
        self._finish_scan(conn, finding_id)

    def fail(self, claim, code):
        with self.engine.begin() as conn:
            row = conn.execute(select(self.job.c.id).where(
                self._fence(claim["id"], claim["token"]),
            ).with_for_update()).first()
            if row is None:
                return False
            self._fail(conn, claim["id"], claim["finding_id"], code)
            return True

    def complete(self, claim, result: ExplainResult):
        if result.fingerprint != claim["input"]["fingerprint"]:
            raise ValueError("Result identity mismatch")
        if result.status == "done" and (result.explanation is None
                or result.explanation.fingerprint != result.fingerprint or result.explanation.variant != "D"):
            raise ValueError("Invalid Red-Blue result")
        with self.engine.begin() as conn:
            updated = conn.execute(update(self.job).where(self._fence(claim["id"], claim["token"])).values(
                status=result.status, result=result.model_dump(mode="json", exclude={"error"}),
                error_code=result.error_code, lease_token=None, lease_until=None, updated_at=func.now(),
            ))
            if updated.rowcount != 1:
                return False
            if result.status == "done":
                values = {key: value for key, value in result.explanation.model_dump(mode="json").items()
                          if key in self.explanation.c}
                values["finding_id"] = claim["finding_id"]
                conn.execute(insert(self.explanation).values(**values).on_conflict_do_update(
                    index_elements=["finding_id", "variant"], set_=values,
                ))
            conn.execute(update(self.finding).where(self.finding.c.id == claim["finding_id"]).values(
                explain_status=result.status,
            ))
            self._finish_scan(conn, claim["finding_id"])
            return True
