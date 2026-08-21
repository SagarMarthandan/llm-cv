# Changelog

## v1.4.0 — 2026-08-21

### Changed

- **Project summaries tightened to 3 lines:** Resume project entries now use exactly 3 bullets (was 3-5) targeting 180-240 chars English / 160-220 chars German (was 250-300 / 230-280). Hard 3-line render limit enforced. Each bullet carries one outcome + its key metric. Eliminates verbose multi-paragraph project descriptions that read as prose padding.
- **Anti-stuffing tech skills principle:** New "Technical skills selection (ANTI-STUFFING)" directive in Step 2 §1. Skills block now includes only JD-relevant skills the candidate genuinely knows, prioritized as: (1) JD-required skills, (2) core tools from selected projects, (3) adjacent strengths. Irrelevant technologies omitted even if known. Prevents the exhaustive inventory pattern that signals ATS keyword stuffing.
- **Project tools field reduced:** Per-project `tools` list in `Resume.yaml` reduced from 5-7 to 3-5 most JD-relevant tools. Tools-Line Deduplication audit (§3) updated to match. Irrelevant tools from catalog entries no longer dilute the signal.
- **Space-fill directive updated:** Character budgets in §2.5 now reference the tighter 180-240/160-220 ranges. Add-one-more-project and LaTeX polish sections updated to match.

### Files Modified

- `02_resume_and_visual_audit.md` — §1 (anti-stuffing + project tools), §2 (layout table, project instructions), §2.5 (space-fill budgets), §3 (tools-line count), §4 (LaTeX polish length), Optional (add project), §B (YAML schema comments)
- `llm-cv-token-optimization-plan.md` — planning doc table updated for consistency


## v1.3.0 — 2026-08-19

### Added

- **Session splitting (`run_pipeline.sh`):** Wrapper script that runs each pipeline step as a separate OMP session with clean context, chaining via disk files. Reduces token consumption by 84% (~400K tokens/run vs ~2.5M single-session). Collects First Action answers and keyword stuffing decision outside the agent, passes them via prompt. Each session starts with `omp -p --auto-approve` and a step-specific prompt.
- **Prompt templates (`prompts/`):** Reference documentation for the 3 session prompts used by `run_pipeline.sh` (`step1.md`, `step2.md`, `step3.md`). Each documents the prompt structure, what the session reads/writes, and token budget.
- **Completion checklist extraction (`99_completion_checklist.md`):** Moved the 30+ item completion checklist out of `SKILL.md` into a separate file read only at pipeline end. Saves ~2,500 base tokens across 25+ API calls where it's not needed.
- **Lazy loading directives:** Each step doc ends with `**Next:** Proceed to Step N — read N_*.md`, chaining steps without loading all docs at once. `SKILL.md` instructs: "Read only the step doc for the step you're executing."
- **First Action persistence in `ATS_Report.yaml`:** `render_mode`, `resume_style`, and `language` are now written as top-level keys in `ATS_Report.yaml` by Step 1, so Step 2 and Step 3 sessions can read them from disk. Enables manual re-runs of individual steps without the wrapper script.

### Changed

- **SKILL.md slimmed 49%** (32,121 → 16,381 bytes): Condensed First Action questions to 4-row table, anti-hallucination principles to tight bullets, pipeline overview to 4-line summary, read-only guardrail to compact list, execution step descriptions condensed, post-pipeline/error handling/self-refresh sections condensed.
- **Step docs slimmed 50-62%:**
  - `00_jd_fetch.md`: 9,466 → 4,159 bytes (56%) — condensed validation heuristic, strategy routing, removed "What this step does NOT do" section.
  - `01_ats_and_jd_archival.md`: 23,591 → 10,113 bytes (57%) — condensed ATS scoring matrix, improvement blueprint, placement weighting, vendor inference. YAML schemas preserved verbatim.
  - `02_resume_and_visual_audit.md`: 42,792 → 16,342 bytes (62%) — removed LaTeX example code blocks, condensed space-fill directive to numbered list, converted layout constraints to table, consolidated compilation commands into single code blocks.
  - `03_cover_letter.md`: 9,936 → 4,984 bytes (50%) — condensed narrative rules to bullets, consolidated compilation + sync commands.
- **De-duplicated guardrails:** Repeated guardrail blocks (READ-ONLY, AGENT EXECUTION, YAML SAFETY, ANTI-HALLUCINATION, Stop-Slop) in all 4 step docs replaced with 1-line `> **Rules:** Follow SKILL.md §"..."` references. Each step doc keeps only its writable-files list.
- **Step 2 inputs:** Now explicitly reads `render_mode`, `resume_style`, `language`, `skill_gaps`, `improvement_blueprint`, `role_archetype`, `closest_candidate_location` from `ATS_Report.yaml` (was implicit before).
- **Step 3 inputs:** Now explicitly reads `render_mode`, `language`, `closest_candidate_location`, `application_source`, `weak_tie_contact`, `role_archetype` from `ATS_Report.yaml`.

### Token Optimization Summary

| Mode | Per run | 4 runs | Quota (60M) | Resumes/month |
|:---|:---|:---|:---|:---|
| Original (v1.2.0) | ~2.5M | ~10M | 16.7% | ~24 |
| Single-session (doc slimming) | ~2.0M | ~8M | 13.3% | ~30 |
| Session-split (all optimizations) | ~400K | ~1.6M | 2.7% | ~149 |

### Fixed

- **Missing YAML Safety Rules section:** Added `## YAML Safety Rules (Non-Negotiable)` section to `SKILL.md` — step docs referenced it but it didn't exist.
- **Missing Read-Only Guardrail header:** Added `## Read-Only Guardrail (Non-Negotiable)` section header to `SKILL.md` to match step doc references.
- **Renamed Agent Execution section:** `## Agent Execution & Anti-Spinning Rules (Mandatory)` → `## Agent Execution Rules (Mandatory)` to match step doc references.

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
