
-- =============================================================
-- NEXUS OTC Policy Storage Schema
-- Minimal, contextual, migration-ready (SQLite → PostgreSQL)
-- =============================================================

-- 1. INTENT CLASSES
-- Low-cardinality lookup. One row per discovered intent cluster.
-- intent_hash = SHA-256 of canonical intent string (deterministic dedup).
CREATE TABLE intent_classes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,   -- SERIAL in PG
    intent_hash     TEXT    NOT NULL UNIQUE,
    canonical_label TEXT    NOT NULL,
    first_seen_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    example_count   INTEGER NOT NULL DEFAULT 0
);

-- 2. MODULE SETS
-- Fingerprint of the *set* of modules available at decision time.
-- set_hash = SHA-256 of sorted module IDs → deterministic identity.
CREATE TABLE module_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    set_hash        TEXT    NOT NULL UNIQUE,
    module_ids      TEXT    NOT NULL,             -- JSON array, e.g. ["weather","clash_royale"]
    cardinality     INTEGER NOT NULL,             -- len(module_ids)
    first_seen_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- 3. POLICY CHECKPOINTS (the "weights" you save per rebuild)
-- One row per (intent_class, module_set) pair, updated on promotion.
-- This IS the lookup table: given (intent, modules) → optimal_n + policy params.
CREATE TABLE policy_checkpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_class_id INTEGER NOT NULL REFERENCES intent_classes(id),
    module_set_id   INTEGER NOT NULL REFERENCES module_sets(id),
    optimal_n       REAL    NOT NULL,             -- estimated optimal tool-call count
    smooth_c        REAL    NOT NULL DEFAULT 2.0, -- OTC reward decay constant
    arm_weights     BLOB    NOT NULL,             -- compact: numpy f16 array or msgpack
    confidence      REAL    NOT NULL DEFAULT 0.0, -- UCB confidence bound / sample count
    sample_count    INTEGER NOT NULL DEFAULT 0,
    promoted_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    orchestrator_version TEXT NOT NULL,           -- git SHA or semver of the build
    UNIQUE(intent_class_id, module_set_id)
);

-- 4. TRAJECTORY LOG (append-only, feeds offline training)
-- Each row = one completed request trajectory.
-- Minimal columns; extensible context in the BLOB.
CREATE TABLE trajectory_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    intent_class_id INTEGER NOT NULL REFERENCES intent_classes(id),
    module_set_id   INTEGER NOT NULL REFERENCES module_sets(id),
    tool_calls      INTEGER NOT NULL,             -- m: actual tool-call count
    run_units       REAL    NOT NULL,             -- from Phase 2 metering
    latency_ms      INTEGER NOT NULL,
    success         INTEGER NOT NULL DEFAULT 0,   -- 1 = contract tests passed
    reward          REAL,                          -- computed OTC reward (nullable until scored)
    context_blob    BLOB                           -- msgpack: {module_call_sequence, token_counts, ...}
);

-- 5. REWARD EVENTS (maps Phase 2 run-unit metering → OTC signal)
-- Derived table; can be materialized view in PG.
-- Separates "what happened" (trajectory_log) from "how we scored it" (reward_events).
CREATE TABLE reward_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trajectory_id   INTEGER NOT NULL REFERENCES trajectory_log(id),
    r_correctness   REAL    NOT NULL,             -- 0.0 or 1.0 (contract pass/fail)
    r_tool          REAL    NOT NULL,             -- OTC tool reward: sin(f(m,n)*pi/(2n))
    r_cost          REAL    NOT NULL,             -- normalized run-unit penalty
    r_composite     REAL    NOT NULL,             -- alpha * r_tool * r_correctness - beta * r_cost
    scored_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    scorer_version  TEXT    NOT NULL              -- reward function version tag
);

-- 6. INDEXES (SQLite-compatible, translate directly to PG)
CREATE INDEX idx_traj_intent_module ON trajectory_log(intent_class_id, module_set_id);
CREATE INDEX idx_traj_ts            ON trajectory_log(ts);
CREATE INDEX idx_policy_lookup      ON policy_checkpoints(intent_class_id, module_set_id);
CREATE INDEX idx_reward_traj        ON reward_events(trajectory_id);

-- =============================================================
-- MIGRATION NOTES (SQLite → PostgreSQL)
-- =============================================================
-- • INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL / BIGSERIAL
-- • TEXT timestamps → TIMESTAMPTZ (with DEFAULT now())
-- • BLOB → BYTEA
-- • TEXT JSON arrays → JSONB (enables GIN index on module_ids)
-- • Add BRIN index on trajectory_log(ts) for time-range scans
-- • Add hypertable (TimescaleDB) on trajectory_log if >100M rows
-- • reward_events can become a materialized view refreshed on scoring
-- =============================================================
