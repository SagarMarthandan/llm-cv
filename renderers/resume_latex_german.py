"""
Resume LaTeX renderer — German market style.

Produces a Lebenslauf PDF with German-convention section ordering:
  Summary → Professional Experience → Education → Technical Skills →
  Projects → Spoken Languages

Language is determined by get_resume_language(data) — automatic from JD.
The renderer works for both German and English language content; the
*style* (section order) is always German market.

Used when the user selects:
  render_mode: latex
  resume_style: german
"""
import os
import sys

from .utils import TEXT_DARK, escape_latex, run_pdflatex
from .resume_common import (
    HEADERS, get_resume_language, get_german_section_order, format_date_numeric,
    GERMAN_STYLE_SECTION_ORDER,
    generate_latex_contact_header, generate_latex_summary_tex,
    generate_latex_education_tex, generate_latex_skills_tex,
    generate_latex_projects_tex, generate_latex_experience_tex,
    generate_latex_languages_tex, generate_latex_document,
)
from config import CANDIDATE_NAME


# ── German-style section order ───────────────────────────────────────────────


def _generate_resume_tex_germany(data, output_path):
    """Generate the .tex source file for a German-style resume."""
    header_tex = generate_latex_contact_header(data)

    lang_code = get_resume_language(data)
    h = HEADERS[lang_code]

    # A. Summary
    summary_tex = generate_latex_summary_tex(data, h)

    # B. Professional Experience
    experience_tex = generate_latex_experience_tex(data, h, include_project_bullets=True)

    # C. Education
    education_tex = generate_latex_education_tex(data, h)

    # D. Technical Skills
    skills_tex = generate_latex_skills_tex(data, h)

    # E. Projects — single-paragraph format
    projects_tex = generate_latex_projects_tex(data, h, strip_trailing_dot=False, vspace='4pt')

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

    # German style uses its own fixed order — no YAML override needed.
    # But respect section_order if explicitly provided (for flexibility).
    order = get_german_section_order(data)
    sections = [section_map[k] for k in order
                if k in section_map and section_map[k]]
    body_tex = "\n\n\\vspace{6pt}\n\n".join(sections)

    tex_content = generate_latex_document(header_tex, body_tex)

    pdf_dir = os.path.dirname(os.path.abspath(output_path))
    pdf_name     = os.path.basename(output_path)
    base_name    = os.path.splitext(pdf_name)[0]
    tex_filename = f"{base_name}.tex"
    tex_path     = os.path.join(pdf_dir, tex_filename)

    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(tex_content)

    return tex_path, pdf_dir


def create_resume_pdf_latex_germany_tex_only(data, output_path):
    """Write the .tex source file without running pdflatex."""
    print(f"Generating German-style Resume .tex (tex-only mode): {output_path}")
    tex_path, pdf_dir = _generate_resume_tex_germany(data, output_path)
    print(f"Wrote LaTeX source: {tex_path}")


def create_resume_pdf_latex_germany(data, output_path):
    """Compile a German-style resume via LaTeX."""
    print(f"Attempting to compile German-style Resume via LaTeX: {output_path}")
    tex_path, pdf_dir = _generate_resume_tex_germany(data, output_path)
    tex_filename = os.path.basename(tex_path)

    try:
        run_pdflatex(tex_filename, pdf_dir, label="Resume (German style)", keep_tex=True)
        print(f"Successfully compiled German-style Resume via LaTeX: {output_path}")

    except Exception as e:
        print(f"Error compiling LaTeX: {e}", file=sys.stderr)
        print("Falling back to ReportLab German-style compilation...", file=sys.stderr)
        from .resume_reportfallback_german import create_resume_pdf_reportlab_germany
        create_resume_pdf_reportlab_germany(data, output_path)
