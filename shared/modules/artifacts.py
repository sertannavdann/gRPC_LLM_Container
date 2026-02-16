"""
Content-addressed artifact bundle system for NEXUS modules.

Provides deterministic artifact bundling with SHA-256 content addressing:
- Bundle builder: creates immutable, content-addressed bundles
- ArtifactIndex: persistent metadata for bundle tracking
- Self-check: verifies bundle determinism
- Diff: compares two bundles to identify changes
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class FileArtifact:
    """Metadata for a single file in a bundle."""
    path: str
    size: int
    sha256: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256
        }


@dataclass
class ArtifactIndex:
    """
    Persistent index record for an artifact bundle.

    Tracks bundle identity, constituent files, and metadata for auditing.
    """
    job_id: str
    attempt_id: int
    bundle_sha256: str
    files: List[FileArtifact]
    created_at: str
    module_id: Optional[str] = None
    stage: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "bundle_sha256": self.bundle_sha256,
            "files": [f.to_dict() for f in self.files],
            "created_at": self.created_at,
            "module_id": self.module_id,
            "stage": self.stage
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ArtifactIndex':
        """Create ArtifactIndex from dictionary."""
        files = [
            FileArtifact(
                path=f["path"],
                size=f["size"],
                sha256=f["sha256"]
            )
            for f in data["files"]
        ]
        return cls(
            job_id=data["job_id"],
            attempt_id=data["attempt_id"],
            bundle_sha256=data["bundle_sha256"],
            files=files,
            created_at=data["created_at"],
            module_id=data.get("module_id"),
            stage=data.get("stage")
        )


class ArtifactBundleBuilder:
    """
    Builder for content-addressed artifact bundles.

    Creates deterministic bundles from file contents:
    1. Hash each file individually (SHA-256)
    2. Sort files by path for determinism
    3. Create bundle hash from sorted file hashes
    4. Return ArtifactIndex with full provenance
    """

    @staticmethod
    def hash_content(content: str) -> str:
        """
        Hash content using SHA-256.

        Args:
            content: String content to hash

        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def hash_file(file_path: Path) -> str:
        """
        Hash file contents using SHA-256.

        Args:
            file_path: Path to file

        Returns:
            Hex-encoded SHA-256 hash
        """
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def build_from_dict(
        files: Dict[str, str],
        job_id: str,
        attempt_id: int,
        module_id: Optional[str] = None,
        stage: Optional[str] = None
    ) -> ArtifactIndex:
        """
        Build artifact bundle from dictionary of path -> content.

        Args:
            files: Dictionary mapping file paths to file contents
            job_id: Unique identifier for the generation job
            attempt_id: Attempt number for this job
            module_id: Optional module identifier
            stage: Optional generation stage

        Returns:
            ArtifactIndex with bundle hash and file metadata
        """
        # Sort files by path for determinism
        sorted_paths = sorted(files.keys())

        # Hash each file and create artifacts
        file_artifacts = []
        file_hashes = []

        for path in sorted_paths:
            content = files[path]
            file_hash = ArtifactBundleBuilder.hash_content(content)
            size = len(content.encode('utf-8'))

            file_artifacts.append(FileArtifact(
                path=path,
                size=size,
                sha256=file_hash
            ))
            file_hashes.append(file_hash)

        # Create bundle hash from sorted file hashes
        bundle_content = "".join(file_hashes)
        bundle_hash = hashlib.sha256(bundle_content.encode('utf-8')).hexdigest()

        # Create index
        return ArtifactIndex(
            job_id=job_id,
            attempt_id=attempt_id,
            bundle_sha256=bundle_hash,
            files=file_artifacts,
            created_at=datetime.utcnow().isoformat() + "Z",
            module_id=module_id,
            stage=stage
        )

    @staticmethod
    def build_from_directory(
        directory: Path,
        job_id: str,
        attempt_id: int,
        module_id: Optional[str] = None,
        stage: Optional[str] = None,
        include_patterns: Optional[List[str]] = None
    ) -> ArtifactIndex:
        """
        Build artifact bundle from files in a directory.

        Args:
            directory: Path to directory containing files
            job_id: Unique identifier for the generation job
            attempt_id: Attempt number for this job
            module_id: Optional module identifier
            stage: Optional generation stage
            include_patterns: Optional list of glob patterns to include

        Returns:
            ArtifactIndex with bundle hash and file metadata
        """
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        # Collect files
        if include_patterns:
            all_files = []
            for pattern in include_patterns:
                all_files.extend(directory.glob(pattern))
        else:
            all_files = directory.rglob("*")

        # Filter to only files (not directories)
        files_dict = {}
        for file_path in all_files:
            if file_path.is_file():
                relative_path = str(file_path.relative_to(directory))
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    files_dict[relative_path] = f.read()

        return ArtifactBundleBuilder.build_from_dict(
            files=files_dict,
            job_id=job_id,
            attempt_id=attempt_id,
            module_id=module_id,
            stage=stage
        )

    @staticmethod
    def self_check(files: Dict[str, str]) -> bool:
        """
        Verify that bundle hash is deterministic for identical inputs.

        Args:
            files: Dictionary mapping file paths to contents

        Returns:
            True if bundle hash is stable across multiple builds
        """
        # Build bundle twice
        bundle1 = ArtifactBundleBuilder.build_from_dict(
            files=files,
            job_id="self-check",
            attempt_id=1
        )

        bundle2 = ArtifactBundleBuilder.build_from_dict(
            files=files,
            job_id="self-check",
            attempt_id=2
        )

        # Hashes should be identical despite different attempt_id
        return bundle1.bundle_sha256 == bundle2.bundle_sha256

    @staticmethod
    def diff_bundles(
        bundle1: ArtifactIndex,
        bundle2: ArtifactIndex
    ) -> Dict[str, any]:
        """
        Compare two bundles and identify changes.

        Args:
            bundle1: First bundle (baseline)
            bundle2: Second bundle (comparison)

        Returns:
            Dictionary with changed, added, deleted files
        """
        # Create path -> hash mappings
        files1 = {f.path: f.sha256 for f in bundle1.files}
        files2 = {f.path: f.sha256 for f in bundle2.files}

        paths1 = set(files1.keys())
        paths2 = set(files2.keys())

        # Identify changes
        added = paths2 - paths1
        deleted = paths1 - paths2
        common = paths1 & paths2

        changed = set()
        for path in common:
            if files1[path] != files2[path]:
                changed.add(path)

        return {
            "identical": bundle1.bundle_sha256 == bundle2.bundle_sha256,
            "added": sorted(list(added)),
            "deleted": sorted(list(deleted)),
            "changed": sorted(list(changed)),
            "unchanged": sorted(list(common - changed))
        }


def verify_bundle_hash(index: ArtifactIndex, files: Dict[str, str]) -> bool:
    """
    Verify that bundle hash matches the files.

    Args:
        index: ArtifactIndex to verify
        files: Dictionary of file paths to contents

    Returns:
        True if bundle hash matches recomputed hash
    """
    # Rebuild bundle with same job_id/attempt_id won't work because created_at differs
    # Instead, verify file hashes and recompute bundle hash
    file_hashes = []
    sorted_paths = sorted(files.keys())

    for path in sorted_paths:
        content = files[path]
        file_hash = ArtifactBundleBuilder.hash_content(content)
        file_hashes.append(file_hash)

    bundle_content = "".join(file_hashes)
    computed_hash = hashlib.sha256(bundle_content.encode('utf-8')).hexdigest()

    return computed_hash == index.bundle_sha256
