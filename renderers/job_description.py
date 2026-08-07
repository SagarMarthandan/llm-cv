"""
Job description renderer — ReportLab only (reportfallback mode).
Handles documents with type: job_description
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from .utils import TEXT_DARK, LINE_COLOR, escape_latex, run_pdflatex, register_lm_roman_10


# ── LaTeX renderer ────────────────────────────────────────────────────────────

def create_job_description_pdf(data, output_path):
    """Compile Job_Description.yaml to a clean PDF via ReportLab directly (ReportLab fallback mode)."""
    print(f"Compiling Job Description via ReportLab fallback mode (no LaTeX): {output_path}")
    _create_job_description_pdf_reportlab(data, output_path)



# ── ReportLab fallback ────────────────────────────────────────────────────────

def _create_job_description_pdf_reportlab(data, output_path):
    margin = 0.3 * inch
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )
    printable_width = A4[0] - (2 * margin)
    styles = getSampleStyleSheet()

    F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC = register_lm_roman_10()

    title_style = ParagraphStyle(
        'JDTitle', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=15, leading=19,
        textColor=colors.black, spaceAfter=15,
    )
    section_style = ParagraphStyle(
        'JDSectionTitle', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=11, leading=14, textColor=colors.black,
    )
    body_style = ParagraphStyle(
        'JDBody', parent=styles['Normal'],
        fontName=F_REG, fontSize=9.5, leading=14,
        textColor=TEXT_DARK, spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        'JDBullet', parent=styles['Normal'],
        fontName=F_REG, fontSize=9.5, leading=14,
        leftIndent=15, firstLineIndent=-10, spaceAfter=3, textColor=TEXT_DARK,
    )

    story = []

    comp = data.get('company', 'Company')
    pos  = data.get('position', 'Position')
    story.append(Paragraph(f"<b>{comp} \u2014 {pos}</b>", title_style))

    for sec in data.get('sections', []):
        title   = sec.get('title', '')
        content = sec.get('content', '')
        bullets = sec.get('bullets', [])

        t = Table([[Paragraph(f"<b>{title}</b>", section_style)]], colWidths=[printable_width])
        t.setStyle(TableStyle([
            ('LINEBELOW',     (0,0), (-1,-1), 0.5, LINE_COLOR),
            ('TOPPADDING',    (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('LEFTPADDING',   (0,0), (-1,-1), 0),
            ('RIGHTPADDING',  (0,0), (-1,-1), 0),
        ]))

        sec_block = [t, Spacer(1, 6)]

        if content:
            if isinstance(content, list):
                for p in content:
                    sec_block.append(Paragraph(p, body_style))
            else:
                sec_block.append(Paragraph(content, body_style))

        for b in bullets:
            sec_block.append(Paragraph(f"&bull;&nbsp;&nbsp;{b}", bullet_style))

        sec_block.append(Spacer(1, 10))
        story.append(KeepTogether(sec_block))

    doc.build(story)
    print(f"Successfully compiled Job Description via ReportLab: {output_path}")
