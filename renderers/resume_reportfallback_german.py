"""
Resume ReportFallback renderer — German market style.

Produces the same visual layout as the German-style LaTeX renderer but via
ReportLab using the LM Roman 10 font family. Used as:
  1. The fallback when the German-style LaTeX renderer's parse-integrity
     audit fails.
  2. The primary renderer when the user selects ReportFallback + German style.

Section order follows German Lebenslauf convention:
  Summary → Professional Experience → Education → Technical Skills →
  Projects → Spoken Languages
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
    HEADERS, get_resume_language, get_german_section_order, format_date_numeric,
    GERMAN_STYLE_SECTION_ORDER,
    create_reportlab_doc, create_reportlab_styles,
    generate_reportlab_contact_header, make_section_header,
    render_summary_rl, render_technical_skills_rl,
    render_projects_rl, render_professional_experience_rl,
    render_education_rl, render_spoken_languages_rl,
    ReportLabRenderContext, GERMAN_SPACING,
)
from config import CANDIDATE_NAME


def create_resume_pdf_reportlab_germany(data, output_path):
    F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC = register_lm_roman_10()

    doc, printable_width = create_reportlab_doc(output_path)
    styles = create_reportlab_styles(F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC)

    story = []

    # Header
    story.extend(generate_reportlab_contact_header(data, styles['name'], styles['contact']))

    def add_section_header(title):
        return make_section_header(title, styles['section_title'], printable_width, GERMAN_SPACING['section_header_toppadding'])

    lang_code = get_resume_language(data)
    h = HEADERS[lang_code]

    ctx = ReportLabRenderContext(data, h, add_section_header, styles, GERMAN_SPACING, include_project_bullets=True)

    section_renderers = {
        'summary': render_summary_rl,
        'professional_experience': render_professional_experience_rl,
        'education': render_education_rl,
        'technical_skills': render_technical_skills_rl,
        'projects': render_projects_rl,
        'spoken_languages': render_spoken_languages_rl,
    }

    # Respect section_order override if provided, otherwise use German default
    order = get_german_section_order(data)

    for key in order:
        story.extend(section_renderers[key](ctx))

    doc.build(story)
    print(f"Successfully compiled German-style Resume via ReportLab (LM Roman 10): {output_path}")
