#!/usr/bin/env python3
"""
check_duplicate_application.py — Detect prior applications to the same job.

Searches the Obsidian vault (primary) and the Applications filesystem tree
(secondary) for existing applications matching the same company + role as the
current application.  Reports matches with dates, ATS scores, and paths so the
user can decide whether to proceed with a new resume or abort.

Usage:
  python check_duplicate_application.py <app_dir> [--json]
  python check_duplicate_application.py --company "Accenture" --position "Junior Applied AI Engineer (all genders)" [--json]

<app_dir>  Path to the current application folder (must contain ATS_Report.yaml
           or ATS_Report.md).

--json     Emit JSON instead of human-readable text (for programmatic consumers).

Exit codes:
  0  No duplicates found.
  1  One or more duplicate applications found.
  2  Error (missing input, unreadable files, etc.).
"""

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML not installed. Run: pip install pyyaml")

# ─── Paths ───────────────────────────────────────────────────────────────────

SKILL_DIR = Path(__file__).parent
VAULT_DIR = Path(os.path.expanduser("~/Documents/Obsidian Vault"))
OBSIDIAN_APPS_DIR = VAULT_DIR / "Job Search" / "Applications"

from config import APPLICATIONS_DIR  # noqa: E402

# ─── Normalization ───────────────────────────────────────────────────────────

# Gender / diversity markers commonly appended to German job titles.
# Matches patterns like (m/w/d), (all genders), (f/m/d), (mwd), (d/w/m), etc.
_GENDER_MARKER_RE = re.compile(
    r"\s*[\(\[]\s*(?:"
    r"all\s*genders"
    r"|m\s*[/\-]\s*w\s*[/\-]\s*d"
    r"|w\s*[/\-]\s*m\s*[/\-]\s*d"
    r"|f\s*[/\-]\s*m\s*[/\-]\s*d"
    r"|d\s*[/\-]\s*w\s*[/\-]\s*m"
    r"|d\s*[/\-]\s*m\s*[/\-]\s*w"
    r"|m\s*[/\-]\s*w"
    r"|w\s*[/\-]\s*m"
    r"|m\s*[/\-]\s*d"
    r"|w\s*[/\-]\s*d"
    r"|d\s*[/\-]\s*m"
    r"|d\s*[/\-]\s*w"
    r"|mwd"
    r"|wmd"
    r"|fmd"
    r"|dwm"
    r"|mfd"
    r"|wfm"
    r"|fmw"
    r"|dfm"
    r"|mdf"
    r"|wmf"
    r"|dwm"
    r")\s*[\)\]]",
    re.IGNORECASE,
)

# Legal-form suffixes stripped from company names for matching.
_LEGAL_SUFFIXES = [
    "gmbh & co. kg",
    "gmbh & co kg",
    "se & co. kg",
    "gmbh",
    "ag & co. kg",
    "ag",
    "se",
    "kg",
    "llc",
    "inc",
    "ltd",
    "s.a.",
    "s.r.l.",
    "b.v.",
    "n.v.",
    "oy",
    "ab",
    "pvt. ltd.",
    "pvt ltd",
    "co.",
    "corp.",
    "corporation",
    "company",
    "limited",
]
_LEGAL_SUFFIX_RE = re.compile(
    r"\s+(?:"
    + "|".join(re.escape(s) for s in _LEGAL_SUFFIXES)
    + r")\s*$",
    re.IGNORECASE,
)


def normalize_company(name: str) -> str:
    """Normalize a company name for fuzzy matching."""
    s = name.lower().strip()
    # Strip legal suffixes (may need multiple passes for compound forms)
    for _ in range(3):
        new = _LEGAL_SUFFIX_RE.sub("", s).strip()
        if new == s:
            break
        s = new
    # Remove punctuation that doesn't carry meaning
    s = re.sub(r"[.,;:'\"&]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_role(name: str) -> str:
    """Normalize a job role/title for fuzzy matching."""
    s = name.strip()
    # Strip gender markers (may be multiple)
    for _ in range(3):
        new = _GENDER_MARKER_RE.sub("", s).strip()
        if new == s:
            break
        s = new
    s = s.lower().strip()
    # Remove punctuation that doesn't carry meaning
    s = re.sub(r"[.,;:'\"&]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fuzzy_ratio(a: str, b: str) -> float:
    """Similarity ratio between two normalized strings (0.0–1.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# Thresholds — company must match strongly, role reasonably.
COMPANY_THRESHOLD = 0.88
ROLE_THRESHOLD = 0.82


def is_match(
    company_a: str,
    role_a: str,
    company_b: str,
    role_b: str,
) -> tuple[bool, float]:
    """Return (matched, combined_score) for two company+role pairs."""
    nc_a = normalize_company(company_a)
    nc_b = normalize_company(company_b)
    nr_a = normalize_role(role_a)
    nr_b = normalize_role(role_b)

    company_score = fuzzy_ratio(nc_a, nc_b)
    role_score = fuzzy_ratio(nr_a, nr_b)

    # Exact normalized match on both is always a hit.
    if nc_a == nc_b and nr_a == nr_b:
        return True, 1.0

    # If company is exact, lower the role bar slightly.
    role_bar = ROLE_THRESHOLD - 0.05 if company_score >= 0.95 else ROLE_THRESHOLD

    matched = company_score >= COMPANY_THRESHOLD and role_score >= role_bar
    combined = (company_score + role_score) / 2
    return matched, combined


# ─── Obsidian vault search ───────────────────────────────────────────────────

_DATE_RE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)\s*$")


def _parse_obsidian_note(note_path: Path) -> dict | None:
    """Parse an Obsidian application note for company, role, date, scores."""
    try:
        text = note_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    company = None
    role = None
    date = None
    ats_pre = None
    ats_post = None

    # Extract from structured fields
    m = re.search(r"\*\*Company:\*\*\s*\[\[([^\]]+)\]\]", text)
    if m:
        company = m.group(1).strip()
    m = re.search(r"\*\*Role:\*\*\s*\[\[([^\]]+)\]\]", text)
    if m:
        role = m.group(1).strip()
    m = re.search(r"\*\*Date:\*\*\s*(\S+)", text)
    if m:
        date = m.group(1).strip()
    m = re.search(r"\*\*ATS Pre-rewrite:\*\*\s*(\d+)", text)
    if m:
        ats_pre = int(m.group(1))
    m = re.search(r"\*\*ATS Post-rewrite:\*\*\s*(\d+)", text)
    if m:
        ats_post = int(m.group(1))

    # Fallback: parse from filename if content fields missing
    stem = note_path.stem  # filename without .md
    if not date:
        m = _DATE_RE.search(stem)
        if m:
            date = m.group(1)
    if not company or not role:
        # Strip trailing date parenthetical, then split on " - " (first occurrence)
        stem_no_date = _DATE_RE.sub("", stem).strip()
        parts = stem_no_date.split(" - ", 1)
        if len(parts) == 2:
            if not company:
                company = parts[0].strip()
            if not role:
                role = parts[1].strip()

    if not company or not role:
        return None

    return {
        "company": company,
        "role": role,
        "date": date or "unknown",
        "ats_pre": ats_pre,
        "ats_post": ats_post,
        "source": "obsidian",
        "path": str(note_path),
    }


def search_obsidian_vault(company: str, role: str) -> list[dict]:
    """Search Obsidian vault Applications notes for matching company+role."""
    matches = []
    if not OBSIDIAN_APPS_DIR.exists():
        return matches

    for note_path in sorted(OBSIDIAN_APPS_DIR.glob("*.md")):
        parsed = _parse_obsidian_note(note_path)
        if not parsed:
            continue
        matched, score = is_match(company, role, parsed["company"], parsed["role"])
        if matched:
            parsed["match_score"] = round(score, 3)
            matches.append(parsed)

    return matches


# ─── Applications filesystem search ──────────────────────────────────────────

def _parse_app_folder_name(folder_name: str) -> tuple[str, str] | None:
    """Parse '[Company] — [Role]' folder name into (company, role)."""
    # Em-dash or en-dash separator
    for sep in ["\u2014", "\u2013", " - "]:
        if sep in folder_name:
            parts = folder_name.split(sep, 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    return None


def _extract_ats_score(app_dir: Path) -> tuple[int | None, int | None]:
    """Extract pre/post ATS scores from ATS_Report.yaml or .md."""
    pre, post = None, None

    yaml_path = app_dir / "ATS_Report.yaml"
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            pre = data.get("ats_score_matrix", {}).get("total_score")
            post_block = data.get("post_rewrite_ats_score", {})
            post = post_block.get("post_rewrite_total_score")
        except Exception:
            pass

    if pre is None or post is None:
        md_path = app_dir / "ATS_Report.md"
        if md_path.exists():
            try:
                text = md_path.read_text(encoding="utf-8")
                if pre is None:
                    m = re.search(r"ATS Pre-rewrite:\*\*\s*(\d+)", text)
                    if m:
                        pre = int(m.group(1))
                if post is None:
                    m = re.search(r"ATS Post-rewrite:\*\*\s*(\d+)", text)
                    if m:
                        post = int(m.group(1))
            except Exception:
                pass

    return pre, post


def _find_app_folders(root: Path) -> list[Path]:
    """Find application folders under root (YYYY/MM/DD/[Company] — [Role]/ or flat)."""
    results = []
    if not root.exists():
        return results
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            # Check if this is a leaf application folder (has ATS_Report)
            if (entry / "ATS_Report.yaml").exists() or (entry / "ATS_Report.md").exists():
                results.append(entry)
            else:
                # Recurse into subdirectories (year/month/day tree or flat)
                results.extend(_find_app_folders(entry))
    return results



def _date_from_path(app_dir: Path) -> str:
    """Extract a date string from a YYYY/MM/DD/[Company] — [Role]/ path tree."""
    parts = app_dir.parts
    # Walk backwards from the app folder name to find date components
    # Expected: .../2026/08/15/[Company] — [Role]
    date_parts = []
    for p in reversed(parts[:-1]):  # exclude the folder name itself
        if p.isdigit() and len(p) <= 4:
            date_parts.insert(0, p)
        else:
            break
    if len(date_parts) == 3:
        return "-".join(date_parts)
    if len(date_parts) == 2:
        return "-".join(date_parts)
    if len(date_parts) == 1:
        return date_parts[0]
    return "unknown"

def search_applications_fs(company: str, role: str, exclude_dir: str | None = None) -> list[dict]:
    """Search the Applications filesystem tree for matching company+role."""
    matches = []
    app_dirs = _find_app_folders(Path(APPLICATIONS_DIR))

    for app_dir in app_dirs:
        if exclude_dir and str(app_dir.resolve()) == str(Path(exclude_dir).resolve()):
            continue

        parsed = _parse_app_folder_name(app_dir.name)
        if not parsed:
            continue

        folder_company, folder_role = parsed
        matched, score = is_match(company, role, folder_company, folder_role)
        if matched:
            pre, post = _extract_ats_score(app_dir)
            matches.append({
                "company": folder_company,
                "role": folder_role,
                "date": _date_from_path(app_dir),
                "ats_pre": pre,
                "ats_post": post,
                "source": "filesystem",
                "path": str(app_dir),
                "match_score": round(score, 3),
            })

    return matches


# ─── Deduplication ───────────────────────────────────────────────────────────
def _dedup(matches: list[dict]) -> list[dict]:
    """Deduplicate matches from different sources by normalized (company, role, date)."""
    seen = {}
    for m in matches:
        key = (
            normalize_company(m["company"]),
            normalize_role(m["role"]),
            m["date"],
        )
        if key not in seen:
            seen[key] = m
        else:
            # Prefer Obsidian source (has parsed scores); merge missing scores
            existing = seen[key]
            if m["source"] == "obsidian" and existing["source"] != "obsidian":
                # Obsidian entry wins, but copy any missing scores from existing
                for field in ("ats_pre", "ats_post"):
                    if existing.get(field) is not None and m.get(field) is None:
                        m[field] = existing[field]
                seen[key] = m
            else:
                # Keep existing; merge scores from new if existing lacks them
                for field in ("ats_pre", "ats_post"):
                    if existing.get(field) is None and m.get(field) is not None:
                        existing[field] = m[field]
    return list(seen.values())


# ─── Input: read current application's company + role ────────────────────────

def read_current_app(app_dir: str) -> tuple[str, str]:
    """Read company and position from ATS_Report.yaml or .md in app_dir."""
    yaml_path = Path(app_dir) / "ATS_Report.yaml"
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        company = data.get("company", "")
        position = data.get("position", "")
        if company and position:
            return company, position

    md_path = Path(app_dir) / "ATS_Report.md"
    if md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        m_c = re.search(r"\*\*Company:\*\*\s*(.+)", text)
        m_p = re.search(r"\*\*Position:\*\*\s*(.+)", text)
        if m_c and m_p:
            return m_c.group(1).strip(), m_p.group(1).strip()

    raise ValueError(f"Could not read company/position from {app_dir}")


# ─── Output ──────────────────────────────────────────────────────────────────

def print_human(matches: list[dict], company: str, role: str) -> int:
    """Print human-readable report. Returns exit code."""
    if not matches:
        print(f"\n  No prior applications found for:")
        print(f"    Company: {company}")
        print(f"    Role:    {role}")
        print()
        return 0

    # Sort by date descending
    sorted_matches = sorted(matches, key=lambda m: m["date"], reverse=True)

    print()
    print(f"  ⚠  DUPLICATE APPLICATION DETECTED  ({len(sorted_matches)} prior)")
    print(f"    Current:  {company} — {role}")
    print()
    for i, m in enumerate(sorted_matches, 1):
        date_str = m["date"]
        scores = ""
        if m["ats_pre"] is not None or m["ats_post"] is not None:
            pre = m["ats_pre"] if m["ats_pre"] is not None else "?"
            post = m["ats_post"] if m["ats_post"] is not None else "?"
            scores = f"  ATS: {pre}→{post}"
        print(f"    {i}. [{date_str}] {m['company']} — {m['role']}{scores}")
        print(f"       Source: {m['source']}  |  Path: {m['path']}")
    print()
    return 1


def print_json(matches: list[dict], company: str, role: str) -> int:
    """Print JSON report. Returns exit code."""
    output = {
        "current": {"company": company, "role": role},
        "duplicates": sorted(matches, key=lambda m: m["date"], reverse=True),
        "count": len(matches),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 1 if matches else 0


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for duplicate applications in Obsidian vault and Applications tree."
    )
    parser.add_argument("app_dir", nargs="?", default=None,
                        help="Path to current application folder (with ATS_Report.yaml/md)")
    parser.add_argument("--company", default=None, help="Company name (if no app_dir)")
    parser.add_argument("--position", default=None, help="Job position/role (if no app_dir)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable text")
    args = parser.parse_args()

    # Determine company + role
    company = args.company
    role = args.position
    app_dir = args.app_dir

    if not company or not role:
        if not app_dir:
            sys.exit("Error: provide either <app_dir> or both --company and --position")
        try:
            company, role = read_current_app(app_dir)
        except (ValueError, OSError) as e:
            sys.exit(f"Error: {e}")

    if not company or not role:
        sys.exit("Error: company and position could not be determined")

    # Search both sources
    matches = []
    matches.extend(search_obsidian_vault(company, role))
    matches.extend(search_applications_fs(company, role, exclude_dir=app_dir))

    # Deduplicate
    matches = _dedup(matches)

    # Output
    if args.json:
        return print_json(matches, company, role)
    else:
        return print_human(matches, company, role)


if __name__ == "__main__":
    sys.exit(main())
