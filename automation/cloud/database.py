"""
Database Layer for Cloud Control Plane.
Supports SQLite (development/local) and PostgreSQL (production) via DATABASE_URL.
Thread-safe connection pooling, parameterized SQL queries, and production hard gates.
"""
import os
import re
import json
import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("ReelsAIFactory.CloudDatabase")

from .models import (
    CloudWeek,
    CloudWeekStatus,
    TelegramApproval,
    TelegramApprovalStatus,
    LocalWorkerCommand,
    CommandType,
    CommandStatus,
    InstagramScheduledJob,
    InstagramJobStatus,
    WorkerHeartbeat,
    NotificationLog
)


class Database:
    """Database manager for Cloud Control Plane."""

    def __init__(self, database_url: str = "sqlite:///workspace/cloud_control_plane.db", is_production: bool = False):
        self.database_url = database_url.strip()
        self.is_production = is_production
        self._lock = threading.RLock()
        
        # Hard Gate: Production requires PostgreSQL
        if self.is_production and not (self.database_url.startswith("postgresql://") or self.database_url.startswith("postgres://")):
            raise ValueError("PRODUCTION_DATABASE_INVALID: Production environment requires PostgreSQL DATABASE_URL")

        self._is_sqlite = self.database_url.startswith("sqlite:")
        self._is_postgres = self.database_url.startswith("postgresql://") or self.database_url.startswith("postgres://")

        if self._is_sqlite:
            db_path_str = self.database_url.replace("sqlite:///", "").replace("sqlite://", "")
            self.db_path = Path(db_path_str).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.db_path = None

        self.init_db()

    def _get_pg_connection(self):
        """Attempts to connect to PostgreSQL using available drivers."""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
            return conn
        except ImportError:
            try:
                import psycopg
                from psycopg.rows import dict_row
                conn = psycopg.connect(self.database_url, row_factory=dict_row)
                return conn
            except ImportError:
                raise RuntimeError("PostgreSQL driver (psycopg2 or psycopg) is required for PostgreSQL DATABASE_URL.")

    @contextmanager
    def get_connection(self):
        """Context manager yielding a database connection."""
        with self._lock:
            if self._is_sqlite:
                conn = sqlite3.connect(str(self.db_path), timeout=30.0)
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
            elif self._is_postgres:
                conn = self._get_pg_connection()
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
            else:
                raise ValueError(f"Unsupported database scheme: {self.database_url}")

    def _execute(self, cur, sql: str, params: Tuple = ()) -> Any:
        """Executes query with appropriate parameter placeholder translation (? -> %s for PG)."""
        if self._is_postgres:
            pg_sql = sql.replace("?", "%s")
            return cur.execute(pg_sql, params)
        return cur.execute(sql, params)

    def init_db(self) -> None:
        """Initializes tables and schema if not present."""
        with self.get_connection() as conn:
            cur = conn.cursor()

            # 1. Cloud Weeks
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cloud_weeks (
                week_id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                timezone TEXT DEFAULT 'Europe/Istanbul',
                status TEXT NOT NULL,
                target_reels INTEGER DEFAULT 14,
                approval_status TEXT DEFAULT 'PENDING',
                approval_sent_at TEXT,
                approved_at TEXT,
                rejected_at TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            """)

            # 2. Telegram Approvals
            cur.execute("""
            CREATE TABLE IF NOT EXISTS telegram_approvals (
                approval_id TEXT PRIMARY KEY,
                week_id TEXT NOT NULL,
                next_week_id TEXT NOT NULL,
                status TEXT NOT NULL,
                telegram_message_id BIGINT,
                telegram_chat_id BIGINT,
                token TEXT,
                expires_at TEXT,
                responded_at TEXT,
                response TEXT,
                created_at TEXT
            );
            """)

            # 3. Local Worker Commands
            cur.execute("""
            CREATE TABLE IF NOT EXISTS local_worker_commands (
                command_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                week_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT,
                claimed_by TEXT,
                claimed_at TEXT,
                completed_at TEXT,
                attempt_count INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TEXT
            );
            """)

            # 4. Instagram Scheduled Jobs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS instagram_scheduled_jobs (
                job_id TEXT PRIMARY KEY,
                week_id TEXT NOT NULL,
                reel_id TEXT NOT NULL,
                scheduled_at_local TEXT NOT NULL,
                scheduled_at_utc TEXT NOT NULL,
                timezone TEXT DEFAULT 'Europe/Istanbul',
                media_object_key TEXT,
                media_sha256 TEXT,
                caption TEXT,
                status TEXT NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                claimed_by TEXT,
                claimed_at TEXT,
                lease_expires_at TEXT,
                container_id TEXT,
                remote_media_id TEXT,
                permalink TEXT,
                published_at TEXT,
                last_error TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            """)

            # 5. Worker Heartbeats
            cur.execute("""
            CREATE TABLE IF NOT EXISTS worker_heartbeats (
                worker_id TEXT PRIMARY KEY,
                hostname_hash TEXT NOT NULL,
                version TEXT,
                capabilities_json TEXT,
                last_seen_at TEXT NOT NULL
            );
            """)

            # 6. Notification Logs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                notification_id TEXT PRIMARY KEY,
                notification_type TEXT NOT NULL,
                recipient TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                sent_at TEXT NOT NULL
            );
            """)

            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ig_status ON instagram_scheduled_jobs(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_status ON local_worker_commands(status);")

    # =========================================================================
    # CLOUD WEEKS OPERATIONS
    # =========================================================================

    def save_week(self, week: CloudWeek) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            INSERT INTO cloud_weeks (
                week_id, start_date, end_date, timezone, status, target_reels,
                approval_status, approval_sent_at, approved_at, rejected_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_id) DO UPDATE SET
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                timezone=excluded.timezone,
                status=excluded.status,
                target_reels=excluded.target_reels,
                approval_status=excluded.approval_status,
                approval_sent_at=excluded.approval_sent_at,
                approved_at=excluded.approved_at,
                rejected_at=excluded.rejected_at,
                updated_at=excluded.updated_at;
            """
            self._execute(cur, sql, (
                week.week_id, week.start_date, week.end_date, week.timezone,
                week.status.value if isinstance(week.status, CloudWeekStatus) else str(week.status),
                week.target_reels, week.approval_status, week.approval_sent_at,
                week.approved_at, week.rejected_at, week.created_at, week.updated_at
            ))
            return True

    def get_week(self, week_id: str) -> Optional[CloudWeek]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            self._execute(cur, "SELECT * FROM cloud_weeks WHERE week_id = ?", (week_id,))
            row = cur.fetchone()
            if not row:
                return None
            return CloudWeek(
                week_id=row["week_id"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                timezone=row["timezone"],
                status=CloudWeekStatus(row["status"]),
                target_reels=row["target_reels"],
                approval_status=row["approval_status"],
                approval_sent_at=row["approval_sent_at"],
                approved_at=row["approved_at"],
                rejected_at=row["rejected_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def list_active_weeks(self) -> List[CloudWeek]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM cloud_weeks WHERE status NOT IN ('COMPLETED', 'REJECTED') ORDER BY start_date ASC")
            rows = cur.fetchall()
            return [
                CloudWeek(
                    week_id=r["week_id"],
                    start_date=r["start_date"],
                    end_date=r["end_date"],
                    timezone=r["timezone"],
                    status=CloudWeekStatus(r["status"]),
                    target_reels=r["target_reels"],
                    approval_status=r["approval_status"],
                    approval_sent_at=r["approval_sent_at"],
                    approved_at=r["approved_at"],
                    rejected_at=r["rejected_at"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in rows
            ]

    # =========================================================================
    # TELEGRAM APPROVALS
    # =========================================================================

    def save_approval(self, approval: TelegramApproval) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            INSERT INTO telegram_approvals (
                approval_id, week_id, next_week_id, status, telegram_message_id,
                telegram_chat_id, token, expires_at, responded_at, response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(approval_id) DO UPDATE SET
                status=excluded.status,
                telegram_message_id=excluded.telegram_message_id,
                telegram_chat_id=excluded.telegram_chat_id,
                responded_at=excluded.responded_at,
                response=excluded.response;
            """
            self._execute(cur, sql, (
                approval.approval_id, approval.week_id, approval.next_week_id,
                approval.status.value if isinstance(approval.status, TelegramApprovalStatus) else str(approval.status),
                approval.telegram_message_id, approval.telegram_chat_id, approval.token,
                approval.expires_at, approval.responded_at, approval.response, approval.created_at
            ))
            return True

    def get_approval(self, approval_id: str) -> Optional[TelegramApproval]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            self._execute(cur, "SELECT * FROM telegram_approvals WHERE approval_id = ?", (approval_id,))
            r = cur.fetchone()
            if not r:
                return None
            return TelegramApproval(
                approval_id=r["approval_id"],
                week_id=r["week_id"],
                next_week_id=r["next_week_id"],
                status=TelegramApprovalStatus(r["status"]),
                telegram_message_id=r["telegram_message_id"],
                telegram_chat_id=r["telegram_chat_id"],
                token=r["token"],
                expires_at=r["expires_at"],
                responded_at=r["responded_at"],
                response=r["response"],
                created_at=r["created_at"]
            )

    def get_pending_approval_for_week(self, week_id: str) -> Optional[TelegramApproval]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            self._execute(cur, "SELECT * FROM telegram_approvals WHERE week_id = ? AND status = 'PENDING'", (week_id,))
            r = cur.fetchone()
            if not r:
                return None
            return TelegramApproval(
                approval_id=r["approval_id"],
                week_id=r["week_id"],
                next_week_id=r["next_week_id"],
                status=TelegramApprovalStatus(r["status"]),
                telegram_message_id=r["telegram_message_id"],
                telegram_chat_id=r["telegram_chat_id"],
                token=r["token"],
                expires_at=r["expires_at"],
                responded_at=r["responded_at"],
                response=r["response"],
                created_at=r["created_at"]
            )

    # =========================================================================
    # LOCAL WORKER COMMANDS
    # =========================================================================

    def create_command(self, cmd: LocalWorkerCommand) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            # Idempotency check: don't create duplicate pending command for same (type, week_id)
            self._execute(
                cur,
                "SELECT command_id FROM local_worker_commands WHERE type = ? AND week_id = ? AND status IN ('PENDING', 'CLAIMED', 'RUNNING')",
                (cmd.type.value if isinstance(cmd.type, CommandType) else str(cmd.type), cmd.week_id)
            )
            if cur.fetchone():
                logger.info(f"[DB] Command {cmd.type} for {cmd.week_id} already exists in queue. Skipping duplicate.")
                return False

            sql = """
            INSERT INTO local_worker_commands (
                command_id, type, week_id, status, payload_json, claimed_by,
                claimed_at, completed_at, attempt_count, last_error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self._execute(cur, sql, (
                cmd.command_id,
                cmd.type.value if isinstance(cmd.type, CommandType) else str(cmd.type),
                cmd.week_id,
                cmd.status.value if isinstance(cmd.status, CommandStatus) else str(cmd.status),
                json.dumps(cmd.payload),
                cmd.claimed_by,
                cmd.claimed_at,
                cmd.completed_at,
                cmd.attempt_count,
                cmd.last_error,
                cmd.created_at
            ))
            return True

    def get_next_pending_command(self) -> Optional[LocalWorkerCommand]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM local_worker_commands WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 1")
            r = cur.fetchone()
            if not r:
                return None
            return LocalWorkerCommand(
                command_id=r["command_id"],
                type=CommandType(r["type"]),
                week_id=r["week_id"],
                status=CommandStatus(r["status"]),
                payload=json.loads(r["payload_json"] or "{}"),
                claimed_by=r["claimed_by"],
                claimed_at=r["claimed_at"],
                completed_at=r["completed_at"],
                attempt_count=r["attempt_count"],
                last_error=r["last_error"],
                created_at=r["created_at"]
            )

    def claim_command(self, command_id: str, worker_id: str) -> bool:
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            UPDATE local_worker_commands
            SET status = 'CLAIMED', claimed_by = ?, claimed_at = ?
            WHERE command_id = ? AND status = 'PENDING'
            """
            self._execute(cur, sql, (worker_id, now_str, command_id))
            return cur.rowcount > 0

    def complete_command(self, command_id: str, status: CommandStatus, error_msg: Optional[str] = None) -> bool:
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            UPDATE local_worker_commands
            SET status = ?, completed_at = ?, last_error = ?
            WHERE command_id = ?
            """
            self._execute(cur, sql, (
                status.value if isinstance(status, CommandStatus) else str(status),
                now_str,
                error_msg,
                command_id
            ))
            return cur.rowcount > 0

    # =========================================================================
    # INSTAGRAM SCHEDULED JOBS
    # =========================================================================

    def save_instagram_job(self, job: InstagramScheduledJob) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            INSERT INTO instagram_scheduled_jobs (
                job_id, week_id, reel_id, scheduled_at_local, scheduled_at_utc,
                timezone, media_object_key, media_sha256, caption, status, attempt_count,
                claimed_by, claimed_at, lease_expires_at, container_id, remote_media_id,
                permalink, published_at, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                media_object_key=excluded.media_object_key,
                media_sha256=excluded.media_sha256,
                caption=excluded.caption,
                status=excluded.status,
                attempt_count=excluded.attempt_count,
                claimed_by=excluded.claimed_by,
                claimed_at=excluded.claimed_at,
                lease_expires_at=excluded.lease_expires_at,
                container_id=excluded.container_id,
                remote_media_id=excluded.remote_media_id,
                permalink=excluded.permalink,
                published_at=excluded.published_at,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at;
            """
            self._execute(cur, sql, (
                job.job_id, job.week_id, job.reel_id, job.scheduled_at_local, job.scheduled_at_utc,
                job.timezone, job.media_object_key, job.media_sha256, job.caption,
                job.status.value if isinstance(job.status, InstagramJobStatus) else str(job.status),
                job.attempt_count, job.claimed_by, job.claimed_at, job.lease_expires_at,
                job.container_id, job.remote_media_id, job.permalink, job.published_at,
                job.last_error, job.created_at, job.updated_at
            ))
            return True

    def get_instagram_job(self, job_id: str) -> Optional[InstagramScheduledJob]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            self._execute(cur, "SELECT * FROM instagram_scheduled_jobs WHERE job_id = ?", (job_id,))
            r = cur.fetchone()
            if not r:
                return None
            return InstagramScheduledJob(
                job_id=r["job_id"],
                week_id=r["week_id"],
                reel_id=r["reel_id"],
                scheduled_at_local=r["scheduled_at_local"],
                scheduled_at_utc=r["scheduled_at_utc"],
                timezone=r["timezone"],
                media_object_key=r["media_object_key"],
                media_sha256=r["media_sha256"],
                caption=r["caption"],
                status=InstagramJobStatus(r["status"]),
                attempt_count=r["attempt_count"],
                claimed_by=r["claimed_by"],
                claimed_at=r["claimed_at"],
                lease_expires_at=r["lease_expires_at"],
                container_id=r["container_id"],
                remote_media_id=r["remote_media_id"],
                permalink=r["permalink"],
                published_at=r["published_at"],
                last_error=r["last_error"],
                created_at=r["created_at"],
                updated_at=r["updated_at"]
            )

    def list_instagram_jobs_for_week(self, week_id: str) -> List[InstagramScheduledJob]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            self._execute(cur, "SELECT * FROM instagram_scheduled_jobs WHERE week_id = ? ORDER BY scheduled_at_local ASC", (week_id,))
            rows = cur.fetchall()
            return [
                InstagramScheduledJob(
                    job_id=r["job_id"],
                    week_id=r["week_id"],
                    reel_id=r["reel_id"],
                    scheduled_at_local=r["scheduled_at_local"],
                    scheduled_at_utc=r["scheduled_at_utc"],
                    timezone=r["timezone"],
                    media_object_key=r["media_object_key"],
                    media_sha256=r["media_sha256"],
                    caption=r["caption"],
                    status=InstagramJobStatus(r["status"]),
                    attempt_count=r["attempt_count"],
                    claimed_by=r["claimed_by"],
                    claimed_at=r["claimed_at"],
                    lease_expires_at=r["lease_expires_at"],
                    container_id=r["container_id"],
                    remote_media_id=r["remote_media_id"],
                    permalink=r["permalink"],
                    published_at=r["published_at"],
                    last_error=r["last_error"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ) for r in rows
            ]

    def claim_due_instagram_job(self, worker_id: str, prepare_cutoff_local: str) -> Optional[InstagramScheduledJob]:
        """Atomically claims the oldest due Instagram job ready for preparation/publishing."""
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lease_expires = (datetime.datetime.now() + datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        with self.get_connection() as conn:
            cur = conn.cursor()
            # Select job that is MEDIA_READY or READY_TO_PUBLISH and due
            sql_select = """
            SELECT job_id FROM instagram_scheduled_jobs
            WHERE (status IN ('MEDIA_READY', 'READY_TO_PUBLISH') OR (status = 'PREPARING' AND lease_expires_at < ?))
              AND scheduled_at_local <= ?
            ORDER BY scheduled_at_local ASC
            LIMIT 1
            """
            self._execute(cur, sql_select, (now_str, prepare_cutoff_local))
            row = cur.fetchone()
            if not row:
                return None

            job_id = row["job_id"]
            sql_update = """
            UPDATE instagram_scheduled_jobs
            SET status = 'PREPARING', claimed_by = ?, claimed_at = ?, lease_expires_at = ?, updated_at = ?
            WHERE job_id = ?
            """
            self._execute(cur, sql_update, (worker_id, now_str, lease_expires, now_str, job_id))

            if cur.rowcount > 0:
                return self.get_instagram_job(job_id)
            return None

    # =========================================================================
    # WORKER HEARTBEATS
    # =========================================================================

    def record_heartbeat(self, heartbeat: WorkerHeartbeat) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            INSERT INTO worker_heartbeats (worker_id, hostname_hash, version, capabilities_json, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                hostname_hash=excluded.hostname_hash,
                version=excluded.version,
                capabilities_json=excluded.capabilities_json,
                last_seen_at=excluded.last_seen_at;
            """
            self._execute(cur, sql, (
                heartbeat.worker_id,
                heartbeat.hostname_hash,
                heartbeat.version,
                json.dumps(heartbeat.capabilities),
                heartbeat.last_seen_at
            ))
            return True

    def get_latest_heartbeat(self) -> Optional[WorkerHeartbeat]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM worker_heartbeats ORDER BY last_seen_at DESC LIMIT 1")
            r = cur.fetchone()
            if not r:
                return None
            return WorkerHeartbeat(
                worker_id=r["worker_id"],
                hostname_hash=r["hostname_hash"],
                version=r["version"],
                capabilities=json.loads(r["capabilities_json"] or "[]"),
                last_seen_at=r["last_seen_at"]
            )

    # =========================================================================
    # NOTIFICATION LOGS
    # =========================================================================

    def has_notification_been_sent(self, payload_hash: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            self._execute(cur, "SELECT notification_id FROM notification_logs WHERE payload_hash = ?", (payload_hash,))
            return cur.fetchone() is not None

    def log_notification(self, log: NotificationLog) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            sql = """
            INSERT INTO notification_logs (notification_id, notification_type, recipient, payload_hash, sent_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(notification_id) DO NOTHING;
            """
            self._execute(cur, sql, (log.notification_id, log.notification_type, log.recipient, log.payload_hash, log.sent_at))
            return True
