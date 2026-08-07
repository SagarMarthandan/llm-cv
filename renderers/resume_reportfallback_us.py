"""
Resume ReportFallback renderer.

Produces the same visual layout as the LaTeX renderer (header with name +
contact, ruled section headers, single-paragraph project entries,
tabbed experience rows) but via ReportLab using the Calibri font family.

Used in two cases:
  1. The user selects `reportfallback` as the render mode at pipeline start.
  2. The LaTeX renderer's parse-integrity audit fails and this renderer is
     triggered automatically as an ATS-safe fallback.
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer,
    Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from .utils import (
    TEXT_DARK, TEXT_MUTED, LINE_COLOR,
    register_lm_roman_10,
)
from .resume_common import (
    HEADERS, get_resume_language, get_section_order, format_date_numeric,
    create_reportlab_doc, create_reportlab_styles,
    generate_reportlab_contact_header, make_section_header,
    render_summary_rl, render_technical_skills_rl,
    render_projects_rl, render_professional_experience_rl,
    render_education_rl, render_spoken_languages_rl,
    ReportLabRenderContext, US_SPACING,
)
from config import CANDIDATE_NAME


def create_resume_pdf_reportlab(data, output_path):
    F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC = register_lm_roman_10()

    doc, printable_width = create_reportlab_doc(output_path)
    styles = create_reportlab_styles(F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC)

    story = []

    # Header (no photo — name is the dominant element)
    story.extend(generate_reportlab_contact_header(data, styles['name'], styles['contact']))

    def add_section_header(title):
        return make_section_header(title, styles['section_title'], printable_width, US_SPACING['section_header_toppadding'])

    # Section renderers — each returns a list of flowables for one section.
    # The main body iterates over the (optionally YAML-overridden) section
    # order and extends `story` with whichever the renderer produces, so the
    # layout order is data-driven rather than hardcoded.
    lang_code = get_resume_language(data)
    h = HEADERS[lang_code]

    ctx = ReportLabRenderContext(data, h, add_section_header, styles, US_SPACING, include_project_bullets=False)

    section_renderers = {
        'summary': render_summary_rl,
        'technical_skills': render_technical_skills_rl,
        'projects': render_projects_rl,
        'professional_experience': render_professional_experience_rl,
        'education': render_education_rl,
        'spoken_languages': render_spoken_languages_rl,
    }
    for key in get_section_order(data):
        story.extend(section_renderers[key](ctx))

    doc.build(story)
    print(f"Successfully compiled Resume via ReportLab (LM Roman 10): {output_path}")
