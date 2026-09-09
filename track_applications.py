#!/usr/bin/env python3
"""
track_applications.py — Application tracking CSV for the llm-cv pipeline.

Collects all applications from the Applications folder and the Obsidian vault,
matches them, and writes a CSV tracker at /home/sagar/Documents/applications_tracker.csv.

Modes:
  --rebuild          Full rebuild from Applications folder + Obsidian vault (default)
  --append <dir>     Append/update a single application (for pipeline integration)
  --dry-run          Show what would be written without writing

Usage:
  # Full rebuild (scan everything, match, write CSV):
  .venv/bin/python track_applications.py --rebuild

  # Append/update a single application (pipeline integration):
  .venv/bin/python track_applications.py --append "/home/sagar/Applications/2026/09/08/Company — Role"

  # Dry run:
  .venv/bin/python track_applications.py --rebuild --dry-run
"""
import argparse
import csv
import os
import re
import sys
from pathlib import Path

import yaml
from tqdm import tqdm

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
APPLICATIONS_DIR = Path(os.getenv("LLM_CV_APPLICATIONS_DIR", "/home/sagar/Applications"))
VAULT_DIR = Path(os.path.expanduser("~/Documents/Obsidian Vault"))
OBSIDIAN_APPS_DIR = VAULT_DIR / "Job Search" / "Applications"
CSV_PATH = Path(os.getenv("LLM_CV_TRACKER_CSV", "/home/sagar/Documents/applications_tracker.csv"))

EM_DASH = "\u2014"
EN_DASH = "\u2013"

CSV_COLUMNS = [
    "Date",
    "Company",
    "Position",
    "Location",
    "Role Archetype",
    "ATS Pre-Score",
    "ATS Post-Score",
    "Score Delta",
    "Score Gate",
    "Application Source",
    "ATS Vendor",
    "Language",
    "Resume Style",
    "Source URL",
    "Job Ref",
    "Skill Gaps",
    "Projects Used",
    "In Obsidian",
    "Folder Path",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Replicate the Obsidian note slugify from obsidian_sync_core.py."""
    name = name.replace(EM_DASH, "-").replace(EN_DASH, "-")
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def find_application_folders(root: Path) -> list[Path]:
    """Find all application folders under YYYY/MM/DD/[Company] — [Role]/."""
    apps: list[Path] = []
    if not root.exists():
        return apps
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue
                for app_dir in sorted(day_dir.iterdir()):
                    if app_dir.is_dir():
                        apps.append(app_dir)
    return apps


def find_unsorted_folders(root: Path) -> list[Path]:
    """Find application folders sitting at the root of Applications/ (not yet sorted)."""
    unsorted: list[Path] = []
    if not root.exists():
        return unsorted
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.isdigit():
            continue  # year folder
        if (entry / "ATS_Report.yaml").exists():
            unsorted.append(entry)
    return unsorted


def extract_projects(resume_path: Path, project_info_path: Path) -> list[str]:
    """Extract project names from Resume.yaml (US + German styles) or project_info.md."""
    projects: list[str] = []

    if resume_path.exists():
        try:
            data = yaml.safe_load(resume_path.read_text(encoding="utf-8"))
            # US style: top-level projects list
            if isinstance(data.get("projects"), list):
                for p in data["projects"]:
                    if isinstance(p, dict) and p.get("name"):
                        projects.append(p["name"])
                    elif isinstance(p, str):
                        projects.append(p)
            # German style: project_bullets under professional_experience
            if not projects:
                for exp in data.get("professional_experience", []):
                    if isinstance(exp, dict):
                        for pb in exp.get("project_bullets", []):
                            if isinstance(pb, dict) and pb.get("name"):
                                projects.append(pb["name"])
        except Exception:
            pass

    # Fallback: project_info.md (# Project Name headers)
    if not projects and project_info_path.exists():
        try:
            for line in project_info_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("# ") and line != "# Tailored Project Portfolio":
                    projects.append(line[2:].strip())
        except Exception:
            pass

    return projects


def parse_application(app_dir: Path) -> dict | None:
    """Parse a single application folder and extract all tracking fields."""
    ats_path = app_dir / "ATS_Report.yaml"
    if not ats_path.exists():
        return None

    try:
        ats = yaml.safe_load(ats_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(ats, dict):
        return None

    jd: dict = {}
    jd_path = app_dir / "Job_Description.yaml"
    if jd_path.exists():
        try:
            jd = yaml.safe_load(jd_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass

    # Date from path: .../Applications/YYYY/MM/DD/[Company]/
    date_str = ""
    parts = app_dir.parts
    try:
        idx = parts.index("Applications")
        date_str = f"{parts[idx + 1]}-{parts[idx + 2]}-{parts[idx + 3]}"
    except (ValueError, IndexError):
        pass

    company = ats.get("company", "") or jd.get("company", "")
    position = ats.get("position", "") or jd.get("position", "")

    # Fallback to folder name split on em-dash/en-dash
    if not company or not position:
        folder_parts = re.split(r"[—–]", app_dir.name, maxsplit=1)
        if len(folder_parts) == 2:
            company = company or folder_parts[0].strip()
            position = position or folder_parts[1].strip()
        else:
            company = company or app_dir.name
            position = position or ""

    # ATS scores
    matrix = ats.get("ats_score_matrix", {})
    pre_score = matrix.get("total_score", "") if isinstance(matrix, dict) else ""

    post = ats.get("post_rewrite_ats_score", {})
    post_score = ""
    score_delta = ""
    score_gate = ""
    if isinstance(post, dict):
        pmatrix = post.get("ats_score_matrix", {})
        if isinstance(pmatrix, dict):
            post_score = pmatrix.get("total_score", "")
        score_delta = post.get("score_delta", "")
        score_gate = post.get("score_gate_verdict", "")

    # Other fields
    location = jd.get("location", "") or ats.get("closest_candidate_location", "")
    archetype = ats.get("role_archetype", {})
    role_archetype = archetype.get("primary", "") if isinstance(archetype, dict) else ""
    skill_gaps = ats.get("skill_gaps", [])
    skill_gaps_str = "; ".join(str(s) for s in skill_gaps) if isinstance(skill_gaps, list) else str(skill_gaps)

    projects = extract_projects(app_dir / "Resume.yaml", app_dir / "project_info.md")

    return {
        "Date": date_str,
        "Company": str(company).strip(),
        "Position": str(position).strip(),
        "Location": str(location).strip(),
        "Role Archetype": str(role_archetype).strip(),
        "ATS Pre-Score": pre_score,
        "ATS Post-Score": post_score,
        "Score Delta": score_delta,
        "Score Gate": str(score_gate).strip(),
        "Application Source": str(ats.get("application_source", "")).strip(),
        "ATS Vendor": str(ats.get("ats_vendor", "")).strip(),
        "Language": str(ats.get("language", "")).strip(),
        "Resume Style": str(ats.get("resume_style", "")).strip(),
        "Source URL": str(ats.get("source_url", "") or jd.get("source_url", "")).strip(),
        "Job Ref": str(ats.get("job_ref", "") or jd.get("ref_number", "")).strip(),
        "Skill Gaps": skill_gaps_str,
        "Projects Used": "; ".join(projects),
        "In Obsidian": "",
        "Folder Path": str(app_dir),
    }


# ─── Obsidian matching ────────────────────────────────────────────────────────

def get_obsidian_notes() -> tuple[dict[str, list[str]], list[str]]:
    """Build index of Obsidian application notes.

    Returns:
        (by_date, all_notes) where:
        by_date: {date_str: [note_filename_lower, ...]} for notes with a date
        all_notes: [note_filename_lower, ...] for every note (date or not)
    """
    by_date: dict[str, list[str]] = {}
    all_notes: list[str] = []
    if not OBSIDIAN_APPS_DIR.exists():
        return by_date, all_notes
    for note_path in OBSIDIAN_APPS_DIR.glob("*.md"):
        filename = note_path.stem
        all_notes.append(filename.lower())
        date_match = re.search(r"\((\d{4}-\d{2}-\d{2})\)", filename)
        if date_match:
            date = date_match.group(1)
            by_date.setdefault(date, []).append(filename.lower())
    return by_date, all_notes


def _company_in_notes(company: str, notes: list[str]) -> bool:
    """Check if company name (or first significant word) appears in any note."""
    if not company:
        return False
    # Direct substring match
    for note in notes:
        if company in note:
            return True
    # First significant word (handles long company names)
    words = company.split()
    if words and len(words[0]) > 3:
        first_word = words[0]
        for note in notes:
            if first_word in note:
                return True
    # Try with "/" stripped (slugify removes it from note names)
    if "/" in company:
        company_noslash = company.replace("/", "")
        for note in notes:
            if company_noslash in note:
                return True
    return False


def check_in_obsidian(
    app: dict, by_date: dict[str, list[str]], all_notes: list[str]
) -> str:
    """Check if an application has a matching Obsidian note.

    Pass 1: match by date + company (precise).
    Pass 2: match by company only across all notes (handles dateless notes).
    """
    date = app["Date"]
    company = app["Company"].lower()
    if not company:
        return "No"

    # Pass 1: date + company
    if date:
        date_notes = by_date.get(date, [])
        if _company_in_notes(company, date_notes):
            return "Yes"

    # Pass 2: company only across ALL notes (handles notes without dates)
    if _company_in_notes(company, all_notes):
        return "Yes"

    return "No"


def find_orphaned_notes(
    apps: list[dict], by_date: dict[str, list[str]], all_notes: list[str]
) -> list[str]:
    """Find Obsidian notes that have no matching application folder."""
    # Collect all company names from applications
    all_companies: set[str] = set()
    for app in apps:
        company = app["Company"].lower()
        if company:
            all_companies.add(company)
            if "/" in company:
                all_companies.add(company.replace("/", ""))

    orphans: list[str] = []
    for note in all_notes:
        matched = False
        for company in all_companies:
            if company in note:
                matched = True
                break
            words = company.split()
            if words and len(words[0]) > 3 and words[0] in note:
                matched = True
                break
        if not matched:
            orphans.append(note)
    return orphans


# ─── CSV I/O ──────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict]) -> None:
    """Write rows to the CSV file (utf-8-sig for spreadsheet compatibility)."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_existing_csv() -> list[dict]:
    """Read existing CSV rows (handles utf-8-sig BOM)."""
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


# ─── Modes ────────────────────────────────────────────────────────────────────

def rebuild_csv(dry_run: bool = False) -> int:
    """Full rebuild: scan Applications folder + Obsidian vault, match, write CSV."""
    print(f"[track] Scanning Applications folder: {APPLICATIONS_DIR}")
    app_folders = find_application_folders(APPLICATIONS_DIR)
    unsorted = find_unsorted_folders(APPLICATIONS_DIR)
    if unsorted:
        print(f"[track]   ({len(unsorted)} unsorted folders at root level)")
        app_folders.extend(unsorted)
    print(f"[track] Found {len(app_folders)} application folders")

    print(f"[track] Scanning Obsidian vault: {OBSIDIAN_APPS_DIR}")
    by_date, all_notes = get_obsidian_notes()
    print(f"[track] Found {len(all_notes)} Obsidian application notes")

    rows: list[dict] = []
    matched = 0
    not_in_obsidian = 0
    parse_failures = 0

    for app_dir in tqdm(app_folders, desc="Parsing applications", unit="app",
                        file=sys.stderr, leave=False):
        app = parse_application(app_dir)
        if app is None:
            parse_failures += 1
            continue
        app["In Obsidian"] = check_in_obsidian(app, by_date, all_notes)
        if app["In Obsidian"] == "Yes":
            matched += 1
        else:
            not_in_obsidian += 1
        rows.append(app)

    rows.sort(key=lambda r: r["Date"], reverse=True)

    orphans = find_orphaned_notes(rows, by_date, all_notes)

    print(f"\n[track] ── Summary ──")
    print(f"[track] Parsed:          {len(rows)} applications")
    print(f"[track] In Obsidian:      {matched}")
    print(f"[track] Not in Obsidian:   {not_in_obsidian}")
    print(f"[track] Orphaned notes:    {len(orphans)}")
    if parse_failures:
        print(f"[track] Parse failures:   {parse_failures}")

    if not_in_obsidian:
        print(f"\n[track] Applications NOT in Obsidian (sync issues):")
        for r in rows:
            if r["In Obsidian"] == "No":
                print(f"  {r['Date']} | {r['Company']} — {r['Position']}")
                print(f"    {r['Folder Path']}")

    if orphans:
        print(f"\n[track] Obsidian notes without matching folder (orphaned):")
        for note in orphans[:20]:
            print(f"  {note}")
        if len(orphans) > 20:
            print(f"  ... and {len(orphans) - 20} more")

    if dry_run:
        print(f"\n[track] DRY RUN — would write {len(rows)} rows to {CSV_PATH}")
        return 0

    write_csv(rows)
    print(f"\n[track] CSV written: {CSV_PATH} ({len(rows)} rows)")
    return 0


def append_csv(app_dir: str, dry_run: bool = False) -> int:
    """Append or update a single application in the CSV."""
    app_path = Path(app_dir)
    if not app_path.exists():
        print(f"[track] Error: folder not found: {app_dir}", file=sys.stderr)
        return 1

    app = parse_application(app_path)
    if app is None:
        print(f"[track] Error: could not parse (no ATS_Report.yaml): {app_dir}", file=sys.stderr)
        return 1

    by_date, all_notes = get_obsidian_notes()
    app["In Obsidian"] = check_in_obsidian(app, by_date, all_notes)

    existing_rows = read_existing_csv()

    # Match by (company, position, date) — update if exists, append if new
    key = (app["Company"].lower(), app["Position"].lower(), app["Date"])
    updated = False
    for i, row in enumerate(existing_rows):
        row_key = (
            row.get("Company", "").lower(),
            row.get("Position", "").lower(),
            row.get("Date", ""),
        )
        if row_key == key:
            existing_rows[i] = app
            updated = True
            break

    if not updated:
        existing_rows.append(app)

    existing_rows.sort(key=lambda r: r.get("Date", ""), reverse=True)

    if dry_run:
        action = "Updated" if updated else "Appended"
        print(f"[track] DRY RUN — would {action.lower()}: {app['Company']} — {app['Position']} ({app['Date']})")
        return 0

    write_csv(existing_rows)
    action = "Updated" if updated else "Appended"
    print(f"[track] {action}: {app['Company']} — {app['Position']} ({app['Date']})")
    print(f"[track] CSV: {CSV_PATH} ({len(existing_rows)} rows)")
    return 0


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Track llm-cv applications in a CSV file at ~/Documents/"
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Full rebuild from Applications folder + Obsidian vault (default)"
    )
    parser.add_argument(
        "--append", metavar="DIR",
        help="Append/update a single application folder to the CSV"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be written without writing"
    )
    args = parser.parse_args()

    if args.append:
        return append_csv(args.append, dry_run=args.dry_run)
    else:
        return rebuild_csv(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
