# Changelog

## v4.0.0 — 2026-09-04

### Added

- **Direct OpenRouter API architecture (`api_pipeline.py`):** Replaced 29 OMP session calls with 3 direct OpenRouter API calls. Python reads input files, builds one prompt per step, calls the API, parses YAML from the response, writes output files. Model: qwen/qwen3.8-flash with reasoning disabled. Cost: ~$0.01/run (was $0.04). Time: 1-2 min/run (was 10 min). ~1236 lines.
- **Static-First cache architecture:** 10.5K-token `SYSTEM_PROMPT` loaded once at module import via `_load_system_prompt()`. Contains full step docs (02, 03), score_boost.md, guardrails, resume constraints, German/US schema templates, and John Deere golden resume + cover letter as few-shot examples. Sent as system message with `cache_control: {"type": "ephemeral"}` in content array format. Cache hits: 0% (cold) → 60% → 80% across a run.
- **2-stage pipeline split:** `run_pipeline.sh` split into `--stage 1` (Step 1 + compile + extract, prints APP_DIR/SKILL_GAPS/ATS_SCORE) and `--stage 2` (Steps 2+3 parallel + compilation + fix loop + Obsidian sync). Keyword stuffing asked AFTER Step 1 when skill gaps are known.
- **`lib/compile.sh` extraction:** All compilation functions extracted to `lib/compile.sh` (199 lines): `compile_step1_pdfs()`, `get_resume_filenames()`, `get_cover_letter_filename()`, `compile_resume()`, `compile_cover_letter()`, `generate_layout_audit()`. Sourced by `run_pipeline.sh`. Main file down from 797 to 615 lines.
- **Firecrawl JD scraping:** Agent scrapes JD via `firecrawl_scrape` MCP tool before launching the pipeline, saves to `/tmp/llm-cv-jd.txt`, passes `--file`. Fixes Jina Reader redirect-following issue on Indeed/Personio. Pipeline spends zero tokens on JD fetching.
- **Page fill directive:** Resumes must fill the ENTIRE text area between margins. Fill via 5-6 technical_skills categories (5-7 skills each), 5th project, 5th-6th IBM bullet. Never extend bullet prose to fill space.
- **Mandatory quantitative metric per bullet:** Every project bullet must contain at least one quantitative metric (%, count, latency, size, duration). A bullet without a number is a hard FAIL.
- **ITIL V3 Foundation and Project Management:** Added as IBM work experience bullets to all 5 English + 1 German base resume files. Added to `okf/skill_mappings.yaml` for Obsidian sync normalization. IBM now has 6 bullets available (was 4).
- **New CLI flags:** `--stage 1|2`, `--app-dir`, `--user-skills`, `--force` (skip duplicate check prompt for non-interactive stage 2).

### Changed

- **`run_pipeline.sh` rewritten:** 797 → 615 lines. Two-stage flow with `--stage 1|2`. Sources `lib/compile.sh`. No more OMP session launching, `hub` monitoring, or `select` menu feeding.
- **SKILL.md updated:** 4 initial questions (was 5, keyword stuffing moved post-Step-1). 2-stage flow documented. Firecrawl JD scraping documented. Flag reference updated. Page fill directive added to Step 2 Hard Constraints.
- **Schema templates (German + US):** 5-6 skills categories (was 4), 5 project slots (was 4, 5th conditional on page fill), 4-6 IBM bullets (was exactly 4).
- **Golden example comment:** Updated to note golden example has 4 projects/4 skills categories, but model should use 5-6 skills and add 5th project if page has empty space.
- **Project count constraint:** Changed from "3-4 projects maximum. Never 5." to "3-5 projects. Default to 4. Add a 5th ONLY when needed for page fill."
- **Token consumption:** ~50K tokens/run (was ~2M). ~$0.01/run (was $0.04). 3 API calls (was 29). 1-2 min/run (was 10 min).

### Files Modified

- `api_pipeline.py` — new file (~1236 lines). Direct OpenRouter API calls, static system prompt, 3 step builders, fix loop, URL fetch.
- `run_pipeline.sh` — rewritten to 2-stage flow (615 lines, was 797).
- `lib/compile.sh` — new file (199 lines). Compilation functions extracted.
- `SKILL.md` — 4 initial questions, 2-stage flow, Firecrawl JD scraping, page fill directive, flag reference.
- `okf/base_files/english/*.md` — 5 files: added ITIL V3 Foundation + team lead bullets to IBM section.
- `okf/base_files/german/resume_de.md` — added team lead bullet + Projektmanagement to WEITERE KOMPETENZEN.
- `okf/skill_mappings.yaml` — added ITIL V3 Foundation and Project Management normalization rules.
- `README.md` — complete overhaul for v4.0 architecture.
- `docs/ARCHITECTURE.md` — complete overhaul for v4.0 architecture.
- `docs/CHANGELOG.md` — v4.0.0 entry added.

## v2.0.0 — 2026-09-03

### Added

- **Bash-orchestrated wrapper (`run_pipeline.sh` v3):** Complete rewrite from session-splitting to bash-orchestrated architecture. The wrapper launches 3 isolated OMP sessions via bash, handles all compilation (pdflatex, stamp_photo, parseability, watermark), fix loops, and Obsidian sync between sessions. No subagent spawning — flash-model safe. ~920 lines.
- **Non-interactive CLI flags:** `--render`, `--style`, `--source`, `--language`, `--weak-tie`, `--stuffing`, `--score-boost` flags let the wrapper run without `select` prompts or TTY input. The agent asks 4 questions via `ask`, passes all answers as flags, and does a single `bash` call. Eliminates the 1.4M-token parent-session overhead from `hub`-based menu feeding.
- **Condensed catalog (`okf/project_catalog_condensed.yaml`):** Same 15 projects as the full catalog but without the `bullets` field (21KB vs 49KB). Step 1 reads this for project ranking, saving ~28KB of context per Step 1 session.
- **`extract_projects.py`:** Three-mode utility: (1) `--condensed` generates the condensed catalog, (2) `--from-project-info` extracts full bullet data for only the 6 ranked projects from `project_info.md` into `selected_projects.yaml` (~7KB), (3) `--titles` extracts by explicit title list. Step 2 reads the 7KB `selected_projects.yaml` instead of the 49KB full catalog.
- **SKILL.md Trigger Action section:** New mandatory section at the top of SKILL.md. Instructs the agent to launch `run_pipeline.sh` via bash when the user says "llm-cv" with a JD, instead of handling pipeline steps itself. Explicitly forbids reading step docs, asking First Action questions, compiling PDFs, or monitoring via `hub`.
- **Score-Boost `--score-boost auto` flag:** `auto` applies score-boosting automatically when ATS score < 85 (default). `yes`/`no` force the decision. Eliminates the interactive `select` prompt.

### Fixed

- **`run_session_bg` stdout pollution:** `log()` inside `run_session_bg` echoed to stdout, mixing with `echo $!` in `$(...)` PID capture, producing garbage PIDs. Fix: redirect `log()` to `>&2`.
- **`$(...)` subshell orphans background process:** `PID=$(run_session_bg ...)` runs the function in a subshell. The backgrounded `timeout` is a child of the subshell, not the main shell. When the subshell exits, the process is reparented to init, so `wait $PID` fails with "pid is not a child of this shell". Fix: use global `_BG_PID=$!` variable set inside the function after `&` backgrounding. Call sites updated to `run_session_bg ...; VAR=$_BG_PID`.
- **`find` breaks on paths with spaces:** `for f in $(find ...)` splits "Company — Role" into separate words. `cut -d' ' -f2` only captures the first word. Fix: use `while IFS= read -r` with process substitution `< <(find ...)` and `cut -d' ' -f2-` to capture the full path.
- **`ls` pipefail exit 2:** The final `ls -la "$APP_DIR"/*.pdf ...` pipeline caused exit 2 under `set -euo pipefail` when a glob didn't match (e.g. no `.md` files). Fix: `set +e` around the `ls | awk` pipeline with `|| true`.
- **Photo path resolution (bug):** `get_photo_path()` in `renderers/resume_common.py` checked `os.path.exists("okf/SAGAR_MARTHANDAN_foto.jpg")` from the application folder cwd, but the photo lives at `/home/sagar/Skills/llm-cv/okf/SAGAR_MARTHANDAN_foto.jpg`. Relative photo paths in YAML are now resolved against `SKILL_DIR` from `config.py`, not cwd. Fix verified: deviceNow resume re-stamped successfully (988x988 image in PDF, parseability still passes).

### Changed

- **SKILL.md restructured:** Trigger Action section added at top (agent is a launcher, not a worker). Bash-Orchestrated Architecture section marked as DEFAULT. Single-session mode demoted to "Manual Debugging Only" with explicit 30x token cost warning. First Action section marked as wrapper-handled reference. Token estimate updated to ~2M/$0.04 (was ~400K/$0.005 — the old estimate was inaccurate).
- **Step docs updated:** `01_ats_and_jd_archival.md` — "Subagent pattern" replaced with "Wrapper mode: agent reads condensed catalog directly". `02_resume_and_visual_audit.md` — compilation sections marked as bash-handled. `03_cover_letter.md` — parallel session note added.
- **Prompt templates updated:** `prompts/step1.md`, `step2.md`, `step3.md` reference wrapper's prompt structure.
- **Token consumption corrected:** Old docs claimed ~400K tokens/run. Measured on deviceNow run: 3.4M tokens (wrapper v1 with `hub`-fed menus). Projected for wrapper v2 with CLI flags: ~2M tokens. The ~400K estimate was the child sessions only, excluding parent overhead.

### Files Modified

- `run_pipeline.sh` — complete rewrite to v3 bash-orchestrated architecture (~920 lines). Added 7 CLI flags, `run_session`/`run_session_bg` helpers, `compile_resume`/`compile_cover_letter`/`compile_step1_pdfs`/`generate_layout_audit` functions, fix loop, all bug fixes.
- `extract_projects.py` — new file (122 lines). Three modes: `--condensed`, `--from-project-info`, `--titles`.
- `okf/project_catalog_condensed.yaml` — new file (21KB, 15 projects without bullets).
- `SKILL.md` — Trigger Action section, Bash-Orchestrated Architecture (DEFAULT), single-session demoted, First Action wrapper note, token estimates updated.
- `00_jd_fetch.md` — wrapper mode note.
- `01_ats_and_jd_archival.md` — subagent pattern replaced with wrapper mode.
- `02_resume_and_visual_audit.md` — compilation sections marked bash-handled.
- `03_cover_letter.md` — parallel session note.
- `prompts/step1.md`, `prompts/step2.md`, `prompts/step3.md` — wrapper prompt structure references.
- `renderers/resume_common.py` — `get_photo_path()` fix: relative paths resolved against `SKILL_DIR`. Added `SKILL_DIR` import from `config.py`.
- `README.md` — complete overhaul for v2.0 architecture.
- `docs/ARCHITECTURE.md` — complete overhaul for v2.0 architecture.
- `docs/CHANGELOG.md` — v2.0.0 entry added.


## v1.7.0 — 2026-08-30

### Added

- **AI watermark/provenance checker (`check_watermarks.py`):** Post-compilation script scanning generated PDFs and YAML for AI provenance marks across three layers: (A) invisible Unicode in YAML text, (B) C2PA/Content Credentials binary markers in PDF non-stream data, (C) PDF metadata vendor strings. Exit 0 = clean, exit 1 = marks found. Supports `--dir` and `--json`.
- **Watermark check wired into pipeline:** Runs after every resume and cover letter compilation.

### Fixed

- **Photo stamping in ReportFallback mode:** `stamp_photo.py` was invoked in the ReportFallback compilation block. Removed; added explicit "NO photo stamping" hard constraint.

### Changed

- **Space-Fill Directive strengthened:** Now requires "zero empty trailing lines" (was "<=1 line trailing whitespace").
- **`renderers/resume.py` dispatcher comment updated:** Photo stamping guard explicitly marked as intentional.


## v1.6.0 — 2026-08-26

### Added

- **Duplicate Application Check (`check_duplicate_application.py`):** Searches Obsidian vault + Applications filesystem tree for prior applications to the same company + role before resume rewrite. Fuzzy-matches with `SequenceMatcher` — normalizes company names (strips legal suffixes) and role titles (strips gender markers). Three options: proceed, abort, reuse prior resume.
- **`run_pipeline.sh` integration:** Duplicate check runs after Step 1, before Step 2.


## v1.5.0 — 2026-08-24

### Added

- **Score-Boost Mode (conditional, user-opt-in):** When initial ATS score < 85, wrapper displays score + 4 measures and asks user whether to apply. Measures: (1) student framing, (2) exact JD phrase weaving, (3) real adjacent skills, (4) itemized scoring rubric. Proven on Harman Intern run: 69 → 88 (+19 delta).
- **`prompts/score_boost.md`:** Reference file with 4 score-boost measures.


## v1.4.0 — 2026-08-21

### Changed

- **Project summaries tightened to 3 lines:** Exactly 3 bullets per project (was 3-5), 180-240 chars EN / 160-220 DE, hard 3-line render limit.
- **Anti-stuffing tech skills:** Skills block includes only JD-relevant skills, prioritized as JD-required → core project tools → adjacent strengths.
- **Project tools field reduced:** 3-5 most JD-relevant tools per project (was 5-7).
- **Section rule separation (hard):** `\titlespacing` after-sep must never go below 4pt.
- **SKILL.md Step 2 hard constraints:** Added compact constraints block directly to SKILL.md (root cause of 6 runs ignoring v1.4.0 changes — step docs not reliably read by session-split agents).
- **Pipeline Summary Output (mandatory):** Agent must print summary box after every run.


## v1.3.0 — 2026-08-19

### Added

- **Session splitting (`run_pipeline.sh` v1):** Wrapper script running each pipeline step as a separate OMP session with clean context. First version of token optimization.
- **Prompt templates (`prompts/`):** Reference docs for session prompts.
- **Completion checklist extraction (`99_completion_checklist.md`):** Moved out of SKILL.md, read only at pipeline end.
- **Lazy loading directives:** Step docs chain via "Next: Proceed to Step N" directives.
- **First Action persistence in `ATS_Report.yaml`:** `render_mode`, `resume_style`, `language` written as top-level keys for cross-session reading.

### Changed

- **SKILL.md slimmed 49%** (32KB → 16KB).
- **Step docs slimmed 50-62%** (total 118KB → 52KB).
- **De-duplicated guardrails:** Repeated blocks in step docs replaced with 1-line references to SKILL.md.


## v1.2.0 — 2026-08-18

### Added

- **Unified technical skills across all 6 base resumes:** Same 72-skill set across 7 categories, reordered per archetype.
- **4-question First Action:** Render mode, resume style, application source, language.
- **Keyword stuffing decision (Step 2):** User chooses Add all / No stuffing / Selective.
- **Anti-hallucination carve-out:** User-directed skill additions are not fabrication.
- **Language override:** User's First Action language selection overrides JD auto-detection.


## v1.1.0 — 2026-08-18

### Added

- **Photo stamping (LaTeX mode):** Candidate headshot stamped onto top-right corner of page 1. `get_photo_path()` resolves from `contact_info.photo` → config default → None. `stamp_photo_on_pdf()` creates ReportLab overlay + pypdf merge.

### Fixed

- **LaTeX education line wrapping:** Long degree+university combinations wrapped in `\mbox{}` with uniform font size.


## v1.0.0 — 2026-08-08

Migrated from algorithmic search (OKF phrase matching + Zvec semantic embeddings) to LLM-based project ranking. Removed 7 Python scripts, 16 portfolio `.md` files, vector database, embedding server, synonyms/noise/phrase pattern data, self-learning loop, and `zvec`/`sentence-transformers` dependencies. Dependencies reduced to `pyyaml`, `reportlab`, `pypdf`.
