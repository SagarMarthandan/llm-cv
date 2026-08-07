"""
Resume LaTeX renderer.

Compiles a resume YAML into a PDF via pdflatex, then runs a parse-integrity
audit on the resulting PDF. If the audit fails, the renderer auto-recovers by
falling back to the ReportLab renderer. The standalone resume_parseability.py
(Step 2 Section 6) is the sole writer of the parse-integrity report.
"""
import os
import sys
import yaml

from .utils import TEXT_DARK, escape_latex, run_pdflatex
from .resume_common import (
    HEADERS, get_resume_language, get_section_order, format_date_numeric,
    generate_latex_contact_header, generate_latex_summary_tex,
    generate_latex_education_tex, generate_latex_skills_tex,
    generate_latex_projects_tex, generate_latex_experience_tex,
    generate_latex_languages_tex, generate_latex_document,
)
from config import CANDIDATE_NAME


# ── LaTeX renderer ────────────────────────────────────────────────────────────

def _generate_resume_tex(data, output_path):
    """Generate the .tex source file for a resume.

    Returns (tex_path, pdf_dir) so callers can decide whether to run
    pdflatex (full compile) or just return the .tex.
    """
    # 1. Parse contact info and format header
    header_tex = generate_latex_contact_header(data)

    # 2. Format sections
    lang_code = get_resume_language(data)
    h = HEADERS[lang_code]

    # A. Summary
    summary_tex = generate_latex_summary_tex(data, h)

    # B. Education
    education_tex = generate_latex_education_tex(data, h)

    # C. Technical Skills
    skills_tex = generate_latex_skills_tex(data, h)

    # D. Projects — single-paragraph format: name --- [GitHub] --- summary
    projects_tex = generate_latex_projects_tex(data, h, strip_trailing_dot=True, vspace='6pt')

    # E. Professional Experience
    experience_tex = generate_latex_experience_tex(data, h, include_project_bullets=False)

    # F. Spoken Languages
    lang_tex = generate_latex_languages_tex(data, h)

    section_map = {
        'summary': summary_tex,
        'technical_skills': skills_tex,
        'projects': projects_tex,
        'professional_experience': experience_tex,
        'education': education_tex,
        'spoken_languages': lang_tex,
    }
    order = get_section_order(data)
    sections = [section_map[k] for k in order
                if k in section_map and section_map[k]]
    body_tex = "\n\n\\vspace{6pt}\n\n".join(sections)

    # 3. Generate LaTeX document
    tex_content = generate_latex_document(header_tex, body_tex)

    # 4. Write .tex file
    pdf_dir      = os.path.dirname(os.path.abspath(output_path))
    pdf_name     = os.path.basename(output_path)
    base_name    = os.path.splitext(pdf_name)[0]
    tex_filename = f"{base_name}.tex"
    tex_path     = os.path.join(pdf_dir, tex_filename)

    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(tex_content)

    return tex_path, pdf_dir


def create_resume_pdf_latex_tex_only(data, output_path):
    """Write the .tex source file without running pdflatex.

    Used in Step A of the resume pipeline where the agent will hand-edit the
    .tex before the final compile in Step C. Avoids a throwaway pdflatex run.
    """
    print(f"Generating Resume .tex (tex-only mode): {output_path}")
    tex_path, pdf_dir = _generate_resume_tex(data, output_path)
    print(f"Wrote LaTeX source: {tex_path}")


def create_resume_pdf_latex(data, output_path):
    print(f"Attempting to compile Resume via LaTeX: {output_path}")
    tex_path, pdf_dir = _generate_resume_tex(data, output_path)
    tex_filename = os.path.basename(tex_path)

    try:
        run_pdflatex(tex_filename, pdf_dir, label="Resume", keep_tex=True)
        print(f"Successfully compiled Resume via LaTeX: {output_path}")

    except Exception as e:
        print(f"Error compiling LaTeX: {e}", file=sys.stderr)
        print("Falling back to ReportLab compilation...", file=sys.stderr)
        from .resume_reportfallback_us import create_resume_pdf_reportlab
        create_resume_pdf_reportlab(data, output_path)
