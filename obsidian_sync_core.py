#!/usr/bin/env python3
"""
obsidian_sync_core.py — Core logic for syncing LLM-CV applications to Obsidian.

Extracted from the original sync_to_obsidian.py monolith. Contains:
  - Skill and project name normalization (loaded from YAML data files)
  - YAML-format and MD-format application parsers
  - Application folder walker and parser
  - Obsidian note generators (application, entity, index)
  - Full-rebuild sync() and targeted sync_targeted()

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
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    sys.exit("PyYAML not installed. Run: pip install pyyaml")

# Folder-sort logic lives in its own module
from obsidian_folder_sort import _move_into_tree

from config import APPLICATIONS_DIR
VAULT_DIR = Path(os.path.expanduser("~/Documents/Obsidian Vault"))
OUTPUT_ROOT = VAULT_DIR / "Job Search"

# ─── Data file paths ──────────────────────────────────────────────────────────

_SKILL_MAPPINGS_PATH = Path(__file__).parent / "okf" / "skill_mappings.yaml"
_PROJECT_MAPPINGS_PATH = Path(__file__).parent / "okf" / "project_mappings.yaml"

# ─── Helpers ──────────────────────────────────────────────────────────────────

EM_DASH = "\u2014"  # —
EN_DASH = "\u2013"  # –


def slugify(name: str) -> str:
    """Sanitize a string for use as an Obsidian note filename."""
    # Replace characters that are problematic in filenames / wikilinks
    name = name.replace(EM_DASH, "-").replace(EN_DASH, "-")
    # Strip characters Obsidian wikilinks don't handle well
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ─── Skill / project normalization (loaded from YAML data files) ──────────────

def _load_skill_mappings(path: Path) -> list:
    """Load skill normalization rules from the YAML data file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("rules", [])


def _load_project_mappings(path: Path) -> tuple:
    """Load project junk patterns and canonical rules from the YAML data file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    junk_patterns = data.get("junk_patterns", [])
    rules = data.get("rules", [])
    return junk_patterns, rules


# Cache at module import time
_SKILL_RULES = _load_skill_mappings(_SKILL_MAPPINGS_PATH)
_PROJECT_JUNK_PATTERNS, _PROJECT_RULES = _load_project_mappings(_PROJECT_MAPPINGS_PATH)


def _match_skill_rule(lower: str, rule: dict) -> bool:
    """Check if a lowercased skill string matches a rule.

    Positive conditions (exact, prefix, contains) are ORed — any one matching
    is sufficient.  Negative conditions (exclude_contains) are ANDed — all must
    be absent for the rule to match.
    """
    # Check positive conditions (OR)
    positive_match = False
    has_positive = False
    exact = rule.get("exact")
    if exact:
        has_positive = True
        if lower in exact:
            positive_match = True
    prefix = rule.get("prefix")
    if prefix:
        has_positive = True
        if any(lower.startswith(p) for p in prefix):
            positive_match = True
    contains = rule.get("contains")
    if contains:
        has_positive = True
        if any(c in lower for c in contains):
            positive_match = True
    if not has_positive or not positive_match:
        return False
    # Check negative conditions (AND — all must be absent)
    exclude_contains = rule.get("exclude_contains")
    if exclude_contains:
        if any(x in lower for x in exclude_contains):
            return False
    return True


def normalize_skill(raw: str) -> str:
    """Normalize a skill string from a JD into a canonical short name."""
    s = raw.strip()
    # Remove parenthetical qualifiers: "SQL (advanced)" → "SQL"
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    # Remove leading bullets / numbering
    s = re.sub(r"^[-*]\s*", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Common normalizations
    lower = s.lower()
    for rule in _SKILL_RULES:
        if _match_skill_rule(lower, rule):
            return rule["canonical"]
    # Title-case fallback for anything else
    return s.title() if s.islower() else s


def normalize_project(raw: str) -> str:
    """Normalize a project name from portfolio/resume into a canonical form.

    Maps the many LLM-generated name variants to canonical project names using
    keyword matching. Returns empty string for junk entries that aren't projects.
    """
    p = raw.strip()
    # Remove surrounding quotes
    p = p.strip('"').strip("'")
    # Remove trailing tools annotation if present
    p = re.sub(r"\s*[—–-]\s*Tools?:.*$", "", p)
    p = re.sub(r"\s*\*Tools?:.*$", "", p)
    # Remove trailing periods
    p = p.rstrip(".")
    # Collapse whitespace
    p = re.sub(r"\s+", " ", p).strip()
    # Remove emoji prefixes (any non-ASCII char at start)
    p = re.sub(r"^[\U0001f000-\U0001ffff\u2600-\u27bf]+\s*", "", p)

    # Junk entries — return empty string so caller can skip
    lower = p.lower()
    for jp in _PROJECT_JUNK_PATTERNS:
        if lower.startswith(jp):
            return ""

    # Canonical project mapping via keyword matching
    # Order matters — more specific patterns first
    for rule in _PROJECT_RULES:
        keywords = rule["keywords"]
        canonical_name = rule["canonical"]
        if all(kw in lower for kw in keywords):
            return canonical_name

    # If no match, return the cleaned-up original
    return p


# ─── YAML-format parsers ──────────────────────────────────────────────────────

def parse_ats_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = {
        "company": data.get("company", ""),
        "position": data.get("position", ""),
        "pre_total": None,
        "post_total": None,
        "score_gate": None,
        "detractors": [],
        "skills_to_add": [],
        "skills_to_remove": [],
        "ats_vendor": data.get("ats_vendor") or "",
        "application_source": data.get("application_source") or "",
        "weak_tie_contact": data.get("weak_tie_contact") or "",
    }
    matrix = data.get("ats_score_matrix", {})
    if isinstance(matrix, dict):
        total = matrix.get("total_score")
        if total is not None:
            result["pre_total"] = int(total)
    post = data.get("post_rewrite_ats_score", {})
    if isinstance(post, dict):
        pmatrix = post.get("ats_score_matrix", {})
        if isinstance(pmatrix, dict):
            ptotal = pmatrix.get("total_score")
            if ptotal is not None:
                result["post_total"] = int(ptotal)
    detractors = data.get("core_score_detractors", [])
    if isinstance(detractors, list):
        result["detractors"] = [str(d) for d in detractors]
    blueprint = data.get("improvement_blueprint", {})
    if isinstance(blueprint, dict):
        gate = blueprint.get("ats_threshold_calibration", {})
        if isinstance(gate, dict):
            verdict = gate.get("score_gate_verdict")
            if verdict:
                result["score_gate"] = str(verdict)
        tuning = blueprint.get("technical_skills_tuning", {})
        if isinstance(tuning, dict):
            add = tuning.get("add", [])
            if isinstance(add, list):
                result["skills_to_add"] = [str(s) for s in add]
            rem = tuning.get("remove", [])
            if isinstance(rem, list):
                result["skills_to_remove"] = [str(s) for s in rem]
    return result


def parse_jd_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = {
        "company": data.get("company", ""),
        "position": data.get("position", ""),
        "skills": [],
        "location": data.get("location", ""),
    }
    sections = data.get("sections", [])
    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            title = (sec.get("title") or "").lower()
            # Only extract skills from tech stack / tooling sections
            # Requirement bullets are full sentences, not skill names
            if "tech stack" in title or "tooling" in title or "technology" in title:
                bullets = sec.get("bullets", [])
                if isinstance(bullets, list):
                    result["skills"].extend(str(b) for b in bullets)
    return result


def parse_resume_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    projects = []
    for p in data.get("projects", []):
        if isinstance(p, dict):
            projects.append(p.get("name", ""))
    return {"projects": [np for np in (normalize_project(p) for p in projects if p) if np]}


# ─── MD-format parsers ─────────────────────────────────────────────────────────

def parse_ats_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    result = {
        "company": "",
        "position": "",
        "pre_total": None,
        "post_total": None,
        "score_gate": None,
        "detractors": [],
        "skills_to_add": [],
        "skills_to_remove": [],
        "ats_vendor": "",
        "application_source": "",
        "weak_tie_contact": "",
    }

    # Title: "# ATS Analysis Report: Company — Role"
    title_match = re.search(r"^#\s+.*?:\s*(.+)$", text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        parts = re.split(r"[—–-]", title, maxsplit=1)
        if len(parts) == 2:
            result["company"] = parts[0].strip()
            result["position"] = parts[1].strip()

    # Scoring table — find all table rows with scores
    # Pattern: | **Category** | **max** | criteria | **score** |
    # Bold markers may or may not be present around numbers
    score_rows = re.findall(
        r"\|\s*\*{0,2}([^|*]+)\*{0,2}\s*\|\s*\*{0,2}:?[0-9]+\*{0,2}\s*\|[^|]*\|\s*\*{0,2}([0-9]+)\*{0,2}\s*\|",
        text,
    )
    if score_rows:
        total_row = [r for r in score_rows if "total" in r[0].lower()]
        if total_row:
            result["pre_total"] = int(total_row[0][1])

    # Post-rewrite score — look for a second scoring table or "Post-Rewrite" section
    post_section = re.search(r"post.?rewrite.*?(?:TOTAL|total).*?(\d+)\s*/?\s*100", text, re.IGNORECASE | re.DOTALL)
    if post_section:
        result["post_total"] = int(post_section.group(1))
    else:
        # Try: "Post-Rewrite ATS Score: XX" or "Post-rewrite: XX"
        m = re.search(r"post.?rewrite.*?(\d{2,3})", text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if val <= 100:
                result["post_total"] = val

    # Score gate verdict
    gate_match = re.search(r"(PROCEED|REVIEW|HOLD)", text, re.IGNORECASE)
    if gate_match:
        result["score_gate"] = gate_match.group(1).upper()
    elif re.search(r"meets_target:\s*true", text, re.IGNORECASE):
        result["score_gate"] = "PROCEED"
    elif re.search(r"meets_target:\s*false", text, re.IGNORECASE):
        result["score_gate"] = "REVIEW"

    # Core detractors — bullet list under "## 3. Core Score Detractors" or similar
    detractor_section = re.search(
        r"##\s*\d*\.?\s*Core Score Detractors\s*\n(.*?)(?=\n##|\Z)",
        text,
        re.DOTALL,
    )
    if detractor_section:
        bullets = re.findall(r"^[-*]\s+(.+)$", detractor_section.group(1), re.MULTILINE)
        # Clean bold markers
        result["detractors"] = [re.sub(r"\*\*([^*]+)\*\*:?\s*", r"\1: ", b).strip() for b in bullets]

    # Skills to add / remove from "Technical Skills Tuning" section
    tuning_section = re.search(
        r"Skills to Add:?\s*\n(.*?)(?:\*\*Skills to Remove|\n##|\Z)",
        text,
        re.DOTALL,
    )
    if tuning_section:
        bullets = re.findall(r"^[-*]\s+(.+)$", tuning_section.group(1), re.MULTILINE)
        result["skills_to_add"] = [b.strip().strip("*") for b in bullets]

    remove_section = re.search(
        r"Skills to Remove:?\s*\n(.*?)(?:\*\*Skills to Reframe|\n##|\Z)",
        text,
        re.DOTALL,
    )
    if remove_section:
        bullets = re.findall(r"^[-*]\s+(.+)$", remove_section.group(1), re.MULTILINE)
        result["skills_to_remove"] = [b.strip().strip("*") for b in bullets]

    # ATS Vendor, Application Source, Weak-tie Contact
    vendor_match = re.search(r"\*\*ATS Vendor:\*\*\s*(.+)", text)
    if vendor_match:
        result["ats_vendor"] = vendor_match.group(1).strip()
    source_match = re.search(r"\*\*Source:\*\*\s*(.+)", text)
    if source_match:
        result["application_source"] = source_match.group(1).strip()
    contact_match = re.search(r"\*\*Referral Contact:\*\*\s*(.+)", text)
    if contact_match:
        result["weak_tie_contact"] = contact_match.group(1).strip()

    return result


def parse_jd_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    result = {"company": "", "position": "", "skills": [], "location": ""}

    # Title: "# Company — Role"
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        parts = re.split(r"[—–-]", title, maxsplit=1)
        if len(parts) == 2:
            result["company"] = parts[0].strip()
            result["position"] = parts[1].strip()

    # Tech stack section — this is the primary source of skill names
    tech_section = re.search(
        r"##\s*.*?(?:Tech Stack|Tooling|Technology).*?\n(.*?)(?=\n##|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if tech_section:
        block = tech_section.group(1)
        bullets = re.findall(r"^[-*]\s+(.+)$", block, re.MULTILINE)
        for b in bullets:
            # Strip bold markers: "**Languages:** Python, SQL" → "Languages: Python, SQL"
            b_clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", b).strip()
            # "Languages: Python, SQL" → split on colon, then commas
            if ":" in b_clean:
                parts = b_clean.split(":", 1)
                items = [i.strip() for i in parts[1].split(",")]
                result["skills"].extend(items)
            else:
                # Single-item bullet — may still be comma-separated
                items = [i.strip() for i in b_clean.split(",")]
                result["skills"].extend(items)

    return result


def parse_resume_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    projects = []
    # Projects are bold lines between **PROJECTS** and **PROFESSIONAL EXPERIENCE**
    proj_section = re.search(
        r"\*\*PROJECTS\*\*\s*\n(.*?)(?:\*\*PROFESSIONAL EXPERIENCE\*\*|\Z)",
        text,
        re.DOTALL,
    )
    if proj_section:
        # Project names are bold: **Project Name** *Tools: ...*
        names = re.findall(r"^\*\*(.+?)\*\*", proj_section.group(1), re.MULTILINE)
        projects = [np for np in (normalize_project(n) for n in names) if np]
    return {"projects": projects}


def parse_project_info_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Project names are H1 headers: "# Project Name"
    names = re.findall(r"^#\s+(.+)$", text, re.MULTILINE)
    # Skip the first "# Tailored Project Portfolio" header
    projects = []
    for n in names:
        n = n.strip()
        if "tailored project portfolio" in n.lower():
            continue
        np = normalize_project(n)
        if np:
            projects.append(np)
    return {"projects": projects}


# ─── Application folder walker ────────────────────────────────────────────────

def find_application_folders(root: Path) -> list:
    """Find all application folders matching YYYY/MM/DD/[Company] — [Role]/."""
    apps = []
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
                    if not app_dir.is_dir():
                        continue
                    apps.append(app_dir)
    return apps


def parse_application(app_dir: Path) -> Optional[dict]:
    """Parse a single application folder, handling both YAML and MD formats."""
    # Determine format
    ats_yaml = app_dir / "ATS_Report.yaml"
    ats_md = app_dir / "ATS_Report.md"
    jd_yaml = app_dir / "Job_Description.yaml"
    jd_md = app_dir / "Job_Description.md"
    resume_yaml = app_dir / "Resume.yaml"
    resume_md = app_dir / "Resume.md"
    project_info = app_dir / "project_info.md"

    # Parse ATS report
    if ats_yaml.exists():
        ats = parse_ats_yaml(ats_yaml)
    elif ats_md.exists():
        ats = parse_ats_md(ats_md)
    else:
        return None  # Not a valid application folder

    # Parse JD
    if jd_yaml.exists():
        jd = parse_jd_yaml(jd_yaml)
    elif jd_md.exists():
        jd = parse_jd_md(jd_md)
    else:
        jd = {"company": "", "position": "", "skills": []}

    # Parse projects
    projects = []
    if project_info.exists():
        projects = parse_project_info_md(project_info)["projects"]
    elif resume_yaml.exists():
        projects = parse_resume_yaml(resume_yaml)["projects"]
    elif resume_md.exists():
        projects = parse_resume_md(resume_md)["projects"]

    # Extract date from path
    parts = app_dir.parts
    # .../Applications/YYYY/MM/DD/[Company]/
    date_str = ""
    try:
        # Find the Applications part and take next 3 segments
        idx = parts.index("Applications")
        year = parts[idx + 1]
        month = parts[idx + 2]
        day = parts[idx + 3]
        date_str = f"{year}-{month}-{day}"
    except (ValueError, IndexError):
        pass

    # Extract company and role from folder name as fallback
    folder_name = app_dir.name
    folder_parts = re.split(r"[—–]", folder_name, maxsplit=1)
    if len(folder_parts) == 2:
        folder_company = folder_parts[0].strip()
        folder_role = folder_parts[1].strip()
    else:
        folder_company = folder_name
        folder_role = ""

    company = ats.get("company") or jd.get("company") or folder_company
    position = ats.get("position") or jd.get("position") or folder_role

    # Normalize skills
    raw_skills = jd.get("skills", [])
    skills = []
    seen = set()
    for s in raw_skills:
        norm = normalize_skill(s)
        if norm and norm.lower() not in seen and len(norm) > 1:
            seen.add(norm.lower())
            skills.append(norm)

    return {
        "folder": app_dir,
        "company": company.strip(),
        "position": position.strip(),
        "date": date_str,
        "pre_total": ats.get("pre_total"),
        "post_total": ats.get("post_total"),
        "score_gate": ats.get("score_gate"),
        "detractors": ats.get("detractors", []),
        "skills_to_add": ats.get("skills_to_add", []),
        "skills_to_remove": ats.get("skills_to_remove", []),
        "ats_vendor": ats.get("ats_vendor", ""),
        "application_source": ats.get("application_source", ""),
        "weak_tie_contact": ats.get("weak_tie_contact", ""),
        "skills": skills,
        "projects": projects,
    }


# ─── Obsidian note generators ─────────────────────────────────────────────────

def app_note_name(app: dict) -> str:
    """Filename for an application note."""
    return slugify(f"{app['company']} — {app['position']} ({app['date']})")


def generate_application_note(app: dict) -> str:
    lines = []
    lines.append(f"# {app['company']} — {app['position']} ({app['date']})")
    lines.append("")
    lines.append(f"**Date:** {app['date']}")
    lines.append(f"**Company:** [[{app['company']}]]")
    lines.append(f"**Role:** [[{app['position']}]]")
    if app.get("ats_vendor"):
        lines.append(f"**ATS Vendor:** [[{app['ats_vendor']}]]")
    if app.get("application_source"):
        lines.append(f"**Source:** [[{app['application_source']}]]")
    lines.append(f"**Referral Contact:** {app.get('weak_tie_contact') or 'None'}")
    if app["pre_total"] is not None:
        lines.append(f"**ATS Pre-rewrite:** {app['pre_total']}/100")
    if app["post_total"] is not None:
        lines.append(f"**ATS Post-rewrite:** {app['post_total']}/100")
    if app["score_gate"]:
        lines.append(f"**Score Gate:** {app['score_gate']}")
    lines.append("")

    if app["skills"]:
        lines.append("## Skills Required")
        for s in app["skills"]:
            lines.append(f"- [[{s}]]")
        lines.append("")

    if app["projects"]:
        lines.append("## Projects Used")
        for p in app["projects"]:
            lines.append(f"- [[{p}]]")
        lines.append("")

    if app["detractors"]:
        lines.append("## Core Detractors")
        for d in app["detractors"]:
            lines.append(f"- {d}")
        lines.append("")

    if app["skills_to_add"]:
        lines.append("## Skills to Add")
        for s in app["skills_to_add"]:
            lines.append(f"- {s}")
        lines.append("")

    if app["skills_to_remove"]:
        lines.append("## Skills to Remove")
        for s in app["skills_to_remove"]:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)


def generate_entity_note(title: str, backlinks_key: str, backlinks: list, extra_sections: dict = None) -> str:
    lines = [f"# {title}", ""]
    if backlinks:
        lines.append(f"## {backlinks_key}")
        for b in sorted(backlinks):
            lines.append(f"- [[{b}]]")
        lines.append("")
    if extra_sections:
        for heading, items in extra_sections.items():
            if items:
                lines.append(f"## {heading}")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")
    return "\n".join(lines)


def generate_index_note(title: str, entries: list) -> str:
    lines = [f"# {title}", ""]
    for e in sorted(entries):
        lines.append(f"- [[{e}]]")
    lines.append("")
    return "\n".join(lines)


# ─── Main sync logic ──────────────────────────────────────────────────────────

def sync(dry_run: bool = False, verbose: bool = False) -> None:
    app_folders = find_application_folders(APPLICATIONS_DIR)
    if verbose:
        print(f"Found {len(app_folders)} application folders")

    applications = []
    for folder in app_folders:
        app = parse_application(folder)
        if app:
            applications.append(app)
            if verbose:
                print(f"  Parsed: {app['company']} — {app['position']} ({app['date']}) "
                      f"pre={app['pre_total']} post={app['post_total']} "
                      f"skills={len(app['skills'])} projects={len(app['projects'])}")
        elif verbose:
            print(f"  Skipped (no ATS report): {folder.name}")

    if not applications:
        print("No valid applications found.")
        return

    # Build aggregation maps
    company_apps = defaultdict(list)   # company → [app_note_name]
    role_apps = defaultdict(list)      # role → [app_note_name]
    skill_apps = defaultdict(list)     # skill → [app_note_name]
    project_apps = defaultdict(list)   # project → [app_note_name]
    vendor_apps = defaultdict(list)    # ats_vendor → [app_note_name]
    source_apps = defaultdict(list)    # application_source → [app_note_name]

    for app in applications:
        note_name = app_note_name(app)
        company_apps[app["company"]].append(note_name)
        role_apps[app["position"]].append(note_name)
        for s in app["skills"]:
            skill_apps[s].append(note_name)
        for p in app["projects"]:
            project_apps[p].append(note_name)
        if app.get("ats_vendor"):
            vendor_apps[app["ats_vendor"]].append(note_name)
        if app.get("application_source"):
            source_apps[app["application_source"]].append(note_name)

    # Prepare output directories
    dirs = {
        "applications": OUTPUT_ROOT / "Applications",
        "companies": OUTPUT_ROOT / "Companies",
        "roles": OUTPUT_ROOT / "Roles",
        "skills": OUTPUT_ROOT / "Skills",
        "projects": OUTPUT_ROOT / "Projects",
        "vendors": OUTPUT_ROOT / "Vendors",
        "sources": OUTPUT_ROOT / "Sources",
    }

    if dry_run:
        print("\n=== DRY RUN ===")
        print(f"Would write {len(applications)} application notes")
        print(f"Would write {len(company_apps)} company notes")
        print(f"Would write {len(role_apps)} role notes")
        print(f"Would write {len(skill_apps)} skill notes")
        print(f"Would write {len(project_apps)} project notes")
        print(f"Would write {len(vendor_apps)} vendor notes")
        print(f"Would write {len(source_apps)} source notes")
        print(f"Output root: {OUTPUT_ROOT}")
        print("\nSample application note:")
        print("---")
        print(generate_application_note(applications[-1]))
        return

    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    written = 0

    # Write application notes
    for app in applications:
        note_path = dirs["applications"] / f"{app_note_name(app)}.md"
        note_path.write_text(generate_application_note(app), encoding="utf-8")
        written += 1

    # Write company notes
    for company, apps in sorted(company_apps.items()):
        note_path = dirs["companies"] / f"{slugify(company)}.md"
        note_path.write_text(
            generate_entity_note(company, "Applications", apps),
            encoding="utf-8",
        )
        written += 1

    # Write role notes
    for role, apps in sorted(role_apps.items()):
        note_path = dirs["roles"] / f"{slugify(role)}.md"
        note_path.write_text(
            generate_entity_note(role, "Applications", apps),
            encoding="utf-8",
        )
        written += 1

    # Write skill notes
    for skill, apps in sorted(skill_apps.items()):
        note_path = dirs["skills"] / f"{slugify(skill)}.md"
        note_path.write_text(
            generate_entity_note(skill, "Required By", apps),
            encoding="utf-8",
        )
        written += 1

    # Write project notes
    for project, apps in sorted(project_apps.items()):
        note_path = dirs["projects"] / f"{slugify(project)}.md"
        note_path.write_text(
            generate_entity_note(project, "Used In", apps),
            encoding="utf-8",
        )
        written += 1

    # Write vendor notes
    for vendor, apps in sorted(vendor_apps.items()):
        note_path = dirs["vendors"] / f"{slugify(vendor)}.md"
        note_path.write_text(
            generate_entity_note(vendor, "Applications", apps),
            encoding="utf-8",
        )
        written += 1

    # Write source notes
    for source, apps in sorted(source_apps.items()):
        note_path = dirs["sources"] / f"{slugify(source)}.md"
        note_path.write_text(
            generate_entity_note(source, "Applications", apps),
            encoding="utf-8",
        )
        written += 1

    # Write index notes
    indexes = {
        "Applications Index.md": [app_note_name(a) for a in applications],
        "Companies Index.md": list(company_apps.keys()),
        "Roles Index.md": list(role_apps.keys()),
        "Skills Index.md": list(skill_apps.keys()),
        "Projects Index.md": list(project_apps.keys()),
        "Vendors Index.md": list(vendor_apps.keys()),
        "Sources Index.md": list(source_apps.keys()),
    }
    for filename, entries in indexes.items():
        note_path = OUTPUT_ROOT / filename
        note_path.write_text(generate_index_note(filename.replace(".md", ""), entries), encoding="utf-8")
        written += 1

    print(f"Sync complete: {written} notes written to {OUTPUT_ROOT}")
    print(f"  {len(applications)} applications")
    print(f"  {len(company_apps)} companies")
    print(f"  {len(role_apps)} roles")
    print(f"  {len(skill_apps)} skills")
    print(f"  {len(project_apps)} projects")
    print(f"  {len(vendor_apps)} vendors")
    print(f"  {len(source_apps)} sources")
    print(f"  7 index notes")
    print(f"\nOpen Obsidian -> Job Search -> graph view to see the mind map.")


# ─── Entry point helpers ──────────────────────────────────────────────────────

def _patch_index_note(note_path: Path, new_entries: list) -> bool:
    """Append new entries to an existing index note, deduplicating.

    Returns True if the file was written (or rewritten), False if nothing changed.
    """
    existing_entries = []
    if note_path.exists():
        text = note_path.read_text(encoding="utf-8")
        # Parse existing entries: lines starting with "- [["
        for line in text.splitlines():
            m = re.match(r"^- \[\[(.+?)\]\]", line)
            if m:
                existing_entries.append(m.group(1))

    existing_set = set(existing_entries)
    added = [e for e in new_entries if e not in existing_set]
    if not added and existing_set:
        # Nothing new to add, and the file already exists — skip
        return False

    all_entries = sorted(set(existing_entries + new_entries))
    title = note_path.stem  # filename without .md
    note_path.write_text(generate_index_note(title, all_entries), encoding="utf-8")
    return True


def _patch_entity_note(note_path: Path, title: str, backlinks_key: str, new_backlinks: list) -> bool:
    """Append new backlinks to an existing entity note, deduplicating.

    Returns True if the file was written, False if nothing changed.
    """
    existing_backlinks = []
    if note_path.exists():
        text = note_path.read_text(encoding="utf-8")
        # Find the backlinks section and parse entries
        in_section = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_section = (backlinks_key in line)
                continue
            if in_section:
                m = re.match(r"^- \[\[(.+?)\]\]", line)
                if m:
                    existing_backlinks.append(m.group(1))

    existing_set = set(existing_backlinks)
    added = [b for b in new_backlinks if b not in existing_set]
    if not added and existing_set:
        return False

    all_backlinks = sorted(set(existing_backlinks + new_backlinks))
    note_path.write_text(
        generate_entity_note(title, backlinks_key, all_backlinks),
        encoding="utf-8",
    )
    return True


def sync_targeted(target_folder: str, dry_run: bool = False, verbose: bool = False, do_sort: bool = False) -> None:
    """Sync a single application folder to the Obsidian vault (incremental).

    Writes/updates only the notes for this application and patches the relevant
    index and entity notes. Much faster than a full rebuild for a single new
    application.
    """
    target = Path(target_folder)
    if not target.is_dir():
        print(f"Error: Target folder not found: {target_folder}", file=sys.stderr)
        sys.exit(1)

    app = parse_application(target)
    if not app:
        print(f"Error: Could not parse application (no ATS report found in {target_folder})", file=sys.stderr)
        sys.exit(1)

    # If date is empty (folder not yet sorted), use creation date as fallback
    if not app["date"]:
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(os.path.getctime(str(target)))
            app["date"] = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
        except Exception:
            app["date"] = "0000-00-00"

    if verbose:
        print(f"Targeted sync: {app['company']} - {app['position']} ({app['date']})")

    note_name = app_note_name(app)

    # Prepare output directories
    dirs = {
        "applications": OUTPUT_ROOT / "Applications",
        "companies": OUTPUT_ROOT / "Companies",
        "roles": OUTPUT_ROOT / "Roles",
        "skills": OUTPUT_ROOT / "Skills",
        "projects": OUTPUT_ROOT / "Projects",
        "vendors": OUTPUT_ROOT / "Vendors",
        "sources": OUTPUT_ROOT / "Sources",
    }

    if dry_run:
        print("\n=== DRY RUN (targeted) ===")
        print(f"Would write application note: {note_name}")
        print(f"Would patch entity notes for: company={app['company']}, role={app['position']}")
        print(f"  skills={app['skills']}, projects={app['projects']}")
        if app.get("ats_vendor"):
            print(f"  vendor={app['ats_vendor']}")
        if app.get("application_source"):
            print(f"  source={app['application_source']}")
        print(f"Would patch 7 index notes")
        if do_sort:
            print(f"Would sort folder into YYYY/MM/DD tree")
        return

    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    written = 0

    # 1. Write the application note (overwrite — it's this app's own note)
    note_path = dirs["applications"] / f"{note_name}.md"
    note_path.write_text(generate_application_note(app), encoding="utf-8")
    written += 1
    if verbose:
        print(f"  Wrote application note: {note_path.name}")

    # 2. Patch entity notes (company, role, skills, projects, vendor, source)
    entity_updates = [
        (dirs["companies"], app["company"], "Applications", [note_name]),
        (dirs["roles"], app["position"], "Applications", [note_name]),
    ]
    for skill in app["skills"]:
        entity_updates.append((dirs["skills"], skill, "Required By", [note_name]))
    for project in app["projects"]:
        entity_updates.append((dirs["projects"], project, "Used In", [note_name]))
    if app.get("ats_vendor"):
        entity_updates.append((dirs["vendors"], app["ats_vendor"], "Applications", [note_name]))
    if app.get("application_source"):
        entity_updates.append((dirs["sources"], app["application_source"], "Applications", [note_name]))

    for dir_path, title, backlinks_key, backlinks in entity_updates:
        ent_path = dir_path / f"{slugify(title)}.md"
        if _patch_entity_note(ent_path, title, backlinks_key, backlinks):
            written += 1
            if verbose:
                print(f"  Patched entity note: {ent_path.name}")
        elif verbose:
            print(f"  Entity note unchanged: {ent_path.name}")

    # 3. Patch all 7 index notes
    index_updates = {
        "Applications Index.md": [note_name],
        "Companies Index.md": [app["company"]],
        "Roles Index.md": [app["position"]],
        "Skills Index.md": list(app["skills"]),
        "Projects Index.md": list(app["projects"]),
        "Vendors Index.md": [app["ats_vendor"]] if app.get("ats_vendor") else [],
        "Sources Index.md": [app["application_source"]] if app.get("application_source") else [],
    }
    for filename, entries in index_updates.items():
        idx_path = OUTPUT_ROOT / filename
        if entries and _patch_index_note(idx_path, entries):
            written += 1
            if verbose:
                print(f"  Patched index: {filename}")

    print(f"Targeted sync complete: {written} notes written/patched in {OUTPUT_ROOT}")
    print(f"  Application: {app['company']} - {app['position']} ({app['date']})")

    # 4. Sort the folder into the YYYY/MM/DD tree (Phase 4.2)
    if do_sort:
        try:
            new_path = _move_into_tree(str(target), applications_dir=str(APPLICATIONS_DIR))
            if new_path:
                print(f"  Sorted to: {os.path.relpath(new_path, str(APPLICATIONS_DIR))}")
            else:
                if verbose:
                    print(f"  Sort: folder already sorted or skipped")
        except Exception as e:
            print(f"  Warning: Folder sort failed (non-blocking): {e}", file=sys.stderr)
