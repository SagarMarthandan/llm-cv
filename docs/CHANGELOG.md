# Changelog

## v1.1.0 — 2026-08-18

### Added

- **Photo stamping (LaTeX mode):** Candidate headshot (`okf/SAGAR_MARTHANDAN_foto.jpg`) is automatically stamped onto the top-right corner of page 1 as a post-processing step after PDF compilation. Photo aligns with the name text at the top and sits just above the first section separator line (1.40in, 0.25in top margin). Stamping uses ReportLab overlay + pypdf merge — no renderer header modifications needed.
  - `CANDIDATE_PHOTO` config constant (env-overridable via `LLM_CV_CANDIDATE_PHOTO`)
  - `get_photo_path()` helper resolves from `contact_info.photo` YAML key → config default → None
  - `stamp_photo_on_pdf()` creates a transparent ReportLab overlay and merges it onto the PDF via pypdf
  - Disable per-application: `contact_info.photo: null` in `Resume.yaml`
  - ReportFallback mode: no stamping (add photo manually via PDF editor if needed)

### Fixed

- **LaTeX education line wrapping:** Long degree+university combinations (e.g. "M.Sc. Quantitative Wirtschaftswissenschaften" + "Christian-Albrechts-Universität zu Kiel, Deutschland") now stay on one line. All education entries use a uniform font size determined by the longest entry, wrapped in `\mbox{}` to prevent breaking. Short entries remain at standard size; long entries shrink to `\small`/`\footnotesize` with all entries matching.

## v1.0.0 — 2026-08-08

Migrated from algorithmic search (OKF phrase matching + Zvec semantic embeddings) to LLM-based project ranking. The agent now reads a condensed `project_catalog.yaml` (16 projects, 8-10 bullets each) and ranks the top 6 for the JD using LLM judgment. Removed 7 Python scripts, 16 portfolio `.md` files, vector database, embedding server, synonyms/noise/phrase pattern data, self-learning loop, and `zvec`/`sentence-transformers` dependencies. Kept all renderers, base resumes, PDF compilation, parse-integrity audit, and Obsidian sync unchanged. Dependencies reduced to `pyyaml`, `reportlab`, `pypdf`.
