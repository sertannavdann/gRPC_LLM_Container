"""
SHA-256 hashing utilities for NEXUS module system.

Single source of truth for content-addressed artifact hashing.
"""
import hashlib
from typing import Dict


def compute_sha256(content: bytes) -> str:
    """
    Compute SHA-256 hash of content.

    Args:
        content: Bytes to hash

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(content).hexdigest()


def compute_bundle_hash(files: Dict[str, bytes]) -> str:
    """
    Compute deterministic bundle hash from multiple files.

    Files are sorted by path for determinism, then their individual hashes
    are concatenated and hashed to create a single bundle identifier.

    Args:
        files: Dictionary mapping file paths to file contents (as bytes)

    Returns:
        Hex-encoded SHA-256 hash of the bundle
    """
    # Sort files by path for determinism
    sorted_paths = sorted(files.keys())

    # Hash each file
    file_hashes = []
    for path in sorted_paths:
        file_hash = compute_sha256(files[path])
        file_hashes.append(file_hash)

    # Create bundle hash from concatenated file hashes
    bundle_content = "".join(file_hashes)
    return hashlib.sha256(bundle_content.encode('utf-8')).hexdigest()
