"""
yaml_to_pdf.py — LLM-CV Pipeline entry point.

Routes an input YAML file to the correct PDF renderer based on the document
type declared in the YAML (or inferred from the filename).

Supported types:
  resume               → renderers/resume.py
  cover_letter         → renderers/cover_letter.py
  job_description      → renderers/job_description.py
  ats_report           → renderers/ats_report.py
  parseability_report  → renderers/parseability_report.py

Usage:
  python yaml_to_pdf.py <input.yaml> <output.pdf> [--tex-only]

The optional --tex-only flag (resume type only, LaTeX mode) writes the .tex
source file without running pdflatex. Used in Step A of the resume pipeline
where the agent will hand-edit the .tex before the final compile in Step C.
"""
import os
import sys
import yaml
import importlib
from typing import Dict, Any

VALID_TYPES = {'resume', 'cover_letter', 'job_description', 'ats_report', 'parseability_report'}

# Lazy renderer loader — maps doc type to (module_path, function_name).
# Only imports the renderer module actually needed, avoiding loading
# reportlab/pdflatex for unrelated types.
_RENDERER_ROUTES = {
    'resume':              ('renderers.resume', 'create_resume_pdf'),
    'cover_letter':        ('renderers.cover_letter', 'create_cover_letter_pdf'),
    'job_description':     ('renderers.job_description', 'create_job_description_pdf'),
    'ats_report':          ('renderers.ats_report', 'create_ats_report_pdf'),
    'parseability_report': ('renderers.parseability_report', 'create_parseability_report_pdf'),
}


def _infer_type(filename: str) -> str:
    """Infer document type from filename when the YAML has no 'type' field."""
    name = filename.lower()
    if 'resume' in name:
        return 'resume'
    if 'cover_letter' in name or 'cover' in name:
        return 'cover_letter'
    if 'ats_report' in name or 'ats' in name:
        return 'ats_report'
    if 'parseability' in name or 'parse' in name:
        return 'parseability_report'
    if 'job_description' in name or 'job' in name:
        return 'job_description'
    return ''


def main() -> None:
    args = sys.argv[1:]
    tex_only = False
    if '--tex-only' in args:
        tex_only = True
        args.remove('--tex-only')

    if len(args) < 2:
        print("Usage: python yaml_to_pdf.py <input.yaml> <output.pdf> [--tex-only]", file=sys.stderr)
        sys.exit(1)

    yaml_path = args[0]
    pdf_path  = args[1]

    if not os.path.exists(yaml_path):
        print(f"Error: Input file '{yaml_path}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error parsing YAML file '{yaml_path}': {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"Error: YAML content must be a dictionary, got {type(data)}.", file=sys.stderr)
        sys.exit(1)

    doc_type = str(data.get('type', '')).lower()

    # Fall back to filename heuristic if type is missing or unrecognised
    if doc_type not in VALID_TYPES:
        doc_type = _infer_type(os.path.basename(yaml_path))

    # Ensure output directory exists
    pdf_dir = os.path.dirname(pdf_path)
    if pdf_dir and not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir, exist_ok=True)

    # --tex-only is only meaningful for resume (LaTeX mode). For other types
    # it is silently ignored.
    if tex_only and doc_type == 'resume':
        from renderers.resume import _resolve_render_mode, _resolve_resume_style
        mode = _resolve_render_mode(data)
        style = _resolve_resume_style(data)
        if mode == 'latex':
            if style == 'german':
                from renderers.resume_latex_german import create_resume_pdf_latex_germany_tex_only
                create_resume_pdf_latex_germany_tex_only(data, pdf_path)
            else:
                from renderers.resume_latex_us import create_resume_pdf_latex_tex_only
                create_resume_pdf_latex_tex_only(data, pdf_path)
            return
        # reportfallback has no .tex polish step — fall through to normal compile
        print("--tex-only ignored for reportfallback mode (no .tex file produced).", file=sys.stderr)

    if doc_type not in _RENDERER_ROUTES:
        print(
            f"Error: Unknown document type '{doc_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_TYPES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Lazy import — only load the renderer module for the document type being compiled
    module_path, fn_name = _RENDERER_ROUTES[doc_type]
    mod = importlib.import_module(module_path)
    render_fn = getattr(mod, fn_name)
    render_fn(data, pdf_path)


if __name__ == '__main__':
    main()
