"""
Cover letter renderer — dispatcher.

Routes to the LaTeX renderer or the ReportFallback (ReportLab + Calibri)
renderer based on the `render_mode` key in the YAML data.

  render_mode: latex          → renderers/cover_letter_latex.py
  render_mode: reportfallback → renderers/cover_letter_reportfallback.py
  (missing / unknown)         → latex (primary, with automatic fallback)
"""
from .cover_letter_latex import create_cover_letter_pdf_latex
from .cover_letter_reportfallback import create_cover_letter_pdf_reportlab

# Backward-compatible alias used by the LaTeX renderer's fallback path.
create_cover_letter_pdf_reportlab = create_cover_letter_pdf_reportlab


def _resolve_render_mode(data) -> str:
    mode = str(data.get('render_mode', '')).lower().strip()
    if mode in ('latex', 'reportfallback', 'report', 'reportlab'):
        if mode in ('report', 'reportlab'):
            return 'reportfallback'
        return mode
    return 'latex'


def create_cover_letter_pdf(data, output_path):
    mode = _resolve_render_mode(data)
    if mode == 'reportfallback':
        print(f"Render mode: reportfallback (ReportLab + LM Roman 10)")
        create_cover_letter_pdf_reportlab(data, output_path)
    else:
        print(f"Render mode: latex")
        create_cover_letter_pdf_latex(data, output_path)
