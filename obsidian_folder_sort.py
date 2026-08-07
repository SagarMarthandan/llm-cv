#!/usr/bin/env python3
"""
obsidian_folder_sort.py — Sort application folders into a YYYY/MM/DD tree.

Extracted from the original sync_to_obsidian.py monolith. Contains the
folder-sorting logic (the `--sort` functionality) that moves application
folders from the Applications/ top level into Applications/YYYY/MM/DD/.
"""

import gc
import os
import shutil
import time
from datetime import datetime as _dt
from pathlib import Path

from config import APPLICATIONS_DIR
# ─── Folder sort (merged from organize_applications.py) ──────────────────────


def _is_year_folder(name: str) -> bool:
    """True if name is a 4-digit year (top-level date bucket)."""
    return len(name) == 4 and name.isdigit()


def _creation_date(path: str) -> _dt:
    """Return the folder creation timestamp as a datetime."""
    return _dt.fromtimestamp(os.path.getctime(path))


def _target_subpath(dt: _dt) -> str:
    """Build the YYYY/MM/DD relative subpath for a given datetime."""
    return os.path.join(f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}")


def _move_into_tree(
    folder_path: str,
    applications_dir: str | None = None,
    dry_run: bool = False,
) -> str | None:
    """
    Move a single application folder into Applications/YYYY/MM/DD/.

    Returns the new path on success, or None if the folder was already nested
    under a date tree (or could not be moved).
    """
    apps_dir = applications_dir if applications_dir is not None else str(APPLICATIONS_DIR)
    folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(folder_path):
        print(f"  skip (not a directory): {folder_path}")
        return None

    # Skip folders already inside a YYYY/MM/DD tree.
    rel = os.path.relpath(folder_path, apps_dir)
    parts = rel.split(os.sep)
    if len(parts) >= 4 and _is_year_folder(parts[0]):
        print(f"  skip (already sorted): {rel}")
        return None

    dt = _creation_date(folder_path)
    dest_dir = os.path.join(apps_dir, _target_subpath(dt))
    dest_path = os.path.join(dest_dir, os.path.basename(folder_path))

    if os.path.exists(dest_path):
        if os.path.normcase(folder_path) == os.path.normcase(dest_path):
            print(f"  skip (already in place): {rel}")
            return None
        print(f"  WARN destination exists, leaving in place: {dest_path}")
        return None

    if dry_run:
        print(f"  [dry-run] {rel} -> {os.path.relpath(dest_path, apps_dir)}")
        return dest_path

    os.makedirs(dest_dir, exist_ok=True)
    _resilient_move(folder_path, dest_path)
    print(f"  moved: {rel} -> {os.path.relpath(dest_path, apps_dir)}")
    return dest_path


def _resilient_move(src: str, dst: str, max_retries: int = 3, delay: float = 0.5) -> None:
    """
    Move ``src`` to ``dst`` with Windows file-lock recovery.

    On Windows, a folder rename/move can fail with ``[WinError 32]`` (file in
    use) if a process — often the agent's own working directory reference or
    a file watcher — holds an open handle inside the tree. This helper:

    1. Tries ``shutil.move`` up to ``max_retries`` times, calling
       ``gc.collect()`` and sleeping ``delay`` seconds between attempts to
       release lingering file handles.
    2. If all rename attempts fail with ``PermissionError`` / ``OSError``
       (WinError 32), falls back to ``shutil.copytree`` + ``shutil.rmtree``,
       which works even when the directory handle is locked (copy reads file
       contents; rmtree removes entries one-by-one).
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            shutil.move(src, dst)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            # WinError 32 = "The process cannot access the file because it is
            # being used by another process." Retry after GC + short delay.
            gc.collect()
            if attempt < max_retries:
                time.sleep(delay)
    # All rename attempts failed — fall back to copy + delete, which works
    # even when a directory handle is held open (copytree reads file
    # contents; rmtree removes entries individually rather than renaming).
    try:
        shutil.copytree(src, dst)
        shutil.rmtree(src)
    except (PermissionError, OSError) as e:
        raise OSError(
            f"Failed to move {src} -> {dst} after {max_retries} retries and "
            f"copy+delete fallback: {e} (original error: {last_err})"
        ) from e


def sort_all_folders(
    applications_dir: str | None = None,
    dry_run: bool = False,
) -> int:
    """Scan Applications/ top-level and move every non-year folder into the tree."""
    apps_dir = applications_dir if applications_dir is not None else str(APPLICATIONS_DIR)
    if not os.path.isdir(apps_dir):
        print(f"Applications directory not found: {apps_dir}")
        return 0

    moved = 0
    for name in sorted(os.listdir(apps_dir)):
        full = os.path.join(apps_dir, name)
        if not os.path.isdir(full):
            continue
        if _is_year_folder(name):
            continue
        if _move_into_tree(full, applications_dir=apps_dir, dry_run=dry_run):
            moved += 1
    return moved
