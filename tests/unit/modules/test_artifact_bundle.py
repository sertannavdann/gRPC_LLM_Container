"""Unit tests for artifact bundle system."""
import pytest
import tempfile
import json
from pathlib import Path
from shared.modules.artifacts import (
    ArtifactBundleBuilder,
    ArtifactIndex,
    FileArtifact,
    verify_bundle_hash
)


@pytest.fixture
def sample_files():
    """Sample files for bundle testing."""
    return {
        "manifest.json": '{"module_id": "weather/openweather", "version": "1.0.0"}',
        "adapter.py": "class WeatherAdapter:\n    pass\n",
        "test_adapter.py": "def test_weather():\n    assert True\n"
    }


@pytest.fixture
def empty_files():
    """Empty files dictionary."""
    return {}


class TestFileArtifact:
    """Tests for FileArtifact dataclass."""

    def test_file_artifact_creation(self):
        """Test that FileArtifact can be created."""
        artifact = FileArtifact(
            path="test.py",
            size=100,
            sha256="abc123"
        )
        assert artifact.path == "test.py"
        assert artifact.size == 100
        assert artifact.sha256 == "abc123"

    def test_file_artifact_to_dict(self):
        """Test serialization to dictionary."""
        artifact = FileArtifact(
            path="test.py",
            size=100,
            sha256="abc123"
        )
        result = artifact.to_dict()
        assert result["path"] == "test.py"
        assert result["size"] == 100
        assert result["sha256"] == "abc123"


class TestArtifactIndex:
    """Tests for ArtifactIndex dataclass."""

    def test_artifact_index_creation(self):
        """Test that ArtifactIndex can be created."""
        index = ArtifactIndex(
            job_id="job-123",
            attempt_id=1,
            bundle_sha256="hash123",
            files=[],
            created_at="2026-02-15T00:00:00Z"
        )
        assert index.job_id == "job-123"
        assert index.attempt_id == 1
        assert index.bundle_sha256 == "hash123"

    def test_artifact_index_serialization_round_trip(self):
        """Test that ArtifactIndex can be serialized and deserialized."""
        original = ArtifactIndex(
            job_id="job-456",
            attempt_id=2,
            bundle_sha256="hash456",
            files=[
                FileArtifact(path="test.py", size=50, sha256="file-hash-1")
            ],
            created_at="2026-02-15T01:00:00Z",
            module_id="weather/openweather",
            stage="adapter"
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = ArtifactIndex.from_dict(data)

        assert restored.job_id == original.job_id
        assert restored.attempt_id == original.attempt_id
        assert restored.bundle_sha256 == original.bundle_sha256
        assert len(restored.files) == len(original.files)
        assert restored.files[0].path == original.files[0].path
        assert restored.module_id == original.module_id
        assert restored.stage == original.stage


class TestArtifactBundleBuilder:
    """Tests for ArtifactBundleBuilder."""

    def test_hash_content_deterministic(self):
        """Test that hash_content produces same hash for same content."""
        content = "Hello, World!"
        hash1 = ArtifactBundleBuilder.hash_content(content)
        hash2 = ArtifactBundleBuilder.hash_content(content)
        assert hash1 == hash2

    def test_hash_content_different_for_different_content(self):
        """Test that different content produces different hashes."""
        hash1 = ArtifactBundleBuilder.hash_content("content1")
        hash2 = ArtifactBundleBuilder.hash_content("content2")
        assert hash1 != hash2

    def test_build_from_dict_creates_index(self, sample_files):
        """Test that build_from_dict creates an ArtifactIndex."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test-job",
            attempt_id=1,
            module_id="weather/openweather",
            stage="initial"
        )

        assert index.job_id == "test-job"
        assert index.attempt_id == 1
        assert index.module_id == "weather/openweather"
        assert index.stage == "initial"
        assert len(index.files) == 3
        assert index.bundle_sha256 is not None

    def test_build_from_dict_file_order_determinism(self, sample_files):
        """Test that file order doesn't affect bundle hash."""
        # Build with different insertion order
        files_order1 = {
            "adapter.py": sample_files["adapter.py"],
            "manifest.json": sample_files["manifest.json"],
            "test_adapter.py": sample_files["test_adapter.py"]
        }

        files_order2 = {
            "test_adapter.py": sample_files["test_adapter.py"],
            "adapter.py": sample_files["adapter.py"],
            "manifest.json": sample_files["manifest.json"]
        }

        index1 = ArtifactBundleBuilder.build_from_dict(
            files=files_order1,
            job_id="test",
            attempt_id=1
        )

        index2 = ArtifactBundleBuilder.build_from_dict(
            files=files_order2,
            job_id="test",
            attempt_id=1
        )

        # Bundle hashes should be identical
        assert index1.bundle_sha256 == index2.bundle_sha256

    def test_build_from_dict_files_sorted_in_index(self, sample_files):
        """Test that files are sorted by path in the index."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        paths = [f.path for f in index.files]
        assert paths == sorted(paths)

    def test_self_check_passes_for_identical_content(self, sample_files):
        """Test that self_check returns True for identical inputs."""
        result = ArtifactBundleBuilder.self_check(sample_files)
        assert result is True

    def test_self_check_determinism_proof(self):
        """Test that bundle hash is stable for identical content across multiple builds."""
        files = {
            "file1.txt": "content 1",
            "file2.txt": "content 2"
        }

        hashes = set()
        for i in range(10):
            bundle = ArtifactBundleBuilder.build_from_dict(
                files=files,
                job_id=f"job-{i}",
                attempt_id=i
            )
            hashes.add(bundle.bundle_sha256)

        # All hashes should be identical
        assert len(hashes) == 1

    def test_different_content_produces_different_hash(self, sample_files):
        """Test that different content produces different bundle hash."""
        index1 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        modified_files = sample_files.copy()
        modified_files["adapter.py"] = "class ModifiedAdapter:\n    pass\n"

        index2 = ArtifactBundleBuilder.build_from_dict(
            files=modified_files,
            job_id="test",
            attempt_id=1
        )

        assert index1.bundle_sha256 != index2.bundle_sha256

    def test_file_sizes_recorded(self, sample_files):
        """Test that file sizes are correctly recorded."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        for artifact in index.files:
            expected_size = len(sample_files[artifact.path].encode('utf-8'))
            assert artifact.size == expected_size

    def test_file_hashes_unique(self, sample_files):
        """Test that each file has a unique hash."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        hashes = [f.sha256 for f in index.files]
        assert len(hashes) == len(set(hashes))  # All unique

    def test_empty_files_creates_valid_bundle(self, empty_files):
        """Test that empty file set creates valid bundle."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=empty_files,
            job_id="test",
            attempt_id=1
        )

        assert len(index.files) == 0
        assert index.bundle_sha256 is not None


class TestBuildFromDirectory:
    """Tests for build_from_directory method."""

    def test_build_from_directory_success(self):
        """Test building bundle from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create test files
            (tmpdir_path / "file1.txt").write_text("content 1")
            (tmpdir_path / "file2.txt").write_text("content 2")

            index = ArtifactBundleBuilder.build_from_directory(
                directory=tmpdir_path,
                job_id="test",
                attempt_id=1
            )

            assert len(index.files) == 2
            paths = {f.path for f in index.files}
            assert "file1.txt" in paths
            assert "file2.txt" in paths

    def test_build_from_directory_with_subdirs(self):
        """Test that subdirectories are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create nested structure
            (tmpdir_path / "root.txt").write_text("root")
            (tmpdir_path / "subdir").mkdir()
            (tmpdir_path / "subdir" / "nested.txt").write_text("nested")

            index = ArtifactBundleBuilder.build_from_directory(
                directory=tmpdir_path,
                job_id="test",
                attempt_id=1
            )

            paths = {f.path for f in index.files}
            assert "root.txt" in paths
            assert "subdir/nested.txt" in paths or "subdir\\nested.txt" in paths  # Windows compat

    def test_build_from_nonexistent_directory(self):
        """Test that nonexistent directory raises error."""
        with pytest.raises(ValueError, match="does not exist"):
            ArtifactBundleBuilder.build_from_directory(
                directory=Path("/nonexistent/path"),
                job_id="test",
                attempt_id=1
            )


class TestDiffBundles:
    """Tests for bundle comparison."""

    def test_diff_identical_bundles(self, sample_files):
        """Test diff of identical bundles."""
        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test1",
            attempt_id=1
        )

        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test2",
            attempt_id=1
        )

        diff = ArtifactBundleBuilder.diff_bundles(bundle1, bundle2)

        assert diff["identical"] is True
        assert len(diff["added"]) == 0
        assert len(diff["deleted"]) == 0
        assert len(diff["changed"]) == 0
        assert len(diff["unchanged"]) == 3

    def test_diff_added_files(self, sample_files):
        """Test detection of added files."""
        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        files_with_addition = sample_files.copy()
        files_with_addition["new_file.py"] = "new content"

        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=files_with_addition,
            job_id="test",
            attempt_id=2
        )

        diff = ArtifactBundleBuilder.diff_bundles(bundle1, bundle2)

        assert diff["identical"] is False
        assert "new_file.py" in diff["added"]
        assert len(diff["deleted"]) == 0
        assert len(diff["changed"]) == 0

    def test_diff_deleted_files(self, sample_files):
        """Test detection of deleted files."""
        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        files_with_deletion = sample_files.copy()
        del files_with_deletion["test_adapter.py"]

        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=files_with_deletion,
            job_id="test",
            attempt_id=2
        )

        diff = ArtifactBundleBuilder.diff_bundles(bundle1, bundle2)

        assert diff["identical"] is False
        assert "test_adapter.py" in diff["deleted"]
        assert len(diff["added"]) == 0
        assert len(diff["changed"]) == 0

    def test_diff_changed_files(self, sample_files):
        """Test detection of changed files."""
        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        files_with_changes = sample_files.copy()
        files_with_changes["adapter.py"] = "class ModifiedAdapter:\n    pass\n"

        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=files_with_changes,
            job_id="test",
            attempt_id=2
        )

        diff = ArtifactBundleBuilder.diff_bundles(bundle1, bundle2)

        assert diff["identical"] is False
        assert "adapter.py" in diff["changed"]
        assert len(diff["added"]) == 0
        assert len(diff["deleted"]) == 0

    def test_diff_complex_changes(self, sample_files):
        """Test diff with multiple types of changes."""
        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        files_changed = {
            "manifest.json": sample_files["manifest.json"],  # Unchanged
            "adapter.py": "modified content",  # Changed
            "new_file.py": "new"  # Added
            # test_adapter.py deleted
        }

        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=files_changed,
            job_id="test",
            attempt_id=2
        )

        diff = ArtifactBundleBuilder.diff_bundles(bundle1, bundle2)

        assert diff["identical"] is False
        assert "new_file.py" in diff["added"]
        assert "test_adapter.py" in diff["deleted"]
        assert "adapter.py" in diff["changed"]
        assert "manifest.json" in diff["unchanged"]


class TestVerifyBundleHash:
    """Tests for bundle hash verification."""

    def test_verify_bundle_hash_success(self, sample_files):
        """Test that valid bundle hash is verified."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        result = verify_bundle_hash(index, sample_files)
        assert result is True

    def test_verify_bundle_hash_failure(self, sample_files):
        """Test that invalid bundle hash is detected."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        # Modify the bundle hash
        index.bundle_sha256 = "invalid_hash"

        result = verify_bundle_hash(index, sample_files)
        assert result is False

    def test_verify_bundle_hash_with_modified_content(self, sample_files):
        """Test that modified content fails verification."""
        index = ArtifactBundleBuilder.build_from_dict(
            files=sample_files,
            job_id="test",
            attempt_id=1
        )

        # Modify the files
        modified_files = sample_files.copy()
        modified_files["adapter.py"] = "modified"

        result = verify_bundle_hash(index, modified_files)
        assert result is False
