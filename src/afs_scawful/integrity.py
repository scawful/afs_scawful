"""File integrity verification using SHA256 checksums.

Provides manifest generation and verification for training artifacts.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class FileEntry:
    """A single file in the manifest."""

    path: str
    sha256: str
    size: int
    mtime: float


@dataclass
class Manifest:
    """A manifest of files with checksums."""

    files: list[FileEntry]
    generated_at: float
    root_path: str
    version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "root_path": self.root_path,
            "files": [asdict(f) for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        files = [FileEntry(**f) for f in data.get("files", [])]
        return cls(
            files=files,
            generated_at=data.get("generated_at", 0),
            root_path=data.get("root_path", ""),
            version=data.get("version", "1.0"),
        )


def compute_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def generate_manifest(
    directory: Path,
    exclude_patterns: Optional[list[str]] = None,
) -> Manifest:
    """Generate a manifest for all files in a directory.

    Args:
        directory: Root directory to scan
        exclude_patterns: Glob patterns to exclude (e.g., ["*.log", "*.tmp"])

    Returns:
        Manifest with checksums for all files
    """
    directory = Path(directory).resolve()
    exclude_patterns = exclude_patterns or []

    files: list[FileEntry] = []

    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        # Check exclusions
        rel_path = file_path.relative_to(directory)
        excluded = False
        for pattern in exclude_patterns:
            if rel_path.match(pattern):
                excluded = True
                break
        if excluded:
            continue

        try:
            stat = file_path.stat()
            sha256 = compute_sha256(file_path)
            files.append(
                FileEntry(
                    path=str(rel_path),
                    sha256=sha256,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )
        except (OSError, IOError) as e:
            # Skip unreadable files
            print(f"Warning: Could not read {file_path}: {e}")
            continue

    return Manifest(
        files=files,
        generated_at=time.time(),
        root_path=str(directory),
    )


@dataclass
class VerificationResult:
    """Result of manifest verification."""

    success: bool
    verified_count: int
    missing_files: list[str]
    corrupted_files: list[str]
    size_mismatches: list[str]
    extra_files: list[str]

    @property
    def error_count(self) -> int:
        return (
            len(self.missing_files)
            + len(self.corrupted_files)
            + len(self.size_mismatches)
        )


def verify_manifest(
    directory: Path,
    manifest: Manifest,
    check_extra: bool = False,
) -> VerificationResult:
    """Verify a directory matches a manifest.

    Args:
        directory: Directory to verify
        manifest: Manifest to check against
        check_extra: If True, report files not in manifest

    Returns:
        VerificationResult with details of any mismatches
    """
    directory = Path(directory).resolve()

    missing_files: list[str] = []
    corrupted_files: list[str] = []
    size_mismatches: list[str] = []
    verified_count = 0

    manifest_paths = set()

    for entry in manifest.files:
        manifest_paths.add(entry.path)
        file_path = directory / entry.path

        if not file_path.exists():
            missing_files.append(entry.path)
            continue

        # Check size first (fast)
        actual_size = file_path.stat().st_size
        if actual_size != entry.size:
            size_mismatches.append(
                f"{entry.path} (expected {entry.size}, got {actual_size})"
            )
            continue

        # Check hash
        actual_sha256 = compute_sha256(file_path)
        if actual_sha256 != entry.sha256:
            corrupted_files.append(entry.path)
            continue

        verified_count += 1

    # Check for extra files
    extra_files: list[str] = []
    if check_extra:
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(directory))
                if rel_path not in manifest_paths:
                    extra_files.append(rel_path)

    success = not missing_files and not corrupted_files and not size_mismatches

    return VerificationResult(
        success=success,
        verified_count=verified_count,
        missing_files=missing_files,
        corrupted_files=corrupted_files,
        size_mismatches=size_mismatches,
        extra_files=extra_files,
    )


def save_manifest(manifest: Manifest, output_path: Path) -> None:
    """Save manifest to a JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2)


def load_manifest(manifest_path: Path) -> Manifest:
    """Load manifest from a JSON file."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Manifest.from_dict(data)


def quick_verify(directory: Path, manifest_path: Optional[Path] = None) -> bool:
    """Quick verification - returns True if directory matches manifest.

    If manifest_path is not provided, looks for MANIFEST.json in directory.
    """
    directory = Path(directory)
    if manifest_path is None:
        manifest_path = directory / "MANIFEST.json"

    if not manifest_path.exists():
        return False

    manifest = load_manifest(manifest_path)
    result = verify_manifest(directory, manifest)
    return result.success


# CLI interface for shell scripts
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m afs_scawful.integrity <generate|verify> <directory> [manifest]")
        sys.exit(1)

    command = sys.argv[1]
    directory = Path(sys.argv[2])

    if command == "generate":
        manifest = generate_manifest(directory, exclude_patterns=["*.log", "*.tmp"])
        output = directory / "MANIFEST.json"
        save_manifest(manifest, output)
        print(f"Generated manifest: {output}")
        print(f"  Files: {len(manifest.files)}")
        total_size = sum(f.size for f in manifest.files)
        print(f"  Total size: {total_size:,} bytes")

    elif command == "verify":
        manifest_path = Path(sys.argv[3]) if len(sys.argv) > 3 else directory / "MANIFEST.json"
        manifest = load_manifest(manifest_path)
        result = verify_manifest(directory, manifest)

        if result.success:
            print(f"Verification PASSED: {result.verified_count} files OK")
            sys.exit(0)
        else:
            print(f"Verification FAILED:")
            if result.missing_files:
                print(f"  Missing: {len(result.missing_files)}")
                for f in result.missing_files[:5]:
                    print(f"    - {f}")
            if result.corrupted_files:
                print(f"  Corrupted: {len(result.corrupted_files)}")
                for f in result.corrupted_files[:5]:
                    print(f"    - {f}")
            if result.size_mismatches:
                print(f"  Size mismatch: {len(result.size_mismatches)}")
                for f in result.size_mismatches[:5]:
                    print(f"    - {f}")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
