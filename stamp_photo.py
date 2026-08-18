"""
stamp_photo.py — Stamp candidate photo onto a resume PDF.

Post-processing step for LaTeX-mode resumes compiled with raw pdflatex
(Step C of the pipeline), which bypasses create_resume_pdf() where the
automatic stamping lives.

Usage:
  python stamp_photo.py <pdf_path> [yaml_path]

If yaml_path is provided, resolves the photo from contact_info.photo →
CANDIDATE_PHOTO config default. If omitted, uses CANDIDATE_PHOTO directly.

Examples:
  python stamp_photo.py SAGAR_MARTHANDAN_Lebenslauf.pdf Resume.yaml
  python stamp_photo.py SAGAR_MARTHANDAN_Lebenslauf.pdf
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from renderers.resume_common import get_photo_path, stamp_photo_on_pdf


def main():
    if len(sys.argv) < 2:
        print("Usage: python stamp_photo.py <pdf_path> [yaml_path]", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    yaml_path = sys.argv[2] if len(sys.argv) > 2 else None

    if yaml_path and os.path.exists(yaml_path):
        import yaml
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        photo = get_photo_path(data)
    else:
        from config import CANDIDATE_PHOTO
        photo = CANDIDATE_PHOTO if CANDIDATE_PHOTO and os.path.exists(CANDIDATE_PHOTO) else None

    if not photo:
        print("No photo found — skipping stamping.", file=sys.stderr)
        sys.exit(0)

    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    stamp_photo_on_pdf(pdf_path, photo, render_mode='latex')


if __name__ == '__main__':
    main()
