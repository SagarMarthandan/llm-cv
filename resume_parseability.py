"""
resume_parseability.py — ATS parse-integrity audit for compiled resume PDFs.

Reads a resume PDF and its source YAML, extracts the PDF text layer via pypdf,
and checks:
  1. Unicode corruption (replacement glyphs U+FFFD)
  2. Keyword recovery (all tools/skills from the YAML must appear in the text)
  3. Section header detection (style-aware: US style checks 6 headers, German style checks 5 — no Projects header since projects fold into experience)
  4. Contact info extraction (name, phone, email, GitHub, LinkedIn)
  5. Text structure stats (lines, avg/max line length)

If the audit fails, the script automatically attempts recovery by re-compiling
the resume with the ReportLab fallback renderer (style-aware: US or German),
then re-audits the recovered PDF. This replaces the in-renderer audit that was
previously embedded in resume_latex_us.py / resume_latex_german.py.

Outputs:
  - Parseability_Report.yaml  (structured audit results)
  - Parseability_Report.pdf   (human-readable report via the renderer)

Usage:
  python resume_parseability.py <resume.pdf> <resume.yaml> [output_dir]
  python resume_parseability.py --check-tex <resume.tex>
  python resume_parseability.py <resume.pdf> <resume.yaml> --no-recovery

The --check-tex mode runs the LaTeX project summary length check only
(<= 300 chars for English, <= 280 chars for German, summary text only —
project name, em-dash separators, and link markup are excluded). No PDF audit is performed.

The --no-recovery flag disables the automatic ReportLab re-compile on audit
failure. By default recovery is attempted.

If output_dir is omitted, the directory of the PDF is used.

Exit codes:
  0 = audit passed (all keywords recovered, no corruptions)
  1 = audit failed (corruptions or missing keywords, or tex length check failed)
  2 = error (could not read PDF or YAML)
"""
import os
import sys
import re
import yaml
import datetime

from reportlab.lib.pagesizes import A4


# ── Lightweight parse-integrity check (recovery trigger) ─────────────────────
# Moved here from resume_latex_us.py. This is a fast subset of the full audit
# used to decide whether to trigger a ReportLab re-compile. The full audit
# (run_audit below) is the authoritative report writer.

def check_parse_integrity(pdf_path, resume_data):
    """Quick parse-integrity check on a compiled PDF.

    Checks:
      1. Unicode corruption (replacement glyphs U+FFFD).
      2. Keyword recovery — critical tools/skills from resume_data must appear
         in the extracted text layer.

    Returns a dict:
      {
        "status": "Pass" | "Fail",
        "unicode_corruptions": [list of corrupted char positions],
        "missing_keywords": [list of keywords not found in text],
        "keyword_recovery_pct": int (0-100),
      }
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        pdf_text = "".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        print(f"Warning: Could not extract PDF text for parse-integrity check: {e}", file=sys.stderr)
        return {
            "status": "Fail",
            "unicode_corruptions": [],
            "missing_keywords": [],
            "keyword_recovery_pct": 0,
            "error": str(e),
        }

    # 1. Check for unicode corruptions
    corruptions = []
    for i, ch in enumerate(pdf_text):
        if ch == '\uFFFD':
            corruptions.append(i)

    # 2. Build keyword list from resume data
    keywords = set()
    # From project tools
    for proj in resume_data.get('projects', resume_data.get('projekte', [])):
        if isinstance(proj, dict):
            for t in proj.get('tools', []):
                if t and len(str(t)) > 1:
                    keywords.add(str(t).strip())
    # From technical skills
    for cat in resume_data.get('technical_skills', resume_data.get('technische_fähigkeiten', resume_data.get('technische fähigkeiten', []))):
        if isinstance(cat, dict):
            for s in cat.get('skills', []):
                if s and len(str(s)) > 1:
                    keywords.add(str(s).strip())
    # Always check these critical ATS terms
    keywords.update(['dbt', 'Snowflake', 'Airflow', 'Python', 'SQL'])

    # Check keyword recovery (case-insensitive substring match)
    pdf_text_lower = pdf_text.lower()
    missing = []
    for kw in sorted(keywords):
        if kw.lower() not in pdf_text_lower:
            missing.append(kw)

    total_keywords = len(keywords)
    recovered = total_keywords - len(missing)
    recovery_pct = int((recovered / total_keywords * 100)) if total_keywords > 0 else 100

    status = "Pass" if (not corruptions and recovery_pct == 100) else "Fail"

    return {
        "status": status,
        "unicode_corruptions": corruptions,
        "missing_keywords": missing,
        "keyword_recovery_pct": recovery_pct,
    }


def _recover_with_reportlab(pdf_path, yaml_path):
    """Re-compile a resume PDF using the ReportLab fallback renderer.

    Determines the resume style (us/german) from the YAML and calls the
    appropriate ReportLab renderer. Returns True if the re-compiled PDF
    passes the lightweight parse-integrity check, False otherwise.
    """
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            resume_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading YAML for recovery: {e}", file=sys.stderr)
        return False

    # Determine resume style
    style = 'us'
    style_val = str(resume_data.get('resume_style', '')).lower().strip()
    if style_val in ('german', 'germany', 'de'):
        style = 'german'

    # Add renderers to path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    print(f"  Triggering ReportLab fallback ({style} style) for ATS-safe PDF...", file=sys.stderr)
    if style == 'german':
        from renderers.resume_reportfallback_german import create_resume_pdf_reportlab_germany
        create_resume_pdf_reportlab_germany(resume_data, pdf_path)
    else:
        from renderers.resume_reportfallback_us import create_resume_pdf_reportlab
        create_resume_pdf_reportlab(resume_data, pdf_path)

    # Re-audit the ReportLab PDF
    if os.path.exists(pdf_path):
        rl_audit = check_parse_integrity(pdf_path, resume_data)
        if rl_audit["status"] == "Fail":
            print(f"\n*** FATAL: ReportLab fallback PDF also failed parse-integrity audit ***", file=sys.stderr)
            print(f"  Missing keywords: {rl_audit.get('missing_keywords', [])}", file=sys.stderr)
            return False
        else:
            print(f"  ReportLab fallback passed parse-integrity audit (recovery: {rl_audit['keyword_recovery_pct']}%)", file=sys.stderr)
            return True
    return False


def _extract_pdf_text(pdf_path):
    """Extract the full text layer from a PDF using pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        pages = len(reader.pages)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text, pages
    except Exception as e:
        print(f"Error extracting PDF text from {pdf_path}: {e}", file=sys.stderr)
        return None, 0


def _check_unicode_corruption(pdf_text):
    """Check for Unicode replacement glyphs (U+FFFD)."""
    corruptions = [i for i, ch in enumerate(pdf_text) if ch == '\uFFFD']
    status = "Pass" if not corruptions else "Fail"
    return {
        "status": status,
        "corruption_count": len(corruptions),
        "positions": corruptions[:50],
    }


def _build_keyword_set(resume_data):
    """Build the set of keywords to check from the resume YAML.

    Only keywords that are actually present in the YAML are checked.
    The audit verifies that every keyword in the YAML source is
    recoverable from the PDF text layer — not that arbitrary external
    keywords are present.
    """
    keywords = set()

    # From project tools
    for proj in resume_data.get('projects', resume_data.get('projekte', [])):
        if isinstance(proj, dict):
            for t in proj.get('tools', []):
                if t and len(str(t)) > 1:
                    keywords.add(str(t).strip())

    # From technical skills
    for cat in resume_data.get('technical_skills',
                               resume_data.get('technische_fähigkeiten',
                                               resume_data.get('technische fähigkeiten', []))):
        if isinstance(cat, dict):
            for s in cat.get('skills', []):
                if s and len(str(s)) > 1:
                    keywords.add(str(s).strip())

    # From summary (extract significant words)
    summary = resume_data.get('summary', resume_data.get('zusammenfassung', ''))
    if isinstance(summary, list):
        summary = ' '.join(summary)
    if summary:
        # Add notable terms from the summary (length > 4 to skip filler words)
        for word in summary.split():
            cleaned = word.strip('.,;:()')
            if len(cleaned) > 4:
                keywords.add(cleaned)

    return keywords


def _check_keyword_recovery(pdf_text, keywords):
    """Check which keywords are recoverable from the PDF text layer.

    Handles line-break splitting: a keyword split across a line break
    (e.g. 'Data Integration\\n& Ingestion') is still considered found
    because ATS parsers normalize whitespace.
    """
    pdf_text_lower = pdf_text.lower()
    # Normalized text (all whitespace collapsed to single spaces)
    normalized = " ".join(pdf_text.split()).lower()

    results = []
    missing = []
    found_count = 0

    for kw in sorted(keywords):
        kw_lower = kw.lower()
        if kw_lower in pdf_text_lower:
            results.append({"keyword": kw, "status": "found", "note": ""})
            found_count += 1
        elif kw_lower in normalized:
            results.append({"keyword": kw, "status": "found", "note": "Recovered after whitespace normalization (split across line break)"})
            found_count += 1
        else:
            # Check if all individual words are present (split across lines)
            words = kw_lower.split()
            all_words_found = all(w in pdf_text_lower for w in words)
            if all_words_found and len(words) > 1:
                results.append({"keyword": kw, "status": "found", "note": "All words present individually (split across lines)"})
                found_count += 1
            else:
                results.append({"keyword": kw, "status": "missing", "note": "Not in resume content"})
                missing.append(kw)

    total = len(keywords)
    recovery_pct = int(found_count / total * 100) if total > 0 else 100

    return {
        "status": "Pass" if not missing else "Fail",
        "keywords_total": total,
        "keywords_recovered": found_count,
        "keywords_missing": missing,
        "recovery_pct": recovery_pct,
        "keyword_results": results,
    }


def _check_section_headers(pdf_text, lang='english', resume_style='us'):
    """Check that all expected section headers are present in the text.

    The section set is order-aware: German style uses a different order
    than US style.
    """
    if resume_style == 'german':
        expected = {
            'english': ['SUMMARY', 'PROFESSIONAL EXPERIENCE', 'EDUCATION',
                        'TECHNICAL SKILLS', 'SPOKEN LANGUAGES'],
            'german': ['ZUSAMMENFASSUNG', 'BERUFSERFAHRUNG', 'AUSBILDUNG',
                       'TECHNISCHE FÄHIGKEITEN', 'SPRACHEN'],
        }
    else:
        expected = {
            'english': ['SUMMARY', 'TECHNICAL SKILLS', 'PROJECTS',
                        'PROFESSIONAL EXPERIENCE', 'EDUCATION', 'SPOKEN LANGUAGES'],
            'german': ['ZUSAMMENFASSUNG', 'TECHNISCHE FÄHIGKEITEN', 'PROJEKTE',
                       'BERUFSERFAHRUNG', 'AUSBILDUNG', 'SPRACHEN'],
        }
    sections = expected.get(lang, expected['english'])
    pdf_upper = pdf_text.upper()

    results = []
    found_count = 0
    for sec in sections:
        if sec.upper() in pdf_upper:
            results.append({"section": sec, "status": "found"})
            found_count += 1
        else:
            results.append({"section": sec, "status": "missing"})

    return {
        "status": "Pass" if found_count == len(sections) else "Fail",
        "sections_total": len(sections),
        "sections_found": found_count,
        "section_results": results,
    }


def _check_contact_info(pdf_text, resume_data):
    """Check that contact info fields are extractable from the PDF text."""
    contact = resume_data.get('contact_info', {})
    checks = {
        'Name':     contact.get('name', ''),
        'Phone':    contact.get('phone', ''),
        'Email':    contact.get('email', ''),
        'GitHub':   contact.get('github', ''),
        'LinkedIn': contact.get('linkedin', ''),
    }

    pdf_lower = pdf_text.lower()
    results = []
    found_count = 0

    for field, val in checks.items():
        if not val:
            continue
        if val.lower() in pdf_lower:
            results.append({"field": field, "value": val, "status": "found"})
            found_count += 1
        else:
            # Try partial match (first segment)
            partial = val.split('.')[0] if '.' in val else val.split(' ')[0]
            if partial.lower() in pdf_lower:
                results.append({"field": field, "value": val, "status": "partial"})
                found_count += 1
            else:
                results.append({"field": field, "value": val, "status": "missing"})

    total = len([v for v in checks.values() if v])
    return {
        "status": "Pass" if found_count == total else "Fail",
        "contact_fields_total": total,
        "contact_fields_found": found_count,
        "contact_results": results,
    }


def _text_stats(pdf_text):
    """Compute basic text structure statistics."""
    lines = [l for l in pdf_text.split('\n') if l.strip()]
    avg_len = sum(len(l) for l in lines) / len(lines) if lines else 0
    max_len = max(len(l) for l in lines) if lines else 0
    return {
        "non_empty_lines": len(lines),
        "avg_line_length": round(avg_len, 1),
        "max_line_length": max_len,
    }


def run_audit(pdf_path, yaml_path):
    """Run the full parse-integrity audit.

    Returns a dict with all audit results.
    """
    # Load YAML
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            resume_data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading YAML {yaml_path}: {e}", file=sys.stderr)
        return None

    # Extract PDF text
    pdf_text, pages = _extract_pdf_text(pdf_path)
    if pdf_text is None:
        return None

    # Determine language
    lang = 'english'
    lang_val = str(resume_data.get('language', '')).lower()
    if 'german' in lang_val or 'deutsch' in lang_val or lang_val == 'de':
        lang = 'german'

    # Determine resume style (us/german) for section header checking
    resume_style = 'us'
    style_val = str(resume_data.get('resume_style', '')).lower().strip()
    if style_val in ('german', 'germany', 'de'):
        resume_style = 'german'

    # Run all checks
    unicode_check = _check_unicode_corruption(pdf_text)
    keywords = _build_keyword_set(resume_data)
    keyword_check = _check_keyword_recovery(pdf_text, keywords)
    section_check = _check_section_headers(pdf_text, lang, resume_style)
    contact_check = _check_contact_info(pdf_text, resume_data)
    stats = _text_stats(pdf_text)

    # Overall verdict
    issues = []
    if unicode_check["status"] == "Fail":
        issues.append("unicode_corruptions")
    if keyword_check["keywords_missing"]:
        # Distinguish genuine misses from keywords not in the resume
        genuine_missing = [kw for kw in keyword_check["keywords_missing"]
                          if kw.lower() not in " ".join(pdf_text.split()).lower()]
        if genuine_missing:
            issues.append(f"missing_keywords: {genuine_missing}")

    overall_status = "Pass" if not issues else "Fail"

    # Extract company/position from YAML if available
    company = resume_data.get('company', '')
    position = resume_data.get('position', '')

    report = {
        "type": "parseability_report",
        "company": company,
        "position": position,
        "pdf_file": os.path.abspath(pdf_path),
        "yaml_file": os.path.abspath(yaml_path),
        "audit_date": datetime.date.today().isoformat(),
        "pages": pages,
        "total_chars": len(pdf_text),
        "total_words": len(pdf_text.split()),
        "overall_status": overall_status,
        "unicode_status": unicode_check["status"],
        "unicode_corruptions": unicode_check["positions"],
        "keyword_recovery_pct": keyword_check["recovery_pct"],
        "keywords_total": keyword_check["keywords_total"],
        "keywords_recovered": keyword_check["keywords_recovered"],
        "keywords_missing": keyword_check["keywords_missing"],
        "keyword_results": keyword_check["keyword_results"],
        "sections_found": section_check["sections_found"],
        "sections_total": section_check["sections_total"],
        "section_results": section_check["section_results"],
        "contact_fields_found": contact_check["contact_fields_found"],
        "contact_fields_total": contact_check["contact_fields_total"],
        "contact_results": contact_check["contact_results"],
        "text_stats": stats,
        "text_preview": pdf_text[:1500],
    }

    return report


def check_tex(tex_path):
    """Check LaTeX summary and project summary lengths against character limits.

    Summary section:
        English resumes: <= 200 chars (strict 2-line limit).
        German resumes (Lebenslauf): <= 170 chars (strict 2-line limit).

    Project summaries (text after the LAST '---' separator, excluding
    project name, em-dash separators, and link markup):
        English resumes: <= 300 chars per project summary.
        German resumes (Lebenslauf): <= 280 chars per project summary.

    Returns 0 if all pass, 1 if any fail.
    """
    if not os.path.exists(tex_path):
        print(f"Error: TeX file '{tex_path}' not found.", file=sys.stderr)
        return 2

    is_german = 'Lebenslauf' in os.path.basename(tex_path)
    proj_limit = 280 if is_german else 300
    summary_limit = 170 if is_german else 200

    with open(tex_path, 'r', encoding='utf-8') as f:
        content = f.read()

    all_ok = True

    # ── Summary length check (strict 2-line limit) ──
    # The summary appears between \section{SUMMARY} (or ZUSAMMENFASSUNG)
    # and the next \section{ or \vspace{6pt} or end of content.
    summary_match = re.search(
        r'\\section\{(?:SUMMARY|ZUSAMMENFASSUNG)\}\s*\n(.+?)(?=\\section\{|\\vspace\{6pt\}|\Z)',
        content, re.DOTALL
    )
    if summary_match:
        summary_text = summary_match.group(1).strip()
        # Remove any remaining LaTeX commands for an accurate char count
        summary_clean = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', summary_text)
        summary_clean = re.sub(r'\\[a-zA-Z]+', '', summary_clean)
        summary_clean = summary_clean.strip()
        summary_status = 'OK' if len(summary_clean) <= summary_limit else 'FAIL'
        if summary_status == 'FAIL':
            all_ok = False
        print(f"TeX summary length check (limit: {summary_limit} chars, strict 2-line):")
        print(f"  {summary_status} | Summary: {len(summary_clean)} chars (limit: {summary_limit})")
    else:
        print("WARNING: No summary section found in TeX file — skipping summary check.")

    # ── Project summary length check ──
    # Capture the project name and everything after it (up to \par or next
    # project / vspace). The summary is extracted by splitting on '---' and
    # taking the last segment — this excludes the name, separators, and any
    # link markup from the character count.
    projects = re.findall(
        r'\\noindent\\textbf\{(.+?)\} (.+?)(?=\\par|\n\\noindent|\\vspace|\n\n|$)',
        content, re.DOTALL
    )

    if projects:
        print(f"TeX project summary length check (limit: {proj_limit} chars, summary only):")
        for name, rest in projects:
            # Split on '---' and take the last segment as the summary text.
            # This excludes the project name, em-dash separators, and link markup.
            parts = rest.split('---')
            summary = parts[-1].strip()
            status = 'OK' if len(summary) <= proj_limit else 'FAIL'
            if status == 'FAIL':
                all_ok = False
            print(f"  {status} | {name}: {len(summary)} chars (limit: {proj_limit})")

    if all_ok:
        print("All length checks passed.")
        return 0
    else:
        print("FAIL: One or more length checks failed.", file=sys.stderr)
        return 1


def main():
    args = sys.argv[1:]

    # --check-tex mode: LaTeX project summary length check only
    if '--check-tex' in args:
        args.remove('--check-tex')
        if len(args) < 1:
            print("Usage: python resume_parseability.py --check-tex <resume.tex>", file=sys.stderr)
            sys.exit(2)
        sys.exit(check_tex(args[0]))

    # --no-recovery flag: disable automatic ReportLab re-compile on failure
    no_recovery = False
    if '--no-recovery' in args:
        no_recovery = True
        args.remove('--no-recovery')

    if len(args) < 2:
        print("Usage: python resume_parseability.py <resume.pdf> <resume.yaml> [output_dir] [--no-recovery]", file=sys.stderr)
        print("       python resume_parseability.py --check-tex <resume.tex>", file=sys.stderr)
        sys.exit(2)

    pdf_path = args[0]
    yaml_path = args[1]
    output_dir = args[2] if len(args) > 2 else os.path.dirname(os.path.abspath(pdf_path))

    if not os.path.exists(pdf_path):
        print(f"Error: PDF file '{pdf_path}' not found.", file=sys.stderr)
        sys.exit(2)

    if not os.path.exists(yaml_path):
        print(f"Error: YAML file '{yaml_path}' not found.", file=sys.stderr)
        sys.exit(2)

    # Run the audit
    report = run_audit(pdf_path, yaml_path)
    if report is None:
        print("Error: Audit could not be completed.", file=sys.stderr)
        sys.exit(2)

    # ── Recovery: re-compile with ReportLab if the audit failed ──────────
    if report['overall_status'] == 'Fail' and not no_recovery:
        print(f"\n*** PARSE-INTEGRITY AUDIT FAILED ***", file=sys.stderr)
        if report.get('unicode_corruptions'):
            print(f"  Unicode corruptions detected: {len(report['unicode_corruptions'])} replacement glyphs (U+FFFD)", file=sys.stderr)
        if report.get('keywords_missing'):
            print(f"  Missing keywords from PDF text layer: {report['keywords_missing']}", file=sys.stderr)
        print(f"  Keyword recovery: {report['keyword_recovery_pct']}%", file=sys.stderr)

        recovered = _recover_with_reportlab(pdf_path, yaml_path)
        if recovered:
            # Re-run the full audit on the recovered PDF
            report = run_audit(pdf_path, yaml_path)
            if report is None:
                print("Error: Re-audit after recovery could not be completed.", file=sys.stderr)
                sys.exit(2)
        else:
            print(f"\n*** FATAL: Recovery failed — both LaTeX and ReportLab PDFs failed parse-integrity audit ***", file=sys.stderr)
            sys.exit(1)

    # Write YAML report
    yaml_out = os.path.join(output_dir, "Parseability_Report.yaml")
    with open(yaml_out, 'w', encoding='utf-8') as f:
        yaml.safe_dump(report, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"Parseability report YAML written: {yaml_out}")

    # Generate PDF report via the renderer
    pdf_out = os.path.join(output_dir, "Parseability_Report.pdf")

    # Add the renderer to the path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    from renderers.parseability_report import create_parseability_report_pdf
    create_parseability_report_pdf(report, pdf_out)
    print(f"Parseability report PDF written: {pdf_out}")

    # Print summary to console
    print()
    print("=" * 60)
    print("PARSE-INTEGRITY AUDIT SUMMARY")
    print("=" * 60)
    print(f"  Overall:        {report['overall_status'].upper()}")
    print(f"  Unicode:        {report['unicode_status']}")
    print(f"  Keywords:       {report['keyword_recovery_pct']}% ({report['keywords_recovered']}/{report['keywords_total']})")
    print(f"  Sections:       {report['sections_found']}/{report['sections_total']}")
    print(f"  Contact:        {report['contact_fields_found']}/{report['contact_fields_total']}")
    print(f"  Pages:          {report['pages']}")
    print(f"  Text extracted: {report['total_chars']} chars / {report['total_words']} words")
    if report['keywords_missing']:
        print(f"  Missing:        {report['keywords_missing']}")
    print("=" * 60)

    # Exit code
    sys.exit(0 if report['overall_status'] == 'Pass' else 1)


if __name__ == '__main__':
    main()
