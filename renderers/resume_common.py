"""
Shared helpers for the resume renderers (LaTeX and ReportFallback).

Keeps language detection, section headers, data extraction, and common
rendering logic in one place so all four renderers stay in sync.
"""
import re

from .utils import (
    TEXT_DARK, TEXT_MUTED, LINE_COLOR,
    escape_latex,
)
from config import CANDIDATE_NAME

# ── ReportLab imports (used by ReportFallback shared functions) ───────────────
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer,
    Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

MONTH_MAP = {
    'jan': '01', 'january': '01',
    'feb': '02', 'february': '02',
    'mar': '03', 'march': '03',
    'apr': '04', 'april': '04',
    'may': '05',
    'jun': '06', 'june': '06',
    'jul': '07', 'july': '07',
    'aug': '08', 'august': '08',
    'sep': '09', 'september': '09',
    'oct': '10', 'october': '10',
    'nov': '11', 'november': '11',
    'dec': '12', 'december': '12',
    'januar': '01', 'februar': '02', 'märz': '03', 'maerz': '03',
    'mai': '05', 'juni': '06', 'juli': '07',
    'oktober': '10', 'dezember': '12',
}

# ── Constants ─────────────────────────────────────────────────────────────────

# Hardcoded dark-blue color used for name, section titles, and GitHub links
DARKBLUE_HEX = '#1A365D'

# Page margins (in inches) — shared between LaTeX and ReportFallback renderers
MARGIN_INCHES = 0.4
TOP_MARGIN_INCHES = 0.3


def format_date_numeric(date_str):
    """Convert month names in a date string to MM/YYYY numeric format.

    Examples:
      "Jan 2023 – April 2025" → "01/2023 – 04/2025"
      "08/2014 – 12/2018"     → "08/2014 – 12/2018" (already numeric)
      "present"               → "present"
    """
    if not date_str:
        return date_str

    def _replace_month(match):
        word = match.group(0).lower().strip('.,')
        year = match.group(1) if match.lastindex and match.lastindex >= 1 else ''
        # Re-match: the regex captures month word + optional year
        return MONTH_MAP.get(word, word)

    # Match month name (3+ letters) optionally followed by a year
    # Pattern: month word, then optional year (4 digits)
    def _convert(text):
        # Pattern: a month name followed by optional year
        pattern = r'\b([A-Za-zäöü]{3,})\.?\s+(\d{4})\b'
        def replacer(m):
            month_word = m.group(1).lower()
            year = m.group(2)
            numeric = MONTH_MAP.get(month_word)
            if numeric:
                return f"{numeric}/{year}"
            return m.group(0)
        return re.sub(pattern, replacer, text)

    return _convert(str(date_str))

HEADERS = {
    'english': {
        'summary': 'SUMMARY',
        'education': 'EDUCATION',
        'technical_skills': 'TECHNICAL SKILLS',
        'projects': 'PROJECTS',
        'professional_experience': 'PROFESSIONAL EXPERIENCE',
        'spoken_languages': 'SPOKEN LANGUAGES'
    },
    'german': {
        'summary': 'ZUSAMMENFASSUNG',
        'education': 'AUSBILDUNG',
        'technical_skills': 'TECHNISCHE FÄHIGKEITEN',
        'projects': 'PROJEKTE',
        'professional_experience': 'BERUFSERFAHRUNG',
        'spoken_languages': 'SPRACHEN'
    }
}

# Default order of resume sections, top to bottom. Both renderers read from
# this list so they stay in sync. A resume YAML may override the order by
# supplying a top-level `section_order` key (a list of these section keys);
# any key not present in the data is skipped, and any unknown key is ignored.
DEFAULT_SECTION_ORDER = [
    'summary',
    'technical_skills',
    'projects',
    'professional_experience',
    'education',
    'spoken_languages',
]

# German-style section order (Lebenslauf convention)
GERMAN_STYLE_SECTION_ORDER = [
    'summary',
    'professional_experience',
    'education',
    'technical_skills',
    'spoken_languages',
]


def get_section_order(data):
    """Return the section order for a resume.

    Reads `data['section_order']` if present (must be a list of section keys
    from DEFAULT_SECTION_ORDER). Falls back to DEFAULT_SECTION_ORDER.
    Unknown keys are dropped; the result preserves the caller's ordering.
    """
    raw = data.get('section_order')
    if not raw or not isinstance(raw, list):
        return list(DEFAULT_SECTION_ORDER)
    valid = set(DEFAULT_SECTION_ORDER)
    return [k for k in raw if k in valid]


def get_resume_language(data):
    # Check top-level language field first
    lang = str(data.get('language', '')).lower().strip()
    if 'german' in lang or 'deutsch' in lang or lang == 'de':
        return 'german'
    if 'english' in lang or lang == 'en':
        return 'english'

    # Fallback to key heuristics
    german_keys = {'zusammenfassung', 'ausbildung', 'berufserfahrung', 'projekte', 'sprachen', 'technische_fähigkeiten', 'technische fähigkeiten'}
    for key in german_keys:
        if key in data:
            return 'german'

    return 'english'


# ── Section order helpers ─────────────────────────────────────────────────────

def get_german_section_order(data):
    """Return section order for German-style resumes.

    German style uses its own fixed order — no YAML override needed.
    But respect section_order if explicitly provided (for flexibility).
    """
    raw_order = data.get('section_order')
    if raw_order and isinstance(raw_order, list):
        valid = set(GERMAN_STYLE_SECTION_ORDER)
        return [k for k in raw_order if k in valid]
    return list(GERMAN_STYLE_SECTION_ORDER)


# ── Data extraction helpers (format-agnostic) ────────────────────────────────

def get_contact_info(data):
    """Extract and normalize contact info from resume data."""
    contact = data.get('contact_info', {})
    raw_name = contact.get('name', CANDIDATE_NAME)
    if raw_name.isupper():
        raw_name = raw_name.title()
    return {
        'name': raw_name,
        'location': contact.get('location', ''),
        'phone': contact.get('phone', ''),
        'github': contact.get('github', ''),
        'email': contact.get('email', ''),
        'linkedin': contact.get('linkedin', ''),
        'visa': contact.get('visa', ''),
        'availability': contact.get('availability', ''),
    }


def get_summary_text(data):
    """Extract summary text from resume data (handles list or string)."""
    summary_val = data.get('summary', data.get('zusammenfassung'))
    if not summary_val:
        return ""
    return " ".join(summary_val) if isinstance(summary_val, list) else summary_val


def get_education_list(data):
    """Extract education list from resume data."""
    return data.get('education', data.get('ausbildung', []))


def get_skills_list(data):
    """Extract technical skills list from resume data."""
    return data.get('technical_skills', data.get('technische_fähigkeiten', data.get('technische fähigkeiten', [])))


def get_projects_list(data):
    """Extract projects list from resume data."""
    return data.get('projects', data.get('projekte', []))


def get_experience_list(data):
    """Extract professional experience list from resume data."""
    return data.get('professional_experience', data.get('berufserfahrung', []))


def get_languages_list(data):
    """Extract spoken languages list from resume data."""
    return data.get('languages', data.get('spoken_languages', data.get('sprachen', [])))


# ── LaTeX-specific shared functions ───────────────────────────────────────────

def generate_latex_contact_header(data):
    """Generate the LaTeX header (name + contact lines).

    Returns the header_tex string.
    """
    # 1. Parse contact info and format header
    contact = data.get('contact_info', {})
    raw_name = contact.get('name', CANDIDATE_NAME)
    if raw_name.isupper():
        raw_name = raw_name.title()
    name = escape_latex(raw_name)

    loc    = escape_latex(contact.get('location', ''))
    phone  = escape_latex(contact.get('phone', ''))
    github = contact.get('github', '')
    email  = contact.get('email', '')
    linkedin = contact.get('linkedin', '')
    visa   = escape_latex(contact.get('visa', ''))
    avail  = escape_latex(contact.get('availability', ''))

    # Contact line 1
    line1_parts = []
    if loc:   line1_parts.append(loc)
    if phone: line1_parts.append(phone)
    if github:
        github_clean = github.replace('https://', '').replace('http://', '')
        line1_parts.append(f"\\href{{https://{github_clean}}}{{{escape_latex(github_clean)}}}")
    line1 = " $\\cdot$ ".join(line1_parts)

    # Contact line 2
    line2_parts = []
    if email:
        line2_parts.append(f"\\href{{mailto:{email}}}{{{escape_latex(email)}}}")
    if linkedin:
        linkedin_clean = linkedin.replace('https://', '').replace('http://', '')
        line2_parts.append(f"\\href{{https://{linkedin_clean}}}{{{escape_latex(linkedin_clean)}}}")
    line2 = " $\\cdot$ ".join(line2_parts)

    # Contact line 3
    line3_parts = []
    if visa:  line3_parts.append(visa)
    if avail: line3_parts.append(avail)
    line3 = " $\\cdot$ ".join(line3_parts)

    contact_lines = [l for l in [line1, line2, line3] if l]
    contact_details_str = " \\\\\n  ".join(contact_lines)

    # 2. Header (no photo — name is the dominant element)
    header_tex = f"""{{\\Huge\\bfseries\\color{{darkblue}} {name}}} \\\\[6pt]
{{\\small
{contact_details_str}
}}
\\vspace{{0pt}}"""

    return header_tex


def generate_latex_summary_tex(data, h):
    """Generate LaTeX summary section."""
    # A. Summary
    summary_text = ""
    summary_val = data.get('summary', data.get('zusammenfassung'))
    if summary_val:
        summary_text = escape_latex(" ".join(summary_val) if isinstance(summary_val, list) else summary_val)
    summary_tex = (
        f"\\vspace{{6pt}}\n"
        f"\\section{{{h['summary']}}}\n"
        f"{summary_text}"
    ) if summary_text else ""
    return summary_tex


def generate_latex_education_tex(data, h):
    """Generate LaTeX education section."""
    edu_tex_items = []
    edu_list = data.get('education', data.get('ausbildung', []))
    for edu in edu_list:
        degree = escape_latex(edu.get('degree', ''))
        univ   = escape_latex(edu.get('university', ''))
        date   = escape_latex(edu.get('date', ''))
        edu_tex_items.append(f"\\eduEntry{{{degree}}}{{{univ}}}{{{date}}}")
    education_body = " \\\\\n".join(edu_tex_items)
    education_tex = (
        f"\\section{{{h['education']}}}\n"
        f"{education_body}"
    ) if edu_tex_items else ""
    return education_tex


def generate_latex_skills_tex(data, h):
    """Generate LaTeX technical skills section."""
    # C. Technical Skills
    skills_tex_items = []
    skills_list = data.get('technical_skills', data.get('technische_fähigkeiten', data.get('technische fähigkeiten', [])))
    for skill_cat in skills_list:
        cat    = escape_latex(skill_cat.get('category', ''))
        skills = [escape_latex(s) for s in skill_cat.get('skills', [])]
        skills_joined = " $\\cdot$ ".join(skills)
        skills_tex_items.append(f"{{\\hangindent=6pt\\relax \\textbf{{{cat}:}} {skills_joined}}}")
    skills_body = "\\\\[1pt]\n".join(skills_tex_items)
    skills_tex = (
        f"\\section{{{h['technical_skills']}}}\n"
        f"{skills_body}"
    ) if skills_tex_items else ""
    return skills_tex


def _clean_prose(text: str) -> str:
    """Clean joined bullet prose: fix orphan punctuation, double periods,
    and extra spaces introduced by joining bullets with spaces.

    - Collapses multiple spaces to one
    - Removes space before punctuation (. , ; : ! ?)
    - Collapses double/triple periods to one
    - Strips leading/trailing whitespace
    """
    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text)
    # Remove space before punctuation
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    # Collapse repeated periods (e.g. ".." or "..." from bullet ends)
    text = re.sub(r'\.{2,}', '.', text)
    # Fix period followed by space then period (e.g. ". ." -> ".")
    text = re.sub(r'\.\s+\.', '.', text)
    # Re-collapse any multiple spaces introduced by substitutions
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

def generate_latex_projects_tex(data, h, strip_trailing_dot=True, vspace='6pt'):
    """Generate LaTeX projects section.

    Projects — single-paragraph format: name --- [GitHub] --- summary
    The project name, em-dash separators (---), and link markup are excluded
    from the character count; only the summary text counts toward the
    <= 300 char (English) / <= 280 char (German) limit.

    Args:
        strip_trailing_dot: If True, strip trailing period from summary (US style).
                           If False, add trailing period (German style).
        vspace: Vertical space between project entries.
    """
    proj_tex_items = []
    projects_list = data.get('projects', data.get('projekte', []))
    for i, proj in enumerate(projects_list):
        proj_name  = escape_latex(proj.get('name', ''))
        repo_url   = proj.get('repo_url', proj.get('url', ''))
        bullets    = [escape_latex(b) for b in proj.get('bullets', [])]
        summary    = _clean_prose(" ".join(bullets))

        # \noindent\textbf{Name} --- \href{repo_url}{[GitHub]} --- summary.\par
        # When no repo_url: \noindent\textbf{Name} --- summary.\par
        link_tex = f" --- \\href{{{repo_url}}}{{\\color{{darkblue}}\\small[GitHub]}}" if repo_url else ""
        if strip_trailing_dot:
            item_tex = f"\\noindent\\textbf{{{proj_name}}}{link_tex} --- {summary.rstrip('.')}\\par"
        else:
            item_tex = f"\\noindent\\textbf{{{proj_name}}}{link_tex} --- {summary}.\\par"

        if i == 0:
            proj_tex_items.append(
                f"\\section{{{h['projects']}}}\n"
                f"\\vspace{{2pt}}\n"
                f"{item_tex}"
            )
        else:
            proj_tex_items.append(item_tex)
    projects_tex = f"\n\\vspace{{{vspace}}}\n".join(proj_tex_items) if proj_tex_items else ""
    return projects_tex


def generate_latex_experience_tex(data, h, include_project_bullets=False):
    """Generate LaTeX professional experience section.

    Args:
        include_project_bullets: If True, include project-style bullets
                                 (name --- [GitHub] --- summary format, German only).
    """
    # E. Professional Experience
    exp_tex_items = []
    exp_list = data.get('professional_experience', data.get('berufserfahrung', []))
    for i, exp in enumerate(exp_list):
        company    = escape_latex(exp.get('company', ''))
        date       = escape_latex(format_date_numeric(exp.get('date', '')))
        title      = escape_latex(exp.get('title', ''))
        bullets    = [escape_latex(b) for b in exp.get('bullets', [])]

        # Project-style bullets (name --- [GitHub] --- summary format)
        proj_bullets_tex = ""
        if include_project_bullets:
            project_bullets = exp.get('project_bullets', [])
            if project_bullets:
                proj_lines = []
                for pb in project_bullets:
                    pb_name    = escape_latex(pb.get('name', ''))
                    pb_url     = pb.get('repo_url', pb.get('url', ''))
                    pb_bullets = [escape_latex(b) for b in pb.get('bullets', [])]
                    pb_summary = _clean_prose(" ".join(pb_bullets))
                    pb_link = f" --- \\href{{{pb_url}}}{{\\color{{darkblue}}\\small[GitHub]}}" if pb_url else ""
                    proj_lines.append(f"  \\resumeItem{{\\textbf{{{pb_name}}}{pb_link} --- {pb_summary.rstrip('.')}.}}")
                proj_bullets_tex = "\n".join(proj_lines) + "\n"

        bullets_tex = "\n".join([f"  \\resumeItem{{{b}}}" for b in bullets])
        all_bullets_tex = "\n".join(filter(None, [proj_bullets_tex, bullets_tex]))

        item_tex = (
            f"\\jobEntry{{{company}}}{{{date}}}\\\\*\n"
            f"\\vspace{{2pt}}\n"
            f"\\jobTitle{{{title}}}\n"
            f"\\vspace{{2pt}}\n"
            f"\\begin{{itemize}}[leftmargin=1.2em, itemindent=0pt, labelsep=0.4em, labelwidth=0.5em, nosep, itemsep=1pt]\n{all_bullets_tex}\n\\end{{itemize}}\\par"
        )
        if i == 0:
            exp_tex_items.append(
                f"\\section{{{h['professional_experience']}}}\n"
                f"\\vspace{{2pt}}\n"
                f"{item_tex}"
            )
        else:
            exp_tex_items.append(item_tex)
    experience_tex = "\n\\vspace{6pt}\n".join(exp_tex_items) if exp_tex_items else ""
    return experience_tex


def generate_latex_languages_tex(data, h):
    """Generate LaTeX spoken languages section."""
    # F. Spoken Languages
    lang_items = data.get('languages', data.get('spoken_languages', data.get('sprachen', [])))
    if lang_items:
        lang_joined = " $\\cdot$ ".join([escape_latex(l) for l in lang_items])
        lang_tex = (
            f"\\section{{{h['spoken_languages']}}}\n"
            f"{lang_joined}"
        )
    else:
        lang_tex = ""
    return lang_tex


def generate_latex_document(header_tex, body_tex):
    """Generate the complete LaTeX document source.

    4. Generate LaTeX document
    """
    tex_content = f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[margin={MARGIN_INCHES}in]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage{{titlesec}}
\\usepackage{{hyperref}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{lmodern}}
\\usepackage{{graphicx}}
\\usepackage{{textcomp}}
\\usepackage{{xcolor}}
\\usepackage[protrusion=true,expansion=true,stretch=40,shrink=40]{{microtype}}
\\tolerance=2000
\\hbadness=10000

\\input{{glyphtounicode}}
\\pdfgentounicode=1
\\usepackage[none]{{hyphenat}}

\\definecolor{{darkblue}}{{HTML}}{{{DARKBLUE_HEX.lstrip('#')}}}
\\definecolor{{BLACK}}{{HTML}}{{000000}}

\\pagestyle{{empty}}
\\setlength{{\\parindent}}{{0pt}}
\\setlength{{\\emergencystretch}}{{3em}}

\\titleformat{{\\section}}{{\\large\\bfseries\\color{{darkblue}}}}{{}}{{0em}}{{}}[\\color{{black}}\\titlerule]
\\titlespacing{{\\section}}{{0pt}}{{6pt}}{{4pt}}

\\newcommand{{\\resumeItem}}[1]{{\\item[$\\cdot$] \\fussy {{#1}}}}
\\newcommand{{\\eduEntry}}[3]{{\\textbf{{#1}} {{\\small\\textit{{#2}}}} \\hfill {{\\small\\textit{{#3}}}}}}
\\newcommand{{\\resumeProject}}[1]{{{{\\normalsize\\textbf{{#1}}}}}}
\\newcommand{{\\jobEntry}}[2]{{{{\\normalsize\\textbf{{#1}} \\hfill {{\\normalsize#2}}}}}}
\\newcommand{{\\jobTitle}}[1]{{{{\\small\\textit{{#1}}}}}}

\\hypersetup{{colorlinks=true,urlcolor=black,linkcolor=black}}

\\begin{{document}}

{header_tex}

{body_tex}

\\end{{document}}
"""
    return tex_content


# ── ReportLab-specific shared functions ───────────────────────────────────────

def create_reportlab_doc(output_path):
    """Create a BaseDocTemplate with a zero-padding frame for resume rendering.

    Use BaseDocTemplate with a zero-padding frame so that Tables (section
    headers) and Paragraphs (body text) both start at the exact same x
    position. SimpleDocTemplate uses a default 6pt frame padding which
    causes Paragraphs to appear 6pt indented relative to Tables.
    Top margin is 0 — content starts from the very top edge of the page.

    Returns (doc, printable_width).
    """
    margin = MARGIN_INCHES * inch
    top_margin = TOP_MARGIN_INCHES * inch
    printable_width = A4[0] - (2 * margin)
    printable_height = A4[1] - margin - top_margin
    doc = BaseDocTemplate(
        output_path, pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=top_margin, bottomMargin=margin,
    )
    frame = Frame(
        margin, margin, printable_width, printable_height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id='normal',
    )
    doc.addPageTemplates([PageTemplate(id='all', frames=[frame], pagesize=A4)])
    return doc, printable_width


def create_reportlab_styles(F_REG, F_BOLD, F_ITALIC, F_BOLDITALIC):
    """Create all ParagraphStyle objects for the resume renderers.

    Returns a dict of style objects keyed by name.
    """
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        'ResName', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=23, leading=26, textColor=colors.HexColor(DARKBLUE_HEX),
        leftIndent=0, firstLineIndent=0,
    )
    contact_style = ParagraphStyle(
        'ResContact', parent=styles['Normal'],
        fontName=F_REG, fontSize=10, leading=11.5, textColor=TEXT_MUTED,
        leftIndent=0, firstLineIndent=0,
    )
    section_title_style = ParagraphStyle(
        'ResSectionTitle', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=12, leading=13, textColor=colors.HexColor(DARKBLUE_HEX),
        leftIndent=0, firstLineIndent=0,
    )
    summary_style = ParagraphStyle(
        'ResSummary', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=13.5, alignment=4, textColor=TEXT_DARK,
        leftIndent=0, firstLineIndent=0,
    )
    comp_style = ParagraphStyle(
        'ResComp', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=11, leading=12.5, textColor=colors.black,
        leftIndent=0, firstLineIndent=0,
    )
    date_style = ParagraphStyle(
        'ResDate', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=12.5, alignment=2, textColor=TEXT_DARK,
        leftIndent=0, firstLineIndent=0,
    )
    title_style = ParagraphStyle(
        'ResTitle', parent=styles['Normal'],
        fontName=F_ITALIC, fontSize=10, leading=11.5, textColor=TEXT_MUTED,
        leftIndent=0, firstLineIndent=0,
    )
    bullet_style = ParagraphStyle(
        'ResBullet', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=13.5,
        leftIndent=16, firstLineIndent=-16, bulletIndent=0,
        alignment=4,  # TA_JUSTIFY
        spaceAfter=1, textColor=TEXT_DARK,
    )
    skill_val_style = ParagraphStyle(
        'ResSkillVal', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=13,
        leftIndent=0, firstLineIndent=0, textColor=TEXT_DARK,
    )
    proj_title_style = ParagraphStyle(
        'ResProjTitle', parent=styles['Normal'],
        fontName=F_BOLD, fontSize=11, leading=12.5, textColor=colors.black,
        leftIndent=0, firstLineIndent=0,
    )
    # Single-paragraph project prose style (mirrors the LaTeX polished format)
    proj_para_style = ParagraphStyle(
        'ResProjPara', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=13.5, alignment=4,
        leftIndent=0, firstLineIndent=0, spaceAfter=1, textColor=TEXT_DARK,
    )
    # Education: degree bold + university italic only (not bold), same font size
    edu_style = ParagraphStyle(
        'ResEdu', parent=styles['Normal'],
        fontName=F_REG, fontSize=11, leading=12.5, textColor=colors.black,
        leftIndent=0, firstLineIndent=0,
    )

    return {
        'name': name_style,
        'contact': contact_style,
        'section_title': section_title_style,
        'summary': summary_style,
        'comp': comp_style,
        'date': date_style,
        'title': title_style,
        'bullet': bullet_style,
        'skill_val': skill_val_style,
        'proj_title': proj_title_style,
        'proj_para': proj_para_style,
        'edu': edu_style,
    }


def generate_reportlab_contact_header(data, name_style, contact_style):
    """Generate the header flowables (name + contact lines).

    Name on its own line, large; contact lines below in small muted text.
    """
    # Header (no photo — name is the dominant element)
    contact  = data.get('contact_info', {})
    raw_name = contact.get('name', CANDIDATE_NAME)
    if raw_name.isupper():
        raw_name = raw_name.title()
    name_str = f"<font color='{DARKBLUE_HEX}'><b>{raw_name}</b></font>"

    loc    = contact.get('location', '')
    phone  = contact.get('phone', '')
    github = contact.get('github', '')
    line1_parts = []
    if loc:   line1_parts.append(loc)
    if phone: line1_parts.append(phone)
    if github:
        line1_parts.append(f"<a href='https://{github}' color='#0000EE'>{github}</a>")
    line1 = " &nbsp;&bull;&nbsp; ".join(line1_parts)

    email    = contact.get('email', '')
    linkedin = contact.get('linkedin', '')
    line2_parts = []
    if email:
        line2_parts.append(f"<a href='mailto:{email}' color='#0000EE'>{email}</a>")
    if linkedin:
        line2_parts.append(f"<a href='https://{linkedin}' color='#0000EE'>{linkedin}</a>")
    line2 = " &nbsp;&bull;&nbsp; ".join(line2_parts)

    visa  = contact.get('visa', '')
    avail = contact.get('availability', '')
    line3_parts = []
    if visa:  line3_parts.append(visa)
    if avail: line3_parts.append(avail)
    line3 = " &nbsp;&bull;&nbsp; ".join(line3_parts)

    contact_lines = [l for l in [line1, line2, line3] if l]
    contact_html = "<br/>".join(contact_lines)

    return [
        Paragraph(name_str, name_style),
        Spacer(1, 2),
        Paragraph(f"<font size=9.5 color='#333333'>{contact_html}</font>", contact_style),
        Spacer(1, 5),
    ]


def make_section_header(title, section_title_style, printable_width, top_padding):
    """Create a section header Table with a bottom rule."""
    t = Table([[Paragraph(f"<b>{title.upper()}</b>", section_title_style)]], colWidths=[printable_width])
    t.setStyle(TableStyle([
        ('LINEBELOW',     (0,0), (-1,-1), 0.5, LINE_COLOR),
        ('TOPPADDING',    (0,0), (-1,-1), top_padding),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('RIGHTPADDING',  (0,0), (-1,-1), 0),
    ]))
    return t


# ── ReportLab spacing configs ─────────────────────────────────────────────────
# US and German renderers differ only in spacing values; these dicts make the
# differences explicit and data-driven.

US_SPACING = {
    'section_header_toppadding': 4,
    'summary_trailing': 4,
    'skills_trailing': 4,
    'projects_last': 2,
    'exp_after_table': 3,
    'exp_last': 2,
    'languages_trailing': 4,
}

GERMAN_SPACING = {
    'section_header_toppadding': 7,
    'summary_trailing': 7,
    'skills_trailing': 7,
    'projects_last': 5,
    'exp_after_table': 5,
    'exp_last': 5,
    'languages_trailing': 7,
}


# ── ReportLab section renderers ───────────────────────────────────────────────
# Each function takes a ReportLabRenderContext and returns a list of flowables.
# Section renderers — each returns a list of flowables for one section.
# The main body iterates over the (optionally YAML-overridden) section
# order and extends `story` with whichever the renderer produces, so the
# layout order is data-driven rather than hardcoded.

class ReportLabRenderContext:
    """Holds shared state for ReportLab section renderers."""
    def __init__(self, data, h, add_section_header, styles, spacing, include_project_bullets=False):
        self.data = data
        self.h = h
        self.add_section_header = add_section_header
        self.styles = styles
        self.spacing = spacing
        self.include_project_bullets = include_project_bullets


def render_summary_rl(ctx):
    """Render the summary section as ReportLab flowables."""
    summary_val = ctx.data.get('summary', ctx.data.get('zusammenfassung'))
    if not summary_val:
        return []
    return [
        ctx.add_section_header(ctx.h['summary']),
        Spacer(1, 4),
        Paragraph(
            " ".join(summary_val) if isinstance(summary_val, list) else summary_val,
            ctx.styles['summary'],
        ),
        Spacer(1, ctx.spacing['summary_trailing'])
    ]


def render_technical_skills_rl(ctx):
    """Render the technical skills section as ReportLab flowables."""
    skills_list = get_skills_list(ctx.data)
    if not skills_list:
        return []
    block = [
        ctx.add_section_header(ctx.h['technical_skills']),
        Spacer(1, 4)
    ]
    for i, cat in enumerate(skills_list):
        category_name = cat.get('category', '')
        skills_joined = " &bull; ".join(cat.get('skills', []))
        block.append(Paragraph(f"<b>{category_name}:</b> {skills_joined}", ctx.styles['skill_val']))
        if i < len(skills_list) - 1:
            block.append(Spacer(1, 1))
    block.append(Spacer(1, ctx.spacing['skills_trailing']))
    return block


def render_projects_rl(ctx):
    """Render the projects section as ReportLab flowables.

    Single-paragraph format: name --- [GitHub] --- summary
    Mirrors the LaTeX layout. The project name, em-dash separators,
    and link markup are excluded from the character count; only the
    summary text counts toward the <= 300 char (English) /
    <= 280 char (German) limit.
    """
    projects_list = get_projects_list(ctx.data)
    if not projects_list:
        return []
    block = []
    for i, proj in enumerate(projects_list):
        if i == 0:
            block.append(ctx.add_section_header(ctx.h['projects']))
            block.append(Spacer(1, 4))
        name       = proj.get('name', '')
        repo_url   = proj.get('repo_url', proj.get('url', ''))
        bullets    = proj.get('bullets', [])
        prose      = _clean_prose(" ".join(bullets))

        # Build: <b>Name</b> --- <a href='repo_url'>[GitHub]</a> --- summary
        # When no repo_url: <b>Name</b> --- summary
        github_link = f" --- <a href='{repo_url}' color='{DARKBLUE_HEX}'><font size=8>[GitHub]</font></a>" if repo_url else ""
        line = f"<b>{name}</b>{github_link} --- {prose.rstrip('.')}."

        block.append(Paragraph(line, ctx.styles['proj_para']))
        # 4pt gap between projects; tighter gap after last project
        block.append(Spacer(1, 4 if i < len(projects_list) - 1 else ctx.spacing['projects_last']))
    return block


def render_professional_experience_rl(ctx):
    """Render the professional experience section as ReportLab flowables."""
    exp_list = get_experience_list(ctx.data)
    if not exp_list:
        return []
    block = []
    for i, exp in enumerate(exp_list):
        if i == 0:
            block.append(ctx.add_section_header(ctx.h['professional_experience']))
            block.append(Spacer(1, 4))
        company    = exp.get('company', '')
        date_range = format_date_numeric(exp.get('date', ''))
        job_title  = exp.get('title', '')
        bullets    = exp.get('bullets', [])

        row1_left  = Paragraph(f"<b>{company}</b>", ctx.styles['comp'])
        row1_right = Paragraph(date_range, ctx.styles['date'])
        exp_table_data = [[row1_left, row1_right]]
        if job_title:
            exp_table_data.append([Paragraph(f"<i>{job_title}</i>", ctx.styles['title']), Paragraph("", ctx.styles['date'])])

        exp_table = Table(exp_table_data, colWidths=[387, 150])
        exp_table.setStyle(TableStyle([
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 0),
            ('RIGHTPADDING',  (0,0), (-1,-1), 0),
            ('TOPPADDING',    (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        block.append(exp_table)
        block.append(Spacer(1, ctx.spacing['exp_after_table']))

        # Project-style bullets (name --- [GitHub] --- summary format)
        if ctx.include_project_bullets:
            project_bullets = exp.get('project_bullets', [])
            for pb in project_bullets:
                pb_name    = pb.get('name', '')
                pb_url     = pb.get('repo_url', pb.get('url', ''))
                pb_bullets = pb.get('bullets', [])
                pb_prose   = _clean_prose(" ".join(pb_bullets))
                pb_github  = f" --- <a href='{pb_url}' color='{DARKBLUE_HEX}'><font size=8>[GitHub]</font></a>" if pb_url else ""
                pb_line    = f"<b>{pb_name}</b>{pb_github} --- {pb_prose.rstrip('.')}."
                block.append(Paragraph(f"<bullet>&bull;&nbsp;&nbsp;</bullet>{pb_line}", ctx.styles['bullet']))

        for b in bullets:
            block.append(Paragraph(f"<bullet>&bull;&nbsp;&nbsp;</bullet>{b}", ctx.styles['bullet']))
        # 4pt gap between companies; tighter gap after last entry
        block.append(Spacer(1, 4 if i < len(exp_list) - 1 else ctx.spacing['exp_last']))
    return block


def render_education_rl(ctx):
    """Render the education section as ReportLab flowables.

    degree (bold) + university (italic only, not bold) on the left,
    date right-aligned (same two-column layout as Professional Experience).
    """
    edu_list = get_education_list(ctx.data)
    if not edu_list:
        return []
    block = [
        ctx.add_section_header(ctx.h['education']),
        Spacer(1, 4)
    ]
    for edu in edu_list:
        degree      = edu.get('degree', '')
        univ        = edu.get('university', '')
        completion  = edu.get('date', '')
        # Keep degree + university on one line: use non-breaking spaces in
        # university name so ReportLab never wraps mid-name. Adaptive font
        # size for the university so long names shrink instead of wrapping.
        univ_nbsp   = univ.replace(' ', '&nbsp;')
        degree_len  = len(degree)
        univ_len    = len(univ)
        # Base university font size is 10pt; shrink for long combined lines
        if degree_len + univ_len <= 55:
            univ_size = 10
        elif degree_len + univ_len <= 65:
            univ_size = 9.5
        elif degree_len + univ_len <= 75:
            univ_size = 9
        else:
            univ_size = 8.5
        left_para   = Paragraph(f"<b>{degree}</b> <font size={univ_size}><i>{univ_nbsp}</i></font>", ctx.styles['edu'])
        right_para  = Paragraph(completion, ctx.styles['date'])
        edu_table   = Table([[left_para, right_para]], colWidths=[400, 137])
        edu_table.setStyle(TableStyle([
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING',   (0,0), (-1,-1), 0),
            ('RIGHTPADDING',  (0,0), (-1,-1), 0),
            ('TOPPADDING',    (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        block.append(edu_table)
        block.append(Spacer(1, 3))
    return block


def render_spoken_languages_rl(ctx):
    """Render the spoken languages section as ReportLab flowables."""
    lang_items = get_languages_list(ctx.data)
    if not lang_items:
        return []
    return [
        ctx.add_section_header(ctx.h['spoken_languages']),
        Spacer(1, 3),
        Paragraph(" &bull; ".join(lang_items), ctx.styles['skill_val']),
        Spacer(1, ctx.spacing['languages_trailing'])
    ]
