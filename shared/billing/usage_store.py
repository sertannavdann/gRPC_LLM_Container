"""
Usage Store — SQLite-backed usage record persistence.

Append-only storage for run-unit consumption records with monthly
aggregation queries. Follows the SQLite pattern from shared/auth/api_keys.py.
"""
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class UsageStore:
    """SQLite-backed usage record store with WAL mode."""

    def __init__(self, db_path: str = "data/billing.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"UsageStore initialized: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_records (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    user_id TEXT,
                    thread_id TEXT,
                    tool_name TEXT NOT NULL,
                    run_units REAL NOT NULL,
                    tier TEXT DEFAULT 'standard',
                    cpu_seconds REAL DEFAULT 0.0,
                    gpu_seconds REAL DEFAULT 0.0,
                    latency_ms REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    period TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_org_period
                ON usage_records(org_id, period)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_org_created
                ON usage_records(org_id, created_at)
            """)

    def record(
        self,
        org_id: str,
        tool_name: str,
        run_units: float,
        tier: str = "standard",
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        cpu_seconds: float = 0.0,
        gpu_seconds: float = 0.0,
        latency_ms: float = 0.0,
    ) -> str:
        """
        Record a usage event. Returns the record ID.
        """
        record_id = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        period = now.strftime("%Y-%m")

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO usage_records
                   (id, org_id, user_id, thread_id, tool_name, run_units,
                    tier, cpu_seconds, gpu_seconds, latency_ms, created_at, period)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record_id, org_id, user_id, thread_id, tool_name,
                 run_units, tier, cpu_seconds, gpu_seconds, latency_ms,
                 created_at, period),
            )

        return record_id

    def get_period_total(
        self,
        org_id: str,
        period: Optional[str] = None,
    ) -> float:
        """
        Get total run units for an org in a billing period.

        Period format: 'YYYY-MM'. Defaults to current month.
        """
        if period is None:
            period = datetime.now(timezone.utc).strftime("%Y-%m")

        with self._connect() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(run_units), 0.0)
                   FROM usage_records
                   WHERE org_id = ? AND period = ?""",
                (org_id, period),
            ).fetchone()

        return float(row[0])

    def get_usage_history(
        self,
        org_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get usage records for an org, ordered by created_at DESC.

        Optional date range filters on created_at (ISO format strings).
        """
        query = "SELECT * FROM usage_records WHERE org_id = ?"
        params: list = [org_id]

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def get_usage_summary(
        self,
        org_id: str,
        period: Optional[str] = None,
    ) -> dict:
        """
        Get usage summary with breakdowns by tool and tier.

        Returns: {total_run_units, record_count, by_tool, by_tier, period}
        """
        if period is None:
            period = datetime.now(timezone.utc).strftime("%Y-%m")

        with self._connect() as conn:
            # Total and count
            row = conn.execute(
                """SELECT COALESCE(SUM(run_units), 0.0), COUNT(*)
                   FROM usage_records
                   WHERE org_id = ? AND period = ?""",
                (org_id, period),
            ).fetchone()
            total_run_units = float(row[0])
            record_count = int(row[1])

            # By tool
            tool_rows = conn.execute(
                """SELECT tool_name, COALESCE(SUM(run_units), 0.0)
                   FROM usage_records
                   WHERE org_id = ? AND period = ?
                   GROUP BY tool_name""",
                (org_id, period),
            ).fetchall()
            by_tool = {r[0]: float(r[1]) for r in tool_rows}

            # By tier
            tier_rows = conn.execute(
                """SELECT tier, COALESCE(SUM(run_units), 0.0)
                   FROM usage_records
                   WHERE org_id = ? AND period = ?
                   GROUP BY tier""",
                (org_id, period),
            ).fetchall()
            by_tier = {r[0]: float(r[1]) for r in tier_rows}

        return {
            "total_run_units": total_run_units,
            "record_count": record_count,
            "by_tool": by_tool,
            "by_tier": by_tier,
            "period": period,
        }
