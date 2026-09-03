#!/usr/bin/env python3
"""Extract selected projects from catalog or generate condensed catalog (no bullets).

Usage:
  # Generate condensed catalog (no bullets) — for Step 1 ranking
  python extract_projects.py --condensed \
      --catalog okf/project_catalog.yaml \
      --output okf/project_catalog_condensed.yaml

  # Extract full data for projects listed in project_info.md — for Step 2 resume writing
  python extract_projects.py --from-project-info path/to/project_info.md \
      --catalog okf/project_catalog.yaml \
      --output path/to/selected_projects.yaml

  # Extract full data for specific titles
  python extract_projects.py --titles "Project A,Project B" \
      --catalog okf/project_catalog.yaml \
      --output selected_projects.yaml
"""
import argparse
import re
import sys
import yaml


def load_catalog(path):
    with open(path) as f:
        return yaml.safe_load(f)


def generate_condensed(catalog):
    """Strip bullets from each project, keep all other fields."""
    condensed = {"projects": []}
    for p in catalog["projects"]:
        cp = {k: v for k, v in p.items() if k != "bullets"}
        condensed["projects"].append(cp)
    return condensed


def parse_titles_from_project_info(path):
    """Extract project titles from project_info.md # headings.

    Skips the first '# Tailored Project Portfolio' heading.
    """
    titles = []
    with open(path) as f:
        for line in f:
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                title = m.group(1).strip()
                if title and not title.lower().startswith("tailored"):
                    titles.append(title)
    return titles


def extract_projects(catalog, titles):
    """Filter catalog to only include projects with matching titles, preserving order."""
    by_title = {p["title"]: p for p in catalog["projects"]}
    selected = []
    missing = []
    for title in titles:
        if title in by_title:
            selected.append(by_title[title])
        else:
            missing.append(title)
    for t in missing:
        print(f"WARNING: '{t}' not found in catalog", file=sys.stderr)
    return {"projects": selected}


def main():
    parser = argparse.ArgumentParser(
        description="Extract projects from catalog or generate condensed catalog"
    )
    parser.add_argument("--catalog", required=True, help="Path to project_catalog.yaml")
    parser.add_argument("--output", required=True, help="Output YAML path")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--condensed",
        action="store_true",
        help="Generate condensed catalog (no bullets)",
    )
    group.add_argument(
        "--from-project-info",
        metavar="PATH",
        help="Extract projects listed in project_info.md",
    )
    group.add_argument(
        "--titles",
        help="Comma-separated project titles to extract",
    )
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)

    if args.condensed:
        result = generate_condensed(catalog)
    elif args.from_project_info:
        titles = parse_titles_from_project_info(args.from_project_info)
        if not titles:
            print("ERROR: No project titles found in project_info.md", file=sys.stderr)
            sys.exit(1)
        result = extract_projects(catalog, titles)
    elif args.titles:
        titles = [t.strip() for t in args.titles.split(",") if t.strip()]
        result = extract_projects(catalog, titles)

    with open(args.output, "w") as f:
        yaml.dump(
            result,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=10000,
        )

    print(f"Wrote {len(result['projects'])} projects to {args.output}")


if __name__ == "__main__":
    main()
