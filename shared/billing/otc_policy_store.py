"""
OTC Policy Store — SQLite-backed OTC policy checkpoint and trajectory storage.

Provides checkpoint storage and trajectory logging for Optimal Tool Calls (OTC)
policy learning. Follows the UsageStore WAL-mode SQLite pattern.

Schema:
- intent_classes: discovered intent clusters
- module_sets: fingerprints of available module combinations
- policy_checkpoints: optimal_n estimates per (intent, module_set) pair
- trajectory_log: append-only execution traces
- reward_events: scored trajectories (observation → evaluation separation)
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OTCPolicyStore:
    """SQLite-backed OTC policy checkpoint and trajectory storage with WAL mode."""

    def __init__(self, db_path: str = "data/otc_policy.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"OTCPolicyStore initialized: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_db(self) -> None:
        """Create all 5 tables + 4 indexes from schema."""
        with self._connect() as conn:
            # 1. Intent classes
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intent_classes (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_hash     TEXT    NOT NULL UNIQUE,
                    canonical_label TEXT    NOT NULL,
                    first_seen_at   TEXT    NOT NULL,
                    example_count   INTEGER NOT NULL DEFAULT 0
                )
            """)

            # 2. Module sets
            conn.execute("""
                CREATE TABLE IF NOT EXISTS module_sets (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    set_hash        TEXT    NOT NULL UNIQUE,
                    module_ids      TEXT    NOT NULL,
                    cardinality     INTEGER NOT NULL,
                    first_seen_at   TEXT    NOT NULL
                )
            """)

            # 3. Policy checkpoints
            conn.execute("""
                CREATE TABLE IF NOT EXISTS policy_checkpoints (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_class_id      INTEGER NOT NULL REFERENCES intent_classes(id),
                    module_set_id        INTEGER NOT NULL REFERENCES module_sets(id),
                    optimal_n            REAL    NOT NULL,
                    smooth_c             REAL    NOT NULL DEFAULT 2.0,
                    arm_weights          BLOB    NOT NULL,
                    confidence           REAL    NOT NULL DEFAULT 0.0,
                    sample_count         INTEGER NOT NULL DEFAULT 0,
                    promoted_at          TEXT    NOT NULL,
                    orchestrator_version TEXT    NOT NULL,
                    UNIQUE(intent_class_id, module_set_id)
                )
            """)

            # 4. Trajectory log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trajectory_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts              TEXT    NOT NULL,
                    intent_class_id INTEGER NOT NULL REFERENCES intent_classes(id),
                    module_set_id   INTEGER NOT NULL REFERENCES module_sets(id),
                    tool_calls      INTEGER NOT NULL,
                    run_units       REAL    NOT NULL,
                    latency_ms      INTEGER NOT NULL,
                    success         INTEGER NOT NULL DEFAULT 0,
                    reward          REAL,
                    context_blob    BLOB
                )
            """)

            # 5. Reward events
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reward_events (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    trajectory_id  INTEGER NOT NULL REFERENCES trajectory_log(id),
                    r_correctness  REAL    NOT NULL,
                    r_tool         REAL    NOT NULL,
                    r_cost         REAL    NOT NULL,
                    r_composite    REAL    NOT NULL,
                    scored_at      TEXT    NOT NULL,
                    scorer_version TEXT    NOT NULL
                )
            """)

            # Indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_traj_intent_module
                ON trajectory_log(intent_class_id, module_set_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_traj_ts
                ON trajectory_log(ts)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_policy_lookup
                ON policy_checkpoints(intent_class_id, module_set_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reward_traj
                ON reward_events(trajectory_id)
            """)

    def upsert_intent_class(self, intent_hash: str, canonical_label: str) -> int:
        """
        Upsert intent class. Returns id. Increments example_count on conflict.

        Args:
            intent_hash: SHA-256 hash of canonical intent
            canonical_label: human-readable intent label

        Returns:
            intent_class_id
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO intent_classes (intent_hash, canonical_label, first_seen_at, example_count)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(intent_hash) DO UPDATE SET example_count = example_count + 1""",
                (intent_hash, canonical_label, now),
            )
            row = conn.execute(
                "SELECT id FROM intent_classes WHERE intent_hash = ?",
                (intent_hash,),
            ).fetchone()

        return int(row[0])

    def upsert_module_set(self, set_hash: str, module_ids: list[str], cardinality: int) -> int:
        """
        Upsert module set. Returns id. Idempotent on conflict.

        Args:
            set_hash: SHA-256 hash of sorted module IDs
            module_ids: list of module identifiers
            cardinality: len(module_ids)

        Returns:
            module_set_id
        """
        now = datetime.now(timezone.utc).isoformat()
        module_ids_json = json.dumps(module_ids)

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO module_sets (set_hash, module_ids, cardinality, first_seen_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(set_hash) DO NOTHING""",
                (set_hash, module_ids_json, cardinality, now),
            )
            row = conn.execute(
                "SELECT id FROM module_sets WHERE set_hash = ?",
                (set_hash,),
            ).fetchone()

        return int(row[0])

    def upsert_policy_checkpoint(
        self,
        intent_class_id: int,
        module_set_id: int,
        optimal_n: float,
        arm_weights: bytes,
        confidence: float,
        sample_count: int,
        orchestrator_version: str,
        smooth_c: float = 2.0,
    ) -> int:
        """
        Upsert policy checkpoint. Returns id. Updates on conflict.

        Args:
            intent_class_id: reference to intent_classes
            module_set_id: reference to module_sets
            optimal_n: estimated optimal tool call count
            arm_weights: serialized policy weights (numpy/msgpack)
            confidence: UCB confidence bound
            sample_count: number of trajectories used
            orchestrator_version: git SHA or semver
            smooth_c: OTC decay constant

        Returns:
            policy_checkpoint_id
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO policy_checkpoints
                   (intent_class_id, module_set_id, optimal_n, smooth_c, arm_weights,
                    confidence, sample_count, promoted_at, orchestrator_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(intent_class_id, module_set_id) DO UPDATE SET
                       optimal_n = excluded.optimal_n,
                       smooth_c = excluded.smooth_c,
                       arm_weights = excluded.arm_weights,
                       confidence = excluded.confidence,
                       sample_count = excluded.sample_count,
                       promoted_at = excluded.promoted_at,
                       orchestrator_version = excluded.orchestrator_version""",
                (intent_class_id, module_set_id, optimal_n, smooth_c, arm_weights,
                 confidence, sample_count, now, orchestrator_version),
            )
            row = conn.execute(
                """SELECT id FROM policy_checkpoints
                   WHERE intent_class_id = ? AND module_set_id = ?""",
                (intent_class_id, module_set_id),
            ).fetchone()

        return int(row[0])

    def log_trajectory(
        self,
        intent_class_id: int,
        module_set_id: int,
        tool_calls: int,
        run_units: float,
        latency_ms: int,
        success: bool,
        context_blob: Optional[bytes] = None,
    ) -> int:
        """
        Log trajectory. Returns trajectory_id.

        Args:
            intent_class_id: reference to intent_classes
            module_set_id: reference to module_sets
            tool_calls: actual tool call count (m)
            run_units: metered run units consumed
            latency_ms: request latency
            success: contract test result
            context_blob: optional serialized context

        Returns:
            trajectory_id
        """
        now = datetime.now(timezone.utc).isoformat()
        success_int = 1 if success else 0

        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO trajectory_log
                   (ts, intent_class_id, module_set_id, tool_calls, run_units,
                    latency_ms, success, context_blob)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (now, intent_class_id, module_set_id, tool_calls, run_units,
                 latency_ms, success_int, context_blob),
            )

        return int(cursor.lastrowid)

    def score_trajectory(
        self,
        trajectory_id: int,
        r_correctness: float,
        r_tool: float,
        r_cost: float,
        r_composite: float,
        scorer_version: str,
    ) -> int:
        """
        Score trajectory. Inserts reward_event and updates trajectory_log.reward.

        Args:
            trajectory_id: reference to trajectory_log
            r_correctness: correctness reward component
            r_tool: tool efficiency reward component
            r_cost: cost efficiency reward component
            r_composite: composite reward
            scorer_version: reward function version tag

        Returns:
            reward_event_id
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            # Insert reward event
            cursor = conn.execute(
                """INSERT INTO reward_events
                   (trajectory_id, r_correctness, r_tool, r_cost, r_composite,
                    scored_at, scorer_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (trajectory_id, r_correctness, r_tool, r_cost, r_composite,
                 now, scorer_version),
            )

            # Update trajectory_log with reward
            conn.execute(
                "UPDATE trajectory_log SET reward = ? WHERE id = ?",
                (r_composite, trajectory_id),
            )

        return int(cursor.lastrowid)

    def lookup_policy(
        self,
        intent_class_id: int,
        module_set_id: int,
    ) -> Optional[dict]:
        """
        Lookup policy checkpoint for (intent, module_set) pair.

        Returns:
            Policy checkpoint dict or None
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM policy_checkpoints
                   WHERE intent_class_id = ? AND module_set_id = ?""",
                (intent_class_id, module_set_id),
            ).fetchone()

        return dict(row) if row else None

    def get_trajectories(
        self,
        intent_class_id: Optional[int] = None,
        module_set_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get trajectories with optional filters.

        Args:
            intent_class_id: filter by intent class
            module_set_id: filter by module set
            limit: max number of results

        Returns:
            List of trajectory dicts
        """
        query = "SELECT * FROM trajectory_log WHERE 1=1"
        params: list = []

        if intent_class_id is not None:
            query += " AND intent_class_id = ?"
            params.append(intent_class_id)
        if module_set_id is not None:
            query += " AND module_set_id = ?"
            params.append(module_set_id)

        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]
