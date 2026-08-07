"""
Resume renderer — dispatcher.

Routes to the correct renderer based on two YAML keys:

  render_mode: latex | reportfallback   (default: latex)
  resume_style: us | german             (default: us)

Routing matrix:
  render_mode=latex + resume_style=us       → resume_latex_us.py
  render_mode=latex + resume_style=german   → resume_latex_german.py
  render_mode=reportfallback + resume_style=us       → resume_reportfallback_us.py
  render_mode=reportfallback + resume_style=german   → resume_reportfallback_german.py

Backward compatible: when resume_style is missing, 'us' is assumed so
existing YAMLs continue to route to the original renderers.
"""
from .resume_common import HEADERS, get_resume_language
from .resume_latex_us import create_resume_pdf_latex
from .resume_reportfallback_us import create_resume_pdf_reportlab
from .resume_latex_german import create_resume_pdf_latex_germany
from .resume_reportfallback_german import create_resume_pdf_reportlab_germany

# Backward-compatible alias used by the LaTeX renderer's audit fallback path.
create_resume_pdf_reportlab = create_resume_pdf_reportlab


def _resolve_render_mode(data) -> str:
    mode = str(data.get('render_mode', '')).lower().strip()
    if mode in ('latex', 'reportfallback', 'report', 'reportlab'):
        if mode in ('report', 'reportlab'):
            return 'reportfallback'
        return mode
    return 'latex'


def _resolve_resume_style(data) -> str:
    style = str(data.get('resume_style', '')).lower().strip()
    if style in ('us', 'german', 'germany', 'de'):
        if style in ('german', 'germany', 'de'):
            return 'german'
        return 'us'
    return 'us'


def create_resume_pdf(data, output_path):
    mode = _resolve_render_mode(data)
    style = _resolve_resume_style(data)
    print(f"Render mode: {mode} | Resume style: {style}")

    if mode == 'reportfallback':
        if style == 'german':
            create_resume_pdf_reportlab_germany(data, output_path)
        else:
            create_resume_pdf_reportlab(data, output_path)
    else:
        if style == 'german':
            create_resume_pdf_latex_germany(data, output_path)
        else:
            create_resume_pdf_latex(data, output_path)
