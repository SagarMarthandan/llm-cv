#!/usr/bin/env python3
"""
sync_to_obsidian.py — Bridge script that walks the LLM-CV Applications tree
and emits linked Obsidian notes into the vault for graph-view navigation.

Handles two application formats:
  - YAML format (older): ATS_Report.yaml, Job_Description.yaml, Resume.yaml, ...
  - MD format  (newer): ATS_Report.md, Job_Description.md, Resume.md, ...

Generates notes under <vault>/Job Search/:
  Applications/  — one note per application
  Companies/     — one note per company
  Roles/         — one note per role archetype
  Skills/        — one note per skill extracted from JDs
  Projects/      — one note per project used in applications
  * Index.md     — index notes listing all entries in each category

Usage:
  python sync_to_obsidian.py [--dry-run] [--verbose]

Config:
  APPLICATIONS_DIR and VAULT_DIR at the top of this file.

---

This file is now the CLI entry point. The core logic lives in:
  - obsidian_sync_core.py   — note generation, parsers, sync logic, skill/project normalization
  - obsidian_folder_sort.py — folder sorting (the --sort functionality)

All public names from both modules are re-exported here so that existing
imports (e.g. organize_applications.py) continue to work unchanged.
"""

import argparse
import sys

# ─── Re-export everything from the split modules ──────────────────────────────

# Core sync logic: parsers, note generators, sync(), sync_targeted(), etc.
from obsidian_sync_core import (  # noqa: F401
    APPLICATIONS_DIR,
    VAULT_DIR,
    OUTPUT_ROOT,
    EM_DASH,
    EN_DASH,
    slugify,
    normalize_skill,
    normalize_project,
    parse_ats_yaml,
    parse_jd_yaml,
    parse_resume_yaml,
    parse_ats_md,
    parse_jd_md,
    parse_resume_md,
    parse_project_info_md,
    find_application_folders,
    parse_application,
    app_note_name,
    generate_application_note,
    generate_entity_note,
    generate_index_note,
    sync,
    _patch_index_note,
    _patch_entity_note,
    sync_targeted,
)

# Folder-sort logic: _move_into_tree(), sort_all_folders(), etc.
from obsidian_folder_sort import (  # noqa: F401
    _is_year_folder,
    _creation_date,
    _target_subpath,
    _move_into_tree,
    sort_all_folders,
)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync LLM-CV applications to Obsidian vault")
    parser.add_argument("target", nargs="?", default=None,
                        help="Target application folder for incremental sync. If omitted, does a full rebuild.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without writing files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-application progress")
    parser.add_argument("--sort", action="store_true",
                        help="After syncing, move the target folder into the YYYY/MM/DD tree (targeted mode only)")
    parser.add_argument("--full", action="store_true",
                        help="Force full rebuild even when a target is given")
    args = parser.parse_args()

    if args.target and not args.full:
        sync_targeted(args.target, dry_run=args.dry_run, verbose=args.verbose, do_sort=args.sort)
    else:
        if args.sort and not args.target:
            print("Warning: --sort is ignored in full rebuild mode (use with a target folder).", file=sys.stderr)
        sync(dry_run=args.dry_run, verbose=args.verbose)
