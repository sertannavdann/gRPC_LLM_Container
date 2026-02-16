"""
Unit tests for OTC policy store.

Tests all CRUD operations, upsert semantics, and query filters
for the OTC policy storage layer.
"""
import pytest
from shared.billing.otc_policy_store import OTCPolicyStore


@pytest.fixture
def store(tmp_path):
    """Create a temporary OTCPolicyStore for testing."""
    db_path = tmp_path / "test_otc.db"
    return OTCPolicyStore(db_path=str(db_path))


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""

    def test_init_creates_all_tables(self, store):
        """Verify all 5 tables are created."""
        with store._connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t[0] for t in tables]

            assert "intent_classes" in table_names
            assert "module_sets" in table_names
            assert "policy_checkpoints" in table_names
            assert "trajectory_log" in table_names
            assert "reward_events" in table_names

    def test_init_creates_all_indexes(self, store):
        """Verify all 4 indexes are created."""
        with store._connect() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
            index_names = [i[0] for i in indexes]

            assert "idx_traj_intent_module" in index_names
            assert "idx_traj_ts" in index_names
            assert "idx_policy_lookup" in index_names
            assert "idx_reward_traj" in index_names

    def test_wal_mode_enabled(self, store):
        """Verify WAL mode is enabled."""
        with store._connect() as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0].lower() == "wal"


class TestIntentClassOperations:
    """Test intent_classes CRUD operations."""

    def test_upsert_intent_class_creates(self, store):
        """First upsert creates new intent class."""
        intent_id = store.upsert_intent_class(
            intent_hash="hash123",
            canonical_label="weather_check",
        )
        assert intent_id > 0

    def test_upsert_intent_class_increments_count(self, store):
        """Re-upsert increments example_count."""
        intent_hash = "hash456"

        # First insert
        id1 = store.upsert_intent_class(intent_hash, "calendar_query")

        # Second insert (conflict)
        id2 = store.upsert_intent_class(intent_hash, "calendar_query")

        assert id1 == id2, "Should return same ID"

        # Check example_count
        with store._connect() as conn:
            row = conn.execute(
                "SELECT example_count FROM intent_classes WHERE id = ?",
                (id1,),
            ).fetchone()
            assert row[0] == 2

    def test_upsert_intent_class_fields_stored(self, store):
        """Verify all fields are stored correctly."""
        intent_id = store.upsert_intent_class(
            intent_hash="hash789",
            canonical_label="gaming_stats",
        )

        with store._connect() as conn:
            row = conn.execute(
                "SELECT intent_hash, canonical_label, first_seen_at FROM intent_classes WHERE id = ?",
                (intent_id,),
            ).fetchone()

            assert row[0] == "hash789"
            assert row[1] == "gaming_stats"
            assert row[2] is not None  # timestamp


class TestModuleSetOperations:
    """Test module_sets CRUD operations."""

    def test_upsert_module_set_creates(self, store):
        """First upsert creates new module set."""
        set_id = store.upsert_module_set(
            set_hash="set123",
            module_ids=["weather", "calendar"],
            cardinality=2,
        )
        assert set_id > 0

    def test_upsert_module_set_idempotent(self, store):
        """Re-upsert with same hash is idempotent."""
        set_hash = "set456"

        id1 = store.upsert_module_set(set_hash, ["gaming"], 1)
        id2 = store.upsert_module_set(set_hash, ["gaming"], 1)

        assert id1 == id2

    def test_upsert_module_set_stores_json(self, store):
        """Verify module_ids stored as JSON."""
        set_id = store.upsert_module_set(
            set_hash="set789",
            module_ids=["weather", "gaming", "finance"],
            cardinality=3,
        )

        with store._connect() as conn:
            row = conn.execute(
                "SELECT module_ids, cardinality FROM module_sets WHERE id = ?",
                (set_id,),
            ).fetchone()

            import json
            module_ids = json.loads(row[0])
            assert module_ids == ["weather", "gaming", "finance"]
            assert row[1] == 3


class TestPolicyCheckpointOperations:
    """Test policy_checkpoints CRUD operations."""

    def test_upsert_policy_checkpoint_creates(self, store):
        """First upsert creates new checkpoint."""
        intent_id = store.upsert_intent_class("intent1", "test")
        set_id = store.upsert_module_set("set1", ["mod1"], 1)

        checkpoint_id = store.upsert_policy_checkpoint(
            intent_class_id=intent_id,
            module_set_id=set_id,
            optimal_n=3.5,
            arm_weights=b"\x00\x01\x02\x03",
            confidence=0.85,
            sample_count=100,
            orchestrator_version="v1.0.0",
            smooth_c=2.0,
        )
        assert checkpoint_id > 0

    def test_upsert_policy_checkpoint_updates_on_conflict(self, store):
        """Re-upsert updates optimal_n and other fields."""
        intent_id = store.upsert_intent_class("intent2", "test")
        set_id = store.upsert_module_set("set2", ["mod2"], 1)

        # First insert
        id1 = store.upsert_policy_checkpoint(
            intent_id, set_id, 3.0, b"\x01", 0.5, 50, "v1.0.0"
        )

        # Update
        id2 = store.upsert_policy_checkpoint(
            intent_id, set_id, 4.0, b"\x02", 0.9, 200, "v1.1.0"
        )

        assert id1 == id2

        # Verify updated
        with store._connect() as conn:
            row = conn.execute(
                "SELECT optimal_n, sample_count FROM policy_checkpoints WHERE id = ?",
                (id1,),
            ).fetchone()
            assert row[0] == 4.0
            assert row[1] == 200


class TestTrajectoryOperations:
    """Test trajectory_log CRUD operations."""

    def test_log_trajectory_creates(self, store):
        """Log trajectory returns incrementing IDs."""
        intent_id = store.upsert_intent_class("intent3", "test")
        set_id = store.upsert_module_set("set3", ["mod3"], 1)

        traj_id = store.log_trajectory(
            intent_class_id=intent_id,
            module_set_id=set_id,
            tool_calls=5,
            run_units=1.2,
            latency_ms=250,
            success=True,
            context_blob=b"context",
        )
        assert traj_id > 0

    def test_log_trajectory_stores_all_fields(self, store):
        """Verify all trajectory fields stored correctly."""
        intent_id = store.upsert_intent_class("intent4", "test")
        set_id = store.upsert_module_set("set4", ["mod4"], 1)

        traj_id = store.log_trajectory(
            intent_id, set_id, 3, 0.8, 150, True, b"blob"
        )

        with store._connect() as conn:
            row = conn.execute(
                """SELECT tool_calls, run_units, latency_ms, success, context_blob
                   FROM trajectory_log WHERE id = ?""",
                (traj_id,),
            ).fetchone()

            assert row[0] == 3
            assert row[1] == 0.8
            assert row[2] == 150
            assert row[3] == 1  # success stored as int
            assert row[4] == b"blob"

    def test_log_trajectory_increments_ids(self, store):
        """Multiple logs return incrementing IDs."""
        intent_id = store.upsert_intent_class("intent5", "test")
        set_id = store.upsert_module_set("set5", ["mod5"], 1)

        id1 = store.log_trajectory(intent_id, set_id, 1, 0.1, 100, True)
        id2 = store.log_trajectory(intent_id, set_id, 2, 0.2, 200, True)
        id3 = store.log_trajectory(intent_id, set_id, 3, 0.3, 300, False)

        assert id2 == id1 + 1
        assert id3 == id2 + 1


class TestRewardOperations:
    """Test reward_events and trajectory scoring."""

    def test_score_trajectory_creates_reward_event(self, store):
        """Score trajectory inserts reward event."""
        intent_id = store.upsert_intent_class("intent6", "test")
        set_id = store.upsert_module_set("set6", ["mod6"], 1)
        traj_id = store.log_trajectory(intent_id, set_id, 3, 0.9, 200, True)

        reward_id = store.score_trajectory(
            trajectory_id=traj_id,
            r_correctness=1.0,
            r_tool=0.95,
            r_cost=0.18,
            r_composite=0.932,
            scorer_version="v1.0.0",
        )
        assert reward_id > 0

    def test_score_trajectory_updates_trajectory_reward(self, store):
        """Scoring updates trajectory_log.reward field."""
        intent_id = store.upsert_intent_class("intent7", "test")
        set_id = store.upsert_module_set("set7", ["mod7"], 1)
        traj_id = store.log_trajectory(intent_id, set_id, 3, 0.9, 200, True)

        # Initial reward should be NULL
        with store._connect() as conn:
            row = conn.execute(
                "SELECT reward FROM trajectory_log WHERE id = ?",
                (traj_id,),
            ).fetchone()
            assert row[0] is None

        # Score it
        store.score_trajectory(traj_id, 1.0, 0.95, 0.18, 0.932, "v1.0.0")

        # Reward should be updated
        with store._connect() as conn:
            row = conn.execute(
                "SELECT reward FROM trajectory_log WHERE id = ?",
                (traj_id,),
            ).fetchone()
            assert row[0] == 0.932


class TestQueryOperations:
    """Test query methods."""

    def test_lookup_policy_returns_checkpoint(self, store):
        """lookup_policy returns checkpoint dict."""
        intent_id = store.upsert_intent_class("intent8", "test")
        set_id = store.upsert_module_set("set8", ["mod8"], 1)
        store.upsert_policy_checkpoint(intent_id, set_id, 3.0, b"\x01", 0.5, 50, "v1.0.0")

        policy = store.lookup_policy(intent_id, set_id)

        assert policy is not None
        assert policy["optimal_n"] == 3.0
        assert policy["sample_count"] == 50

    def test_lookup_policy_returns_none_for_missing(self, store):
        """lookup_policy returns None for non-existent pair."""
        policy = store.lookup_policy(intent_class_id=999, module_set_id=999)
        assert policy is None

    def test_get_trajectories_returns_list(self, store):
        """get_trajectories returns list of dicts."""
        intent_id = store.upsert_intent_class("intent9", "test")
        set_id = store.upsert_module_set("set9", ["mod9"], 1)

        store.log_trajectory(intent_id, set_id, 1, 0.1, 100, True)
        store.log_trajectory(intent_id, set_id, 2, 0.2, 200, True)

        trajectories = store.get_trajectories(limit=10)

        assert len(trajectories) == 2
        assert all(isinstance(t, dict) for t in trajectories)

    def test_get_trajectories_filters_by_intent(self, store):
        """get_trajectories filters by intent_class_id."""
        intent_id1 = store.upsert_intent_class("intent10", "test1")
        intent_id2 = store.upsert_intent_class("intent11", "test2")
        set_id = store.upsert_module_set("set10", ["mod10"], 1)

        store.log_trajectory(intent_id1, set_id, 1, 0.1, 100, True)
        store.log_trajectory(intent_id2, set_id, 2, 0.2, 200, True)

        trajectories = store.get_trajectories(intent_class_id=intent_id1)

        assert len(trajectories) == 1
        assert trajectories[0]["intent_class_id"] == intent_id1

    def test_get_trajectories_filters_by_module_set(self, store):
        """get_trajectories filters by module_set_id."""
        intent_id = store.upsert_intent_class("intent12", "test")
        set_id1 = store.upsert_module_set("set11", ["mod11"], 1)
        set_id2 = store.upsert_module_set("set12", ["mod12"], 1)

        store.log_trajectory(intent_id, set_id1, 1, 0.1, 100, True)
        store.log_trajectory(intent_id, set_id2, 2, 0.2, 200, True)

        trajectories = store.get_trajectories(module_set_id=set_id1)

        assert len(trajectories) == 1
        assert trajectories[0]["module_set_id"] == set_id1

    def test_get_trajectories_respects_limit(self, store):
        """get_trajectories respects limit parameter."""
        intent_id = store.upsert_intent_class("intent13", "test")
        set_id = store.upsert_module_set("set13", ["mod13"], 1)

        # Create 10 trajectories
        for i in range(10):
            store.log_trajectory(intent_id, set_id, i, 0.1 * i, 100 + i, True)

        trajectories = store.get_trajectories(limit=5)

        assert len(trajectories) == 5

    def test_get_trajectories_orders_by_ts_desc(self, store):
        """get_trajectories orders by timestamp descending."""
        intent_id = store.upsert_intent_class("intent14", "test")
        set_id = store.upsert_module_set("set14", ["mod14"], 1)

        # Create multiple trajectories with slight delays
        id1 = store.log_trajectory(intent_id, set_id, 1, 0.1, 100, True)
        id2 = store.log_trajectory(intent_id, set_id, 2, 0.2, 200, True)
        id3 = store.log_trajectory(intent_id, set_id, 3, 0.3, 300, True)

        trajectories = store.get_trajectories(limit=10)

        # Most recent should be first
        assert trajectories[0]["id"] == id3
        assert trajectories[1]["id"] == id2
        assert trajectories[2]["id"] == id1
