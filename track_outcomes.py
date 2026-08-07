"""
track_outcomes.py — Application outcome & channel tracker.

Problem this solves: as of Aug 2026, 302 application folders had ATS_Report.yaml
scoring data but zero recorded outcomes (interview/rejection/ghosted) and 63% had
no logged application_source. You cannot tune a funnel you don't measure. This
script is a thin, standalone layer on top of the existing Applications/ tree —
it does NOT touch ATS_Report.yaml, Resume.yaml, or any pipeline-owned file.

It writes/reads one new file per application folder: Application_Status.yaml.

Usage
-----
Record an outcome for one application:
    python track_outcomes.py set "Trassets GmbH — BI Engineer" interview --source referral --notes "warm intro via LinkedIn"

Valid --status values: sent, viewed, interview, second_round, offer, rejected, ghosted
Valid --source values: cold_apply, referral, linkedin_connection, direct

List every application missing a status (to catch up on backlog):
    python track_outcomes.py pending

Weekly/anytime digest — response rate by archetype and by channel:
    python track_outcomes.py report

Digest for a specific window only:
    python track_outcomes.py report --since 2026-07-01
"""
import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

import yaml

APPLICATIONS_ROOT = Path("/home/sagar/Applications")

VALID_STATUSES = ["sent", "viewed", "interview", "second_round", "offer", "rejected", "ghosted"]
VALID_SOURCES = ["cold_apply", "referral", "linkedin_connection", "direct"]

# Statuses that count as "the application got a human response" for response-rate math.
RESPONSE_STATUSES = {"interview", "second_round", "offer"}


def _find_app_folder(name_fragment: str) -> Path:
    """Locate an application folder by exact name or substring match under the Year/Month/Day tree."""
    candidates = [p for p in APPLICATIONS_ROOT.rglob("*") if p.is_dir() and name_fragment.lower() in p.name.lower()]
    # Only leaf application folders contain ATS_Report.yaml or Job_Description.yaml
    candidates = [c for c in candidates if (c / "ATS_Report.yaml").exists() or (c / "Job_Description.yaml").exists()]
    if not candidates:
        raise SystemExit(f"No application folder found matching '{name_fragment}'")
    if len(candidates) > 1:
        listing = "\n".join(f"  - {c}" for c in candidates)
        raise SystemExit(f"Multiple folders match '{name_fragment}', be more specific:\n{listing}")
    return candidates[0]


def _load_ats_report(folder: Path) -> dict:
    f = folder / "ATS_Report.yaml"
    if not f.exists():
        return {}
    try:
        data = yaml.safe_load(f.read_text(errors="ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def cmd_set(args: argparse.Namespace) -> int:
    folder = _find_app_folder(args.company)
    status_file = folder / "Application_Status.yaml"

    existing = {}
    if status_file.exists():
        try:
            existing = yaml.safe_load(status_file.read_text(errors="ignore")) or {}
        except Exception:
            existing = {}

    history = existing.get("history", [])
    history.append({
        "status": args.status,
        "date": dt.date.today().isoformat(),
        "notes": args.notes or "",
    })

    record = {
        "company_folder": folder.name,
        "status": args.status,
        "application_source": args.source or existing.get("application_source") or "unlogged",
        "last_updated": dt.date.today().isoformat(),
        "history": history,
    }

    status_file.write_text(yaml.dump(record, allow_unicode=True, sort_keys=False))
    print(f"Recorded status='{args.status}' source='{record['application_source']}' -> {status_file}")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    all_folders = [
        p.parent for p in APPLICATIONS_ROOT.rglob("ATS_Report.yaml")
    ]
    missing = [f for f in all_folders if not (f / "Application_Status.yaml").exists()]
    missing.sort(key=lambda p: str(p))
    print(f"{len(missing)} of {len(all_folders)} application folders have no recorded status:\n")
    for f in missing:
        print(f"  {f}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    since = dt.date.fromisoformat(args.since) if args.since else None

    status_files = list(APPLICATIONS_ROOT.rglob("Application_Status.yaml"))
    if not status_files:
        print("No Application_Status.yaml records found yet. Use 'set' to start recording outcomes.")
        return 0

    by_archetype = defaultdict(lambda: {"total": 0, "responded": 0})
    by_source = defaultdict(lambda: {"total": 0, "responded": 0})
    status_counts = defaultdict(int)
    total = 0

    for sf in status_files:
        try:
            rec = yaml.safe_load(sf.read_text(errors="ignore")) or {}
        except Exception:
            continue
        last_updated = rec.get("last_updated")
        if since and last_updated:
            try:
                if dt.date.fromisoformat(last_updated) < since:
                    continue
            except ValueError:
                pass

        folder = sf.parent
        ats = _load_ats_report(folder)
        archetype = ((ats.get("role_archetype") or {}).get("primary")) or "Unknown"
        source = rec.get("application_source") or "unlogged"
        status = rec.get("status", "unknown")

        total += 1
        status_counts[status] += 1
        responded = 1 if status in RESPONSE_STATUSES else 0

        by_archetype[archetype]["total"] += 1
        by_archetype[archetype]["responded"] += responded
        by_source[source]["total"] += 1
        by_source[source]["responded"] += responded

    print(f"=== Outcome digest ({total} tracked applications{' since ' + args.since if args.since else ''}) ===\n")

    print("Status breakdown:")
    for s in VALID_STATUSES + ["unknown"]:
        if status_counts.get(s):
            print(f"  {s:14s} {status_counts[s]}")
    print()

    print("Response rate by role archetype (interview+ / total):")
    for arch, d in sorted(by_archetype.items(), key=lambda kv: -kv[1]["total"]):
        rate = (d["responded"] / d["total"] * 100) if d["total"] else 0
        print(f"  {arch:35s} {d['responded']:>3d}/{d['total']:<3d}  ({rate:.1f}%)")
    print()

    print("Response rate by application source (interview+ / total):")
    for src, d in sorted(by_source.items(), key=lambda kv: -kv[1]["total"]):
        rate = (d["responded"] / d["total"] * 100) if d["total"] else 0
        print(f"  {src:20s} {d['responded']:>3d}/{d['total']:<3d}  ({rate:.1f}%)")

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Application outcome & channel tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_set = sub.add_parser("set", help="Record a status for one application")
    p_set.add_argument("company", help="Company name or folder-name substring")
    p_set.add_argument("status", choices=VALID_STATUSES)
    p_set.add_argument("--source", choices=VALID_SOURCES, default=None)
    p_set.add_argument("--notes", default=None)
    p_set.set_defaults(func=cmd_set)

    p_pending = sub.add_parser("pending", help="List applications with no recorded status yet")
    p_pending.set_defaults(func=cmd_pending)

    p_report = sub.add_parser("report", help="Print response-rate digest by archetype and channel")
    p_report.add_argument("--since", default=None, help="ISO date, only count updates on/after this date")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
