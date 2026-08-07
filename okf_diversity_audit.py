"""
okf_diversity_audit.py — Clustering audit utility for the LLM-CV pipeline.

Scans the Applications/ directory to evaluate historical application
distributions by ATS vendor and application source. Emits warnings when
applicant-firm clustering by vendor or low referral rates are detected,
acting as a buffer against algorithmic monoculture.

Walks the YYYY/MM/DD/[Company] — [Role]/ tree, parses each ATS_Report.yaml
for ats_vendor and application_source, and reports:
  - Vendor clustering: warns if >= DIVERSITY_VENDOR_CLUSTER_THRESHOLD
    applications to the same vendor in the last DIVERSITY_LOOKBACK_DAYS days.
  - Referral rate: warns if referral rate < DIVERSITY_REFERRAL_RATE_MIN.

Usage:
    python okf_diversity_audit.py [applications_dir]

Exit code is always 0 (advisory only — does not block the pipeline).
"""
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    sys.exit("PyYAML not installed. Run: pip install pyyaml")

from config import (
    APPLICATIONS_DIR,
    DIVERSITY_VENDOR_CLUSTER_THRESHOLD,
    DIVERSITY_REFERRAL_RATE_MIN,
    DIVERSITY_LOOKBACK_DAYS,
)


def find_application_folders(root: Path) -> List[Tuple[Path, Optional[date]]]:
    """Find all application folders matching YYYY/MM/DD/[Company] — [Role]/.

    Returns a list of (app_dir, date) tuples. Date is parsed from the path
    segments; None if the path doesn't follow the expected structure.
    """
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
                    try:
                        app_date = date(int(year_dir.name), int(month_dir.name), int(day_dir.name))
                    except ValueError:
                        app_date = None
                    apps.append((app_dir, app_date))
    return apps


def parse_ats_vendor_data(app_dir: Path) -> Dict[str, Optional[str]]:
    """Parse ATS_Report.yaml (or .md) for vendor and application source fields."""
    result = {"ats_vendor": None, "application_source": None}

    ats_yaml = app_dir / "ATS_Report.yaml"
    ats_md = app_dir / "ATS_Report.md"

    if ats_yaml.exists():
        try:
            data = yaml.safe_load(ats_yaml.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                vendor = data.get("ats_vendor")
                source = data.get("application_source")
                if vendor:
                    result["ats_vendor"] = str(vendor).strip()
                if source:
                    result["application_source"] = str(source).strip()
        except Exception:
            pass
    elif ats_md.exists():
        try:
            text = ats_md.read_text(encoding="utf-8")
            import re
            vendor_match = re.search(r"\*\*ATS Vendor:\*\*\s*(.+)", text)
            if vendor_match:
                result["ats_vendor"] = vendor_match.group(1).strip()
            source_match = re.search(r"\*\*Source:\*\*\s*(.+)", text)
            if source_match:
                result["application_source"] = source_match.group(1).strip()
        except Exception:
            pass

    return result


def audit_diversity(applications_dir: str = APPLICATIONS_DIR) -> None:
    """Run the diversity audit and print the status report to stdout."""
    root = Path(applications_dir)
    if not root.exists():
        print(f"\n=== Diversity Audit: Applications directory not found ({root}) ===")
        print("No historical applications to audit. Skipping.")
        return

    all_apps = find_application_folders(root)
    if not all_apps:
        print(f"\n=== Diversity Audit: No application folders found in {root} ===")
        print("Tree should follow YYYY/MM/DD/[Company] — [Role]/ structure.")
        return

    # Cutoff date for the lookback window
    today = date.today()
    cutoff = today - timedelta(days=DIVERSITY_LOOKBACK_DAYS)

    # Collect data
    vendor_counts = defaultdict(int)       # vendor -> count (in lookback window)
    source_counts = defaultdict(int)       # source -> count (in lookback window)
    total_recent = 0
    total_legacy = 0  # apps outside lookback or with missing dates
    missing_vendor = 0
    missing_source = 0

    for app_dir, app_date in all_apps:
        vendor_data = parse_ats_vendor_data(app_dir)

        vendor = vendor_data["ats_vendor"]
        source = vendor_data["application_source"]

        if app_date is None or app_date < cutoff:
            total_legacy += 1
            continue

        total_recent += 1

        if vendor:
            vendor_counts[vendor] += 1
        else:
            missing_vendor += 1

        if source:
            source_counts[source] += 1
        else:
            missing_source += 1

    # ─── Report ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  DIVERSITY AUDIT REPORT")
    print(f"  Applications dir: {root}")
    print(f"  Lookback window:  last {DIVERSITY_LOOKBACK_DAYS} days (since {cutoff.isoformat()})")
    print(f"{'=' * 60}")
    print(f"\n  Total applications found:     {len(all_apps)}")
    print(f"  In lookback window:           {total_recent}")
    print(f"  Outside lookback (legacy):    {total_legacy}")

    # ── Vendor clustering ────────────────────────────────────────────────────
    print(f"\n  --- ATS Vendor Distribution (last {DIVERSITY_LOOKBACK_DAYS} days) ---")
    if vendor_counts:
        for vendor, count in sorted(vendor_counts.items(), key=lambda x: -x[1]):
            flag = " *** WARNING" if count >= DIVERSITY_VENDOR_CLUSTER_THRESHOLD else ""
            print(f"    {vendor}: {count} application(s){flag}")
    else:
        print("    (no vendor data in lookback window)")

    if missing_vendor > 0:
        print(f"    [unknown/missing vendor]: {missing_vendor} application(s)")

    vendor_warnings = [
        v for v, c in vendor_counts.items()
        if c >= DIVERSITY_VENDOR_CLUSTER_THRESHOLD
    ]
    if vendor_warnings:
        print(f"\n  WARNING: Vendor clustering detected for: {', '.join(vendor_warnings)}")
        print(f"    Threshold: >= {DIVERSITY_VENDOR_CLUSTER_THRESHOLD} applications to the same vendor")
        print(f"    in the last {DIVERSITY_LOOKBACK_DAYS} days. Consider diversifying application sources")
        print(f"    or leveraging weak-tie referrals to counter algorithmic monoculture.")

    # ── Referral rate ─────────────────────────────────────────────────────────
    print(f"\n  --- Application Source Distribution (last {DIVERSITY_LOOKBACK_DAYS} days) ---")
    if source_counts:
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            print(f"    {source}: {count} application(s)")
    else:
        print("    (no source data in lookback window)")

    if missing_source > 0:
        print(f"    [unknown/missing source]: {missing_source} application(s)")

    referral_count = source_counts.get("Referral", 0) + source_counts.get("LinkedIn Connection", 0)
    if total_recent > 0:
        referral_rate = referral_count / total_recent
        print(f"\n  Referral rate: {referral_count}/{total_recent} = {referral_rate:.0%}")
        if referral_rate < DIVERSITY_REFERRAL_RATE_MIN:
            print(f"  WARNING: Referral rate {referral_rate:.0%} is below the {DIVERSITY_REFERRAL_RATE_MIN:.0%} threshold.")
            print(f"    Consider reaching out to weak-tie contacts before submitting cold applications.")
    else:
        print("\n  Referral rate: N/A (no applications in lookback window)")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_warnings = len(vendor_warnings) + (1 if total_recent > 0 and referral_count / total_recent < DIVERSITY_REFERRAL_RATE_MIN else 0)
    print(f"\n  Summary: {total_warnings} warning(s)")
    if total_warnings == 0:
        print("  Status: OK — no clustering or referral-rate concerns detected.")
    print(f"{'=' * 60}\n")


def main():
    applications_dir = sys.argv[1] if len(sys.argv) > 1 else APPLICATIONS_DIR
    audit_diversity(applications_dir)
    # Always exit 0 — this is advisory only and should not block the pipeline
    sys.exit(0)


if __name__ == "__main__":
    main()
