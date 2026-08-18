# Changelog

## v1.2.0 — 2026-08-18

### Added

- **Unified technical skills across all 6 base resumes:** Every base resume (5 English archetypes + 1 German) now carries the same 72-skill set across 7 categories (Programming & Query Languages, Data Engineering & Transformation, Cloud/Warehousing & Platforms, BI & Visualization, AI & ML, Data Quality/Governance & CI/CD, Streaming & Distributed Systems). Each archetype reorders the categories to lead with its strongest domain. Eliminates archetype-siloed blind spots where e.g. the Data Engineer base lacked Power BI/DAX/scikit-learn that the candidate actually knows — no LLM model sees candidate skills as "gaps" regardless of which archetype is matched.
- **4-question First Action:** Pipeline startup prompt expanded from 2 to 4 questions in a single `ask` call: render mode, resume style, application source (`Cold Apply`/`Referral`/`LinkedIn Connection`/`Direct`), and output language (`English`/`German`). Application source and language are read downstream without re-prompting. `weak_tie_contact` is collected during First Action when source is `Referral` or `LinkedIn Connection`.
- **Keyword stuffing decision (Step 2):** New First Action at Step 2 start presents the `skill_gaps` list from Step 1 and asks the user to choose: `Add all` (add every gap skill), `No stuffing` (standard anti-hallucination guardrail), or `Selective` (user specifies which skills). Stored as `keyword_stuffing` (bool) and `user_directed_skills` (list) in `Resume.yaml` for audit trail.
- **Anti-hallucination carve-out (§3):** SKILL.md §3 now explicitly waives the skill-addition restriction when the user directs specific skill additions via the Step 2 keyword stuffing prompt. The model executes a user directive, not fabrication. The guardrail remains fully enforced for projects, metrics, employment history, repo URLs, and company facts.
- **Language override:** User's First Action language selection overrides JD auto-detection. Useful for international roles at German companies where the JD is in German but English output is preferred.

### Changed

- **Step 1 (`01_ats_and_jd_archival.md`):** `application_source` changed from a Step 1 prompt to reading the pre-selected value from First Action. Base resume loading now uses the user's language selection instead of JD auto-detection. `target_language_confirmation` updated to reference First Action choice.
- **Step 2 (`02_resume_and_visual_audit.md`):** Skill gap closure rewritten as 3 branches (Add all / Selective / No stuffing) keyed to the `keyword_stuffing` decision. Space-fill directive updated with the carve-out for `keyword_stuffing: true`. `Resume.yaml` schema adds `keyword_stuffing` and `user_directed_skills` top-level keys. Match Language section references user's First Action choice.
- **Completion checklist:** Added checks for `application_source`, `keyword_stuffing`, and `user_directed_skills` fields.

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
