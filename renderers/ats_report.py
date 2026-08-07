"""
ATS Report renderer — ReportLab only (reportfallback mode).
Handles documents with type: ats_report
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from .utils import TEXT_DARK, LINE_COLOR, escape_latex, run_pdflatex, register_lm_roman_10


# ── LaTeX renderer ────────────────────────────────────────────────────────────

def create_ats_report_pdf(data, output_path):
    """Compile ATS_Report.yaml to a clean PDF via ReportLab directly (ReportLab fallback mode)."""
    print(f"Compiling ATS Report via ReportLab fallback mode (no LaTeX): {output_path}")
    _create_ats_report_pdf_reportlab(data, output_path)



# ── ReportLab fallback ────────────────────────────────────────────────────────

def _create_ats_report_pdf_reportlab(data, output_path):
    """ReportLab fallback renderer for ATS_Report.yaml."""
    margin = 0.3 * inch
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )
    printable_width = A4[0] - 2 * margin
    styles = getSampleStyleSheet()

    F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC = register_lm_roman_10()

    h1     = ParagraphStyle('ATSH1', parent=styles['Normal'], fontName=F_BOLD,
                            fontSize=20, leading=24, spaceAfter=4)
    h2     = ParagraphStyle('ATSH2', parent=styles['Normal'], fontName=F_BOLD,
                            fontSize=10.5, leading=13)
    h3     = ParagraphStyle('ATSH3', parent=styles['Normal'], fontName=F_BOLD,
                            fontSize=9.5, leading=12, spaceAfter=2)
    body   = ParagraphStyle('ATSBody', parent=styles['Normal'], fontName=F_REG,
                            fontSize=9, leading=12.5, textColor=TEXT_DARK)
    bullet = ParagraphStyle('ATSBullet', parent=styles['Normal'], fontName=F_REG,
                            fontSize=9, leading=12.5, leftIndent=12, firstLineIndent=-8,
                            spaceAfter=2, textColor=TEXT_DARK)

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

    story = []

    company  = data.get('company',  '')
    position = data.get('position', '')
    subtitle = f"{company} \u2014 {position}" if company and position else (company or position)

    story.append(Paragraph('<b>ATS Analysis Report</b>', h1))
    if subtitle:
        story.append(Paragraph(subtitle, body))
    story.append(Spacer(1, 8))

    # Score Matrix
    story.append(section_header('ATS Score Matrix'))
    story.append(Spacer(1, 6))

    matrix = data.get('ats_score_matrix', {})
    cat_labels = {
        'keywords_and_terminology': 'Keywords & Terminology',
        'experience_relevance':      'Experience Relevance',
        'technical_skills':          'Technical Skills',
        'soft_skills_and_language':  'Soft Skills & Language',
    }
    table_data = [[Paragraph('<b>Category</b>', h3), Paragraph('<b>Score</b>', h3),
                   Paragraph('<b>Max</b>', h3),      Paragraph('<b>Evaluation Criteria</b>', h3)]]
    for key, label in cat_labels.items():
        if key in matrix:
            cat     = matrix[key]
            current = cat.get('current_score', 0)
            max_s   = cat.get('max_score', 0)
            crit    = str(cat.get('evaluation_criteria', ''))
            table_data.append([Paragraph(label, body), Paragraph(str(current), body),
                                Paragraph(str(max_s), body), Paragraph(crit, body)])
    total_score = matrix.get('total_score', 0)
    score_color = ('#1a7a1a' if total_score >= 85
                   else '#b35900' if total_score >= 65
                   else '#a00000')
    table_data.append([Paragraph('<b>Total</b>', h3),
                       Paragraph(f'<b><font color="{score_color}">{total_score}</font></b>', h3),
                       Paragraph('<b>100</b>', h3), Paragraph('', body)])

    score_table = Table(table_data, colWidths=[140, 40, 35, printable_width - 215])
    score_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
        ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
        ('LINEABOVE',     (0,-1), (-1,-1), 0.5, LINE_COLOR),
        ('LINEBELOW',     (0,-1), (-1,-1), 0.5, LINE_COLOR),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING',   (0,0), (-1,-1), 4),
        ('RIGHTPADDING',  (0,0), (-1,-1), 4),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 8))

    # Formatting Quality (non-scored verdict)
    fq = data.get('formatting_quality') or {}
    fq_verdict = str(fq.get('verdict', '') or '').strip()
    if fq_verdict:
        story.append(section_header('Formatting Quality'))
        story.append(Spacer(1, 4))
        vlower = fq_verdict.lower()
        if vlower == 'excellent':
            vcolor = '#1a7a1a'
        elif vlower == 'good':
            vcolor = '#2a6a2a'
        elif vlower == 'average':
            vcolor = '#b35900'
        else:  # bad or unknown
            vcolor = '#a00000'
        story.append(Paragraph(
            f'<b>Verdict:</b> <font color="{vcolor}"><b>{fq_verdict.capitalize()}</b></font>', body
        ))
        fq_notes = fq.get('notes', '')
        if fq_notes:
            story.append(Paragraph(str(fq_notes), body))
        fq_suggestions = fq.get('suggestions', []) or []
        if fq_suggestions:
            story.append(Paragraph('<b>Suggested Changes:</b>', body))
            for s in fq_suggestions:
                story.append(Paragraph(f'&bull;&nbsp;&nbsp;{s}', bullet))
        story.append(Spacer(1, 6))

    # Semantic Similarity (Resume ↔ JD)
    sim = data.get('resume_jd_semantic_similarity') or {}
    pre_sim = sim.get('pre_rewrite_similarity')
    post_sim = sim.get('post_rewrite_similarity')
    if pre_sim is not None or post_sim is not None:
        story.append(section_header('Resume-JD Semantic Similarity'))
        story.append(Spacer(1, 4))
        if pre_sim is not None:
            story.append(Paragraph(
                f'<b>Pre-rewrite:</b> {float(pre_sim):.4f}', body))
        if post_sim is not None:
            story.append(Paragraph(
                f'<b>Post-rewrite:</b> {float(post_sim):.4f}', body))
        if pre_sim is not None and post_sim is not None:
            delta = float(post_sim) - float(pre_sim)
            delta_color = '#1a7a1a' if delta >= 0 else '#a00000'
            delta_str = f'+{delta:.4f}' if delta >= 0 else f'{delta:.4f}'
            story.append(Paragraph(
                f'<b>Delta:</b> <font color="{delta_color}"><b>{delta_str}</b></font>', body))
        story.append(Spacer(1, 6))

    # Skill Gap Analysis
    skill_gaps = data.get('skill_gaps')
    if skill_gaps and isinstance(skill_gaps, list) and skill_gaps:
        story.append(section_header('Skill Gap Analysis'))
        story.append(Spacer(1, 4))
        for gap in skill_gaps:
            story.append(Paragraph(f'&bull;&nbsp;&nbsp;{gap}', bullet))
        story.append(Spacer(1, 6))

    # Placement Breakdown (Contextual Keyword Placement)
    placement = data.get('placement_breakdown') or {}
    placement_items = placement.get('keywords') or []
    if placement_items:
        story.append(section_header('Contextual Keyword Placement'))
        story.append(Spacer(1, 4))
        placement_data = [[Paragraph('<b>Keyword</b>', h3),
                           Paragraph('<b>Sections Found</b>', h3),
                           Paragraph('<b>Multiplier</b>', h3)]]
        for item in placement_items:
            if isinstance(item, dict):
                kw = str(item.get('keyword', ''))
                sections = ', '.join(item.get('sections_found', []))
                mult = item.get('multiplier', 1.0)
                try:
                    mult_str = f'{float(mult):.1f}x'
                except (ValueError, TypeError):
                    mult_str = str(mult)
                placement_data.append([
                    Paragraph(kw, body),
                    Paragraph(sections, body),
                    Paragraph(mult_str, body),
                ])
        placement_tbl = Table(placement_data, colWidths=[120, printable_width - 180, 60])
        placement_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
            ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
            ('TOPPADDING',    (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(placement_tbl)
        story.append(Spacer(1, 6))

    # Core Score Detractors
    detractors = data.get('core_score_detractors', [])
    if detractors:
        story.append(section_header('Core Score Detractors'))
        story.append(Spacer(1, 4))
        for d in detractors:
            story.append(Paragraph(f'&bull;&nbsp;&nbsp;{d}', bullet))
        story.append(Spacer(1, 6))

    # Improvement Blueprint
    bp = data.get('improvement_blueprint', {})
    if bp:
        story.append(section_header('Improvement Blueprint'))
        story.append(Spacer(1, 4))

        def _format_item(item):
            """Render a blueprint item as readable text instead of a Python dict repr."""
            if isinstance(item, dict):
                return ' \u2014 '.join(f"{k}: {v}" for k, v in item.items())
            return str(item)

        def sub(title, text=None, items=None):
            story.append(Paragraph(f'<b>{title}</b>', h3))
            if text:
                story.append(Paragraph(str(text), body))
            if items:
                for item in items:
                    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{_format_item(item)}', bullet))
            story.append(Spacer(1, 4))

        sub('Target Language', bp.get('target_language_confirmation', ''))

        # Bullet Point Density Audit — items are {bullet, issue} dicts
        density = bp.get('bullet_point_density_audit', []) or []
        if density:
            story.append(Paragraph('<b>Bullet Point Density Audit</b>', h3))
            for d in density:
                if isinstance(d, dict):
                    b_text = str(d.get('bullet', ''))
                    issue  = str(d.get('issue', ''))
                    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{b_text}', bullet))
                    if issue:
                        story.append(Paragraph(
                            f'<i>&nbsp;&nbsp;&nbsp;&nbsp;Issue: {issue}</i>', bullet))
                else:
                    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{d}', bullet))
            story.append(Spacer(1, 4))
        else:
            story.append(Paragraph('<b>Bullet Point Density Audit</b>', h3))
            story.append(Paragraph('All bullets contain quantified metrics.', body))
            story.append(Spacer(1, 4))

        swap     = bp.get('project_swap_directive', {})
        rem_p    = swap.get('remove_projects', [])
        add_p    = swap.get('add_projects', [])
        vol      = swap.get('volume_constraint_check', '')
        add_strs = []
        for p in add_p:
            if isinstance(p, dict):
                add_strs.append(f"{p.get('name','')} \u2014 {p.get('justification','')}")
            else:
                add_strs.append(str(p))
        story.append(Paragraph('<b>Project Swap Directive</b>', h3))
        story.append(Paragraph('<i>Remove:</i>', body))
        for p in rem_p:
            story.append(Paragraph(f'&bull;&nbsp;&nbsp;{p}', bullet))
        story.append(Paragraph('<i>Add:</i>', body))
        for a in add_strs:
            story.append(Paragraph(f'&bull;&nbsp;&nbsp;{a}', bullet))
        if vol:
            story.append(Paragraph(f'<i>Volume check:</i> {vol}', body))
        story.append(Spacer(1, 4))

        kw = bp.get('keyword_inventory', {})
        story.append(Paragraph('<b>Keyword Inventory</b>', h3))
        for label, key in [('Hard Skills', 'hard_skills'),
                            ('Methodologies', 'methodologies'),
                            ('Domain Terms', 'domain_terms')]:
            vals = ', '.join(kw.get(key, []))
            if vals:
                story.append(Paragraph(f'<b>{label}:</b> {vals}', body))
        story.append(Spacer(1, 4))

        tuning = bp.get('technical_skills_tuning', {})
        story.append(Paragraph('<b>Technical Skills Tuning</b>', h3))
        adds = ', '.join(tuning.get('add', []))
        rems = ', '.join(tuning.get('remove', []))
        if adds: story.append(Paragraph(f'<b>Add:</b> {adds}', body))
        if rems: story.append(Paragraph(f'<b>Remove:</b> {rems}', body))
        story.append(Spacer(1, 4))

        # Quantified Outcomes — items are {original, suggested} dicts
        outcomes = bp.get('quantified_outcomes', []) or []
        if outcomes:
            story.append(Paragraph('<b>Quantified Outcomes</b>', h3))
            for o in outcomes:
                if isinstance(o, dict):
                    orig = str(o.get('original', ''))
                    sug  = str(o.get('suggested', ''))
                    story.append(Paragraph(f'&bull;&nbsp;&nbsp;<b>Original:</b> {orig}', bullet))
                    if sug:
                        story.append(Paragraph(
                            f'&nbsp;&nbsp;&nbsp;&nbsp;<b>Suggested:</b> {sug}', bullet))
                else:
                    story.append(Paragraph(f'&bull;&nbsp;&nbsp;{o}', bullet))
            story.append(Spacer(1, 4))

        cal       = bp.get('ats_threshold_calibration', {})
        meets     = cal.get('meets_target', False)
        meets_txt = ('<font color="#1a7a1a"><b>YES \u2014 Target met</b></font>' if meets
                     else '<font color="#a00000"><b>NO \u2014 Below threshold (85)</b></font>')
        story.append(Paragraph('<b>ATS Threshold Calibration</b>', h3))
        story.append(Paragraph(meets_txt, body))
        raw_remedy = cal.get('remedy_suggestions', '')
        if isinstance(raw_remedy, list):
            for r in raw_remedy:
                story.append(Paragraph(f'&bull;&nbsp;&nbsp;{r}', bullet))
        elif raw_remedy:
            story.append(Paragraph(f'<i>Remedy:</i> {raw_remedy}', body))

    # ── Post-Rewrite ATS Score ────────────────────────────────────────────────
    post = data.get('post_rewrite_ats_score') or {}
    post_matrix  = post.get('ats_score_matrix') or {}
    post_total   = post_matrix.get('total_score')
    post_delta   = post.get('score_delta')
    post_verdict = post.get('score_gate_verdict')
    post_gaps    = post.get('remaining_gaps') or []

    if post_total is not None:
        story.append(Spacer(1, 10))
        story.append(section_header('Post-Rewrite ATS Score'))
        story.append(Spacer(1, 6))

        post_table_data = [
            [Paragraph('<b>Category</b>', h3), Paragraph('<b>Score</b>', h3),
             Paragraph('<b>Max</b>', h3),      Paragraph('<b>Evaluation Criteria</b>', h3)]
        ]
        for key, label in cat_labels.items():
            if key in post_matrix:
                cat     = post_matrix[key]
                current = cat.get('current_score')
                max_s   = cat.get('max_score', 0)
                if current is None:
                    continue
                crit = str(cat.get('evaluation_criteria', ''))
                post_table_data.append([
                    Paragraph(label, body), Paragraph(str(current), body),
                    Paragraph(str(max_s), body), Paragraph(crit, body)
                ])

        post_score_color = ('#1a7a1a' if post_total >= 85
                            else '#b35900' if post_total >= 65
                            else '#a00000')
        delta_str = ''
        if post_delta is not None:
            try:
                n = int(post_delta)
                delta_str = f' (+{n})' if n > 0 else f' ({n})'
            except (ValueError, TypeError):
                delta_str = f' ({post_delta})'
        post_table_data.append([
            Paragraph('<b>Total</b>', h3),
            Paragraph(f'<b><font color="{post_score_color}">{post_total}{delta_str}</font></b>', h3),
            Paragraph('<b>100</b>', h3), Paragraph('', body)
        ])

        post_tbl = Table(post_table_data, colWidths=[140, 40, 35, printable_width - 215])
        post_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#f0f0f0')),
            ('LINEBELOW',     (0,0), (-1,0), 0.5, LINE_COLOR),
            ('LINEABOVE',     (0,-1), (-1,-1), 0.5, LINE_COLOR),
            ('LINEBELOW',     (0,-1), (-1,-1), 0.5, LINE_COLOR),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('RIGHTPADDING',  (0,0), (-1,-1), 4),
            ('TOPPADDING',    (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(post_tbl)
        story.append(Spacer(1, 8))

        if post_verdict:
            vok = str(post_verdict).upper() == 'PROCEED'
            vcolor = '#1a7a1a' if vok else '#b8860b'
            vlabel = ('\u2713 PROCEED \u2014 Target met' if vok
                      else '\u26a0 REVIEW \u2014 Still below 85 (informational, not blocking)')
            story.append(Paragraph(
                f'<b>Post-Rewrite Verdict:</b> <font color="{vcolor}"><b>{vlabel}</b></font>', body
            ))
            story.append(Spacer(1, 4))

        if post_gaps:
            story.append(Paragraph('<b>Remaining Gaps</b>', h3))
            for g in post_gaps:
                story.append(Paragraph(f'&bull;&nbsp;&nbsp;{g}', bullet))

        # Post-Rewrite Formatting Quality (optional, non-scored)
        post_fq = post.get('formatting_quality') or {}
        post_fq_verdict = str(post_fq.get('verdict', '') or '').strip()
        if post_fq_verdict:
            story.append(Spacer(1, 4))
            vlower = post_fq_verdict.lower()
            if vlower == 'excellent':
                vcolor = '#1a7a1a'
            elif vlower == 'good':
                vcolor = '#2a6a2a'
            elif vlower == 'average':
                vcolor = '#b35900'
            else:
                vcolor = '#a00000'
            story.append(Paragraph(
                f'<b>Post-Rewrite Formatting:</b> '
                f'<font color="{vcolor}"><b>{post_fq_verdict.capitalize()}</b></font>', body
            ))
            post_fq_suggestions = post_fq.get('suggestions', []) or []
            for s in post_fq_suggestions:
                story.append(Paragraph(f'&bull;&nbsp;&nbsp;{s}', bullet))

        # Post-Rewrite Semantic Similarity (optional)
        post_sim_val = post.get('post_rewrite_similarity')
        if post_sim_val is not None:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f'<b>Post-Rewrite Similarity:</b> {float(post_sim_val):.4f}', body))

    doc.build(story)
    print(f"Successfully compiled ATS Report via ReportLab: {output_path}")
