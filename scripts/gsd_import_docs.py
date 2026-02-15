#!/usr/bin/env python3
"""
GSD Import — Generate .planning/ canonical files from docs/** and docs/archive/**

Usage:
    python scripts/gsd_import_docs.py [--check]

Flags:
    --check   Validate that .planning/ files exist and are non-empty (exit 1 if not)

This script is intentionally idempotent: re-running it verifies the planning
directory structure without overwriting hand-edited files.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLANNING_DIR = PROJECT_ROOT / ".planning"
RESEARCH_DIR = PLANNING_DIR / "research"
GSD_IMPORT_DIR = PROJECT_ROOT / "docs" / "_gsd_import"
DOCS_DIR = PROJECT_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"

CANONICAL_FILES = [
    PLANNING_DIR / "PROJECT.md",
    PLANNING_DIR / "REQUIREMENTS.md",
    PLANNING_DIR / "ROADMAP.md",
    PLANNING_DIR / "STATE.md",
    RESEARCH_DIR / "SUMMARY.md",
]

IMPORT_FILES = [
    GSD_IMPORT_DIR / "DOC_INDEX.md",
    GSD_IMPORT_DIR / "HISTORY_SUMMARY.md",
]

# ---------------------------------------------------------------------------
# Category heuristics (path + filename → category)
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "ARCHITECTURE": "architecture/HLD",
    "HIGH_LEVEL_DESIGN": "architecture/HLD",
    "API-REFERENCE": "API/contracts",
    "EXTENSION-GUIDE": "API/contracts",
    "SECURITY": "security/compliance",
    "OPERATIONS": "ops/runbooks",
    "RUNBOOK": "ops/runbooks",
    "USER_TESTING": "ops/runbooks",
    "ROADMAP": "roadmap/plans",
    "PLAN": "roadmap/plans",
    "EXECUTION_PLAN": "roadmap/plans",
    "MONETIZATION": "roadmap/plans",
    "KNOWN-ISSUES": "changelogs/releases",
    "BRANCH_SUMMARY": "changelogs/releases",
    "PROJECT_VISION": "vision/overview",
    "NEXUS_LEAN_CANVAS": "vision/overview",
    "GLOSSARY": "vision/overview",
    "README": "vision/overview",
    "_INDEX": "vision/overview",
    "next-phase": "ADR/decisions",
}


def categorize(filename: str) -> str:
    stem = Path(filename).stem.upper().replace("-", "_")
    for key, cat in CATEGORY_MAP.items():
        if key.upper().replace("-", "_") in stem:
            return cat
    return "experiments"


def scan_docs() -> list[dict]:
    """Scan docs/ and docs/archive/ and return metadata list."""
    entries = []
    for root, _dirs, files in os.walk(DOCS_DIR):
        for f in files:
            if not f.endswith(".md"):
                continue
            full = Path(root) / f
            rel = full.relative_to(PROJECT_ROOT)
            is_archive = "archive" in str(rel)
            stat = full.stat()
            entries.append({
                "path": str(rel),
                "title": _extract_title(full),
                "last_modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m"),
                "category": categorize(f),
                "current_or_historical": "historical" if is_archive else "current",
            })
    return entries


def _extract_title(path: Path) -> str:
    """Pull the first H1 from a markdown file."""
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
    except Exception:
        pass
    return path.stem


def validate_check_mode() -> bool:
    """Return True if all canonical + import files exist and are non-empty."""
    ok = True
    for p in CANONICAL_FILES + IMPORT_FILES:
        if not p.exists():
            print(f"MISSING: {p.relative_to(PROJECT_ROOT)}")
            ok = False
        elif p.stat().st_size == 0:
            print(f"EMPTY:   {p.relative_to(PROJECT_ROOT)}")
            ok = False
        else:
            print(f"OK:      {p.relative_to(PROJECT_ROOT)}")
    return ok


def generate_doc_index(entries: list[dict]) -> str:
    """Generate DOC_INDEX.md content from scan results."""
    lines = [
        "# GSD Import — Document Index\n",
        f"> **Generated**: {datetime.now().strftime('%Y-%m-%d')}\n",
        "> **Source**: `docs/**` + `docs/archive/**`\n",
        "",
        "| Path | Title | Last Modified | Category | Current/Historical |",
        "|------|-------|---------------|----------|---------------------|",
    ]
    for e in sorted(entries, key=lambda x: (x["current_or_historical"], x["path"])):
        lines.append(
            f"| `{e['path']}` | {e['title']} | {e['last_modified']} "
            f"| {e['category']} | {e['current_or_historical']} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    check_mode = "--check" in sys.argv

    if check_mode:
        ok = validate_check_mode()
        sys.exit(0 if ok else 1)

    # Ensure directories exist
    PLANNING_DIR.mkdir(exist_ok=True)
    RESEARCH_DIR.mkdir(exist_ok=True)
    GSD_IMPORT_DIR.mkdir(exist_ok=True)

    # Scan and regenerate DOC_INDEX (always safe to overwrite — it's auto-generated)
    entries = scan_docs()
    index_content = generate_doc_index(entries)
    (GSD_IMPORT_DIR / "DOC_INDEX.md").write_text(index_content)
    print(f"[gsd-import] Wrote {GSD_IMPORT_DIR / 'DOC_INDEX.md'}")

    # Validate that canonical files exist (do NOT overwrite — they may be hand-edited)
    missing = []
    for p in CANONICAL_FILES + IMPORT_FILES:
        if p.exists() and p.stat().st_size > 0:
            print(f"[gsd-import] OK: {p.relative_to(PROJECT_ROOT)}")
        elif not p.exists():
            missing.append(str(p.relative_to(PROJECT_ROOT)))
            print(f"[gsd-import] MISSING: {p.relative_to(PROJECT_ROOT)}")

    if missing:
        print(f"\n[gsd-import] WARNING: {len(missing)} canonical file(s) missing.")
        print("[gsd-import] Run the GSD bootstrap to generate them.")
        sys.exit(1)

    print(f"\n[gsd-import] All {len(CANONICAL_FILES) + len(IMPORT_FILES)} planning files present.")
    print(f"[gsd-import] Scanned {len(entries)} doc(s) from docs/**.")
    print("[gsd-import] Done.")


if __name__ == "__main__":
    main()
