"""
Parseability Report renderer — ReportLab only.

Renders the output of resume_parseability.py as a clean PDF report using
the LM Roman 10 font family, matching the style of the ATS Report renderer.

Handles documents with type: parseability_report
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from .utils import TEXT_DARK, LINE_COLOR, register_lm_roman_10

# Status colors
PASS_COLOR = '#1a7a1a'
FAIL_COLOR = '#a00000'
WARN_COLOR = '#b35900'
INFO_COLOR = '#1A365D'


def create_parseability_report_pdf(data, output_path):
    """Compile parseability audit results to a PDF report."""
    print(f"Compiling Parseability Report via ReportLab: {output_path}")

    F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC = register_lm_roman_10()

    margin = 0.4 * inch
    printable_width = A4[0] - (2 * margin)
    printable_height = A4[1] - (2 * margin)

    doc = BaseDocTemplate(
        output_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )
    frame = Frame(
        margin, margin, printable_width, printable_height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id='normal',
    )
    doc.addPageTemplates([PageTemplate(id='all', frames=[frame], pagesize=A4)])

    styles = getSampleStyleSheet()

    h1 = ParagraphStyle('ParseH1', parent=styles['Normal'], fontName=F_BOLD,
                        fontSize=20, leading=24, spaceAfter=4, leftIndent=0, firstLineIndent=0)
    h2 = ParagraphStyle('ParseH2', parent=styles['Normal'], fontName=F_BOLD,
                        fontSize=10.5, leading=13, leftIndent=0, firstLineIndent=0)
    h3 = ParagraphStyle('ParseH3', parent=styles['Normal'], fontName=F_BOLD,
                        fontSize=9.5, leading=12, spaceAfter=2, leftIndent=0, firstLineIndent=0)
    body = ParagraphStyle('ParseBody', parent=styles['Normal'], fontName=F_REG,
                          fontSize=9, leading=12, textColor=TEXT_DARK,
                          leftIndent=0, firstLineIndent=0)
    bullet = ParagraphStyle('ParseBullet', parent=styles['Normal'], fontName=F_REG,
                            fontSize=9, leading=12, leftIndent=12, firstLineIndent=-8,
                            spaceAfter=2, textColor=TEXT_DARK)
    mono = ParagraphStyle('ParseMono', parent=styles['Normal'], fontName=F_REG,
                          fontSize=8, leading=10.5, textColor=TEXT_DARK,
                          leftIndent=0, firstLineIndent=0)

    def section_header(title):
        t = Table([[Paragraph(f'<b>{title.upper()}</b>', h2)]], colWidths=[printable_width])
        t.setStyle(TableStyle([
            ('LINEBELOW',     (0,0), (-1,-1), 0.5, LINE_COLOR),
            ('TOPPADDING',    (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('LEFTPADDING',   (0,0), (-1,-1), 0),
            ('RIGHTPADDING',  (0,0), (-1,-1), 0),
        ]))
        return t

    def status_label(status):
        s = str(status).lower().strip()
        if s in ('pass', 'passed', 'ok'):
            return f'<font color="{PASS_COLOR}"><b>PASS</b></font>'
        elif s in ('fail', 'failed'):
            return f'<font color="{FAIL_COLOR}"><b>FAIL</b></font>'
        elif s in ('warn', 'warning', 'partial'):
            return f'<font color="{WARN_COLOR}"><b>WARN</b></font>'
        return f'<b>{status}</b>'

    story = []

    # ── Title ────────────────────────────────────────────────────────────────
    company = data.get('company', '')
    position = data.get('position', '')
    subtitle = f"{company} \u2014 {position}" if company and position else (company or position)

    story.append(Paragraph('<b>Resume Parseability Report</b>', h1))
    if subtitle:
        story.append(Paragraph(subtitle, body))
    story.append(Spacer(1, 4))

    pdf_file = data.get('pdf_file', '')
    yaml_file = data.get('yaml_file', '')
    audit_date = data.get('audit_date', '')
    if pdf_file or yaml_file or audit_date:
        story.append(Paragraph(
            f'<font size=8 color="#555555">'
            f'PDF: {os.path.basename(pdf_file)} &nbsp;|&nbsp; '
            f'YAML: {os.path.basename(yaml_file)} &nbsp;|&nbsp; '
            f'Date: {audit_date}'
            f'</font>',
            body
        ))
    story.append(Spacer(1, 8))

    # ── Overall Verdict ──────────────────────────────────────────────────────
    overall = data.get('overall_status', 'Unknown')
    recovery_pct = data.get('keyword_recovery_pct', 0)

    story.append(section_header('Overall Verdict'))
    story.append(Spacer(1, 6))

    verdict_color = PASS_COLOR if str(overall).lower() == 'pass' else FAIL_COLOR
    story.append(Paragraph(
        f'<b>Status:</b> <font color="{verdict_color}"><b>{overall.upper()}</b></font>',
        body
    ))
    story.append(Spacer(1, 2))

    summary_table_data = [
        [Paragraph('<b>Check</b>', h3), Paragraph('<b>Result</b>', h3)],
        [Paragraph('Unicode Integrity', body),
         Paragraph(status_label(data.get('unicode_status', 'Pass')), body)],
        [Paragraph('Keyword Recovery', body),
         Paragraph(f'{recovery_pct}% ({data.get("keywords_recovered", 0)}/{data.get("keywords_total", 0)})', body)],
        [Paragraph('Section Headers', body),
         Paragraph(f'{data.get("sections_found", 0)}/{data.get("sections_total", 0)} detected', body)],
        [Paragraph('Contact Info', body),
         Paragraph(f'{data.get("contact_fields_found", 0)}/{data.get("contact_fields_total", 0)} extracted', body)],
        [Paragraph('Pages', body),
         Paragraph(str(data.get('pages', 1)), body)],
        [Paragraph('Text Extracted', body),
         Paragraph(f'{data.get("total_chars", 0)} chars / {data.get("total_words", 0)} words', body)],
    ]
    summary_tbl = Table(summary_table_data, colWidths=[200, printable_width - 200])
    summary_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
        ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING',   (0,0), (-1,-1), 4),
        ('RIGHTPADDING',  (0,0), (-1,-1), 4),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 8))

    # ── Unicode Corruption ───────────────────────────────────────────────────
    story.append(section_header('Unicode Integrity'))
    story.append(Spacer(1, 4))

    unicode_corruptions = data.get('unicode_corruptions', [])
    if unicode_corruptions:
        story.append(Paragraph(
            f'{status_label("Fail")} {len(unicode_corruptions)} replacement glyphs (U+FFFD) found at positions: '
            f'{unicode_corruptions[:20]}{"..." if len(unicode_corruptions) > 20 else ""}',
            body
        ))
    else:
        story.append(Paragraph(
            f'{status_label("Pass")} No replacement glyphs (U+FFFD) detected in the extracted text layer.',
            body
        ))
    story.append(Spacer(1, 8))

    # ── Keyword Recovery ─────────────────────────────────────────────────────
    story.append(section_header('Keyword Recovery'))
    story.append(Spacer(1, 4))

    keyword_results = data.get('keyword_results', [])
    if keyword_results:
        kw_table_data = [
            [Paragraph('<b>Keyword</b>', h3), Paragraph('<b>Status</b>', h3), Paragraph('<b>Note</b>', h3)]
        ]
        for kr in keyword_results:
            kw = kr.get('keyword', '')
            st = kr.get('status', 'found')
            note = kr.get('note', '')
            kw_table_data.append([
                Paragraph(kw, body),
                Paragraph(status_label(st), body),
                Paragraph(note, body),
            ])

        kw_tbl = Table(kw_table_data, colWidths=[180, 60, printable_width - 240])
        kw_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
            ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
            ('TOPPADDING',    (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        story.append(kw_tbl)
    else:
        story.append(Paragraph('All keywords recovered.', body))
    story.append(Spacer(1, 8))

    # ── Section Header Detection ─────────────────────────────────────────────
    story.append(section_header('Section Header Detection'))
    story.append(Spacer(1, 4))

    section_results = data.get('section_results', [])
    if section_results:
        sec_table_data = [
            [Paragraph('<b>Section</b>', h3), Paragraph('<b>Status</b>', h3)]
        ]
        for sr in section_results:
            sec_name = sr.get('section', '')
            sec_st = sr.get('status', 'found')
            sec_table_data.append([
                Paragraph(sec_name, body),
                Paragraph(status_label(sec_st), body),
            ])
        sec_tbl = Table(sec_table_data, colWidths=[250, printable_width - 250])
        sec_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
            ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
            ('TOPPADDING',    (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        story.append(sec_tbl)
    story.append(Spacer(1, 8))

    # ── Contact Info Extraction ──────────────────────────────────────────────
    story.append(section_header('Contact Info Extraction'))
    story.append(Spacer(1, 4))

    contact_results = data.get('contact_results', [])
    if contact_results:
        ct_table_data = [
            [Paragraph('<b>Field</b>', h3), Paragraph('<b>Value</b>', h3), Paragraph('<b>Status</b>', h3)]
        ]
        for cr in contact_results:
            field = cr.get('field', '')
            value = cr.get('value', '')
            st = cr.get('status', 'found')
            ct_table_data.append([
                Paragraph(field, body),
                Paragraph(value, body),
                Paragraph(status_label(st), body),
            ])
        ct_tbl = Table(ct_table_data, colWidths=[80, printable_width - 140, 60])
        ct_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
            ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
            ('TOPPADDING',    (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        story.append(ct_tbl)
    story.append(Spacer(1, 8))

    # ── Text Structure ───────────────────────────────────────────────────────
    story.append(section_header('Text Structure'))
    story.append(Spacer(1, 4))

    text_stats = data.get('text_stats', {})
    story.append(Paragraph(f'<b>Non-empty lines:</b> {text_stats.get("non_empty_lines", 0)}', body))
    story.append(Paragraph(f'<b>Average line length:</b> {text_stats.get("avg_line_length", 0):.0f} chars', body))
    story.append(Paragraph(f'<b>Max line length:</b> {text_stats.get("max_line_length", 0)} chars', body))
    story.append(Spacer(1, 8))

    # ── Extracted Text Preview ───────────────────────────────────────────────
    story.append(section_header('Extracted Text Preview (first 1500 chars)'))
    story.append(Spacer(1, 4))

    text_preview = data.get('text_preview', '')
    if text_preview:
        # Escape XML/HTML special chars for ReportLab
        preview_escaped = (text_preview
                           .replace('&', '&amp;')
                           .replace('<', '&lt;')
                           .replace('>', '&gt;'))
        story.append(Paragraph(f'<font face="{F_REG}" size=8>{preview_escaped}</font>', mono))

    doc.build(story)
    print(f"Successfully compiled Parseability Report: {output_path}")
