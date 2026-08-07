"""
organize_applications.py — Sort application folders into a Year/Month/Date tree.

The core logic has been merged into sync_to_obsidian.py. This file remains as a
thin shim for backward compatibility and standalone manual sorting of older
unsorted application folders.

Usage
-----
Standalone (sort everything in Applications/):
    python organize_applications.py

Targeted (sort a single freshly-created application folder):
    python organize_applications.py "Applications/[Company Name] — [Job Role]"

Dry run (report what would move, change nothing):
    python organize_applications.py --dry-run

Override the Applications root (for testing):
    python organize_applications.py --root "C:/path/to/fake/Applications"
"""
import os
import sys

# Force UTF-8 on stdout/stderr so unicode paths always print safely.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
from config import APPLICATIONS_DIR
# Import the merged functions from sync_to_obsidian.py
from sync_to_obsidian import _move_into_tree, sort_all_folders


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    apps_dir = APPLICATIONS_DIR
    args: list[str] = []
    it = iter(argv[1:])
    for arg in it:
        if arg == "--dry-run":
            continue
        if arg == "--root":
            apps_dir = next(it, APPLICATIONS_DIR)
            continue
        args.append(arg)

    print(f"Applications root: {apps_dir}")

    if args:
        for arg in args:
            candidate = arg if os.path.isabs(arg) else os.path.abspath(arg)
            if not os.path.isdir(candidate):
                candidate = os.path.join(apps_dir, arg)
            print(f"Sorting: {candidate}")
            _move_into_tree(candidate, applications_dir=apps_dir, dry_run=dry_run)
    else:
        print("Scanning Applications/ for unsorted application folders...")
        count = sort_all_folders(applications_dir=apps_dir, dry_run=dry_run)
        print(f"Done. Moved {count} folder(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
