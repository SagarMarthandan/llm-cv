# Changelog

## v1.0.0 — 2026-08-08

Migrated from algorithmic search (OKF phrase matching + Zvec semantic embeddings) to LLM-based project ranking. The agent now reads a condensed `project_catalog.yaml` (16 projects, 8-10 bullets each) and ranks the top 6 for the JD using LLM judgment. Removed 7 Python scripts, 16 portfolio `.md` files, vector database, embedding server, synonyms/noise/phrase pattern data, self-learning loop, and `zvec`/`sentence-transformers` dependencies. Kept all renderers, base resumes, PDF compilation, parse-integrity audit, and Obsidian sync unchanged. Dependencies reduced to `pyyaml`, `reportlab`, `pypdf`.
