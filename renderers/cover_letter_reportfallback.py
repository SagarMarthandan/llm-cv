"""
Cover letter ReportFallback renderer.

Produces a DIN 5008 Form B-compliant Geschäftsbrief layout via ReportLab:
  - Anschriftfeld (small sender line + recipient block for window envelopes)
  - Right-aligned date
  - Bold subject line (Betreff)
  - Salutation, body paragraphs, closing + signature
  - Anlagen (enclosures) section after signature
  - Footer line with phone/email at the bottom of the page

Used in two cases:
  1. The user selects `reportfallback` as the render mode at pipeline start.
  2. The LaTeX renderer fails to compile and this renderer is triggered
     automatically as a fallback.
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from .utils import TEXT_DARK, format_address, register_lm_roman_10, strip_gender_tags


def create_cover_letter_pdf_reportlab(data, output_path):
    F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC = register_lm_roman_10()

    margin = 1.0 * inch
    styles = getSampleStyleSheet()

    # ── Styles ────────────────────────────────────────────────────────────
    # Small sender line at top of Anschriftfeld (DIN 5008: ~8pt, single line)
    sender_line_style = ParagraphStyle(
        'CLSenderLine', parent=styles['Normal'],
        fontName=F_REG, fontSize=8, leading=10, textColor=colors.HexColor('#333333'),
    )
    # Recipient block below the sender line (DIN 5008: 11pt)
    recipient_style = ParagraphStyle(
        'CLRecipient', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=13.5, textColor=colors.black,
    )
    date_style = ParagraphStyle(
        'CLDate', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=13.5, alignment=2, textColor=colors.black,
    )
    subject_style = ParagraphStyle(
        'CLSubject', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=12, leading=14.5, textColor=colors.black,
    )
    body_style = ParagraphStyle(
        'CLBody', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=14.5, alignment=4, textColor=TEXT_DARK,
    )
    left_body_style = ParagraphStyle(
        'CLLeftBody', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=14.5, alignment=0, textColor=TEXT_DARK,
    )
    enclosures_style = ParagraphStyle(
        'CLEnclosures', parent=styles['Normal'],
        fontName=F_REG, fontSize=10, leading=12, textColor=TEXT_DARK,
        leftIndent=0, firstLineIndent=0,
    )

    # ── Footer callback (phone/email at bottom of page) ───────────────────
    sender = data.get('sender', {})
    footer_phone = sender.get('phone', '')
    footer_email = sender.get('email', '')
    footer_parts = []
    if footer_phone:
        footer_parts.append(footer_phone)
    if footer_email:
        footer_parts.append(footer_email)
    footer_text = "  |  ".join(footer_parts)

    def _draw_footer(canvas, doc):
        if not footer_text:
            return
        canvas.saveState()
        canvas.setFont(F_REG, 9)
        canvas.setFillColor(colors.HexColor('#444444'))
        footer_y = 0.6 * inch
        canvas.drawString(margin, footer_y, footer_text)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
    )

    story = []

    # ── Anschriftfeld (DIN 5008 Form B) ───────────────────────────────────
    # Small sender line: "Name · Address" (single line, ~8pt)
    raw_sender = sender.get('name', '')
    if raw_sender.isupper():
        raw_sender = raw_sender.title()
    sender_addr_raw = sender.get('address', '')
    if isinstance(sender_addr_raw, list):
        sender_addr_short = ", ".join(sender_addr_raw)
    else:
        sender_addr_short = sender_addr_raw
    sender_line = f"{raw_sender}"
    if sender_addr_short:
        sender_line += f" &middot; {sender_addr_short}"
    story.append(Paragraph(sender_line, sender_line_style))
    story.append(Spacer(1, 4))

    # Recipient block
    recipient = data.get('recipient', {})
    rec_addr = format_address(recipient.get('address', ''), latex=False)
    rec_text = f"<b>{recipient.get('company', '')}</b><br/>{recipient.get('department', '')}<br/>{rec_addr}"
    story.append(Paragraph(rec_text, recipient_style))
    story.append(Spacer(1, 10))

    # ── Date (right-aligned) ──────────────────────────────────────────────
    story.append(Paragraph(data.get('date', ''), date_style))
    story.append(Spacer(1, 42))

    # ── Subject (Betreff, bold) ───────────────────────────────────────────
    story.append(Paragraph(f"<b>{strip_gender_tags(data.get('subject', ''))}</b>", subject_style))
    story.append(Spacer(1, 10))

    # ── Salutation ────────────────────────────────────────────────────────
    story.append(Paragraph(data.get('salutation', 'Sehr geehrte Damen und Herren,'), left_body_style))
    story.append(Spacer(1, 6))

    # ── Body paragraphs ───────────────────────────────────────────────────
    for p in data.get('paragraphs', []):
        story.append(Paragraph(p, body_style))
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 8))

    # ── Closing + signature ───────────────────────────────────────────────
    closing = data.get('closing', 'Mit freundlichen Grüßen,')
    sig_name = data.get('signature_name', '')
    if sig_name.isupper():
        sig_name = sig_name.title()
    story.append(Paragraph(f"{closing}<br/><br/><br/><br/><b>{sig_name}</b>", left_body_style))

    # ── Anlagen (enclosures) ──────────────────────────────────────────────
    enclosures = data.get('enclosures', [])
    if enclosures:
        story.append(Spacer(1, 12))
        if isinstance(enclosures, list):
            enc_text = "<b>Anlagen:</b><br/>" + "<br/>".join(enclosures)
        else:
            enc_text = f"<b>Anlagen:</b><br/>{enclosures}"
        story.append(Paragraph(enc_text, enclosures_style))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    print(f"Successfully compiled Cover Letter via ReportLab (LM Roman 10): {output_path}")
