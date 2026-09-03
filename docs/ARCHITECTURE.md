# LLM-CV Architecture

## Overview

LLM-CV is an ATS-optimized resume and cover letter generation pipeline. A bash-orchestrated wrapper (`run_pipeline.sh`) launches 3 isolated OMP sessions, each with a focused prompt a flash model can handle. Bash handles all compilation, fix loops, and Obsidian sync between sessions. No subagent spawning.

### Design Philosophy

- **Agent is a launcher, not a worker:** When the user says "llm-cv" with a JD, the agent's only job is to ask 4 configuration questions via `ask`, then launch `run_pipeline.sh` with all flags via one `bash` call. The wrapper handles everything else.
- **LLM judgment over algorithmic matching:** The LLM ranker correctly distinguishes AI roles from DE roles, prioritizes Power BI projects for BI roles, and understands domain relevance — all without synonyms, allowlists, or transferable skills definitions.
- **Single source of truth:** One `project_catalog.yaml` file (15 projects) replaces 16 portfolio `.md` files, a synonyms map, a body-skill allowlist, and a transferable skills definition.
- **Condensed catalog for ranking, extracted subset for writing:** Step 1 reads a 21KB condensed catalog (no bullets) for ranking. Bash then extracts full bullet data for only the 6 ranked projects into a 7KB `selected_projects.yaml` for Step 2. This avoids loading the 49KB full catalog into any session.
- **Minimal dependencies:** Only `pyyaml`, `reportlab`, `pypdf` — no vector databases, embedding models, or ML frameworks.
- **Token-efficient:** 3 isolated sessions + bash compilation (0 tokens) + condensed catalog = ~2M tokens/run (~$0.04) vs ~8M single-session (~$0.13).

---

## Pipeline Flow

### Bash-Orchestrated Mode (DEFAULT — always use the wrapper)

```
User says "llm-cv" + JD (URL, file, or pasted text)
    │
    ├── Agent asks 4 questions via ask (render mode, style, source, language)
    │
    └── Agent launches run_pipeline.sh with all flags via ONE bash call
            │
            │  ── Session 1 (Step 1): ATS + JD archival + project ranking ──
            │     reads: SKILL.md + 01_ats_and_jd_archival.md + condensed catalog (21KB) + base resume
            │     writes: ATS_Report.yaml, Job_Description.yaml, project_info.md
            │     ~13 API calls, foreground, 600s timeout
            │
            │  ── [bash] Compile Step 1 PDFs (ATS_Report.pdf, Job_Description.pdf)
            │  ── [bash] extract_projects.py → selected_projects.yaml (7KB, full bullets for 6 ranked projects)
            │  ── [bash] Duplicate application check (check_duplicate_application.py)
            │  ── [bash] Apply keyword stuffing + score-boost decisions from CLI flags
            │
            │  ── Session 2 (Step 2): Resume writer + ATS rescoring     ┐
            │     reads: SKILL.md + 02_resume_and_visual_audit.md        │ parallel
            │            + selected_projects.yaml (7KB) + ATS_Report.yaml │
            │     writes: Resume.yaml, updates ATS_Report.yaml            │
            │     ~11 API calls, background, 900s timeout                 │
            │                                                            │
            │  ── Session 3 (Step 3): Cover letter writer               ┘
            │     reads: SKILL.md + 03_cover_letter.md + project_info.md + ATS_Report.yaml
            │     writes: Cover_Letter.yaml
            │     ~5 API calls, background, 600s timeout
            │
            │  ── [bash] wait for both sessions
            │  ── [bash] Compile resume: yaml_to_pdf --tex-only → check-tex → pdflatex x2 → stamp_photo → parseability → watermark
            │  ── [bash] Compile cover letter: yaml_to_pdf → watermark
            │  ── [bash] Fix loop: if parseability fails, launch minimal fix session (max 2 attempts)
            │  ── [bash] Recompile ATS_Report.pdf with post-rewrite scores
            │  ── [bash] Generate Layout_Audit_Report.yaml
            │  ── [bash] Obsidian sync + sort
            │
            └── Print summary block (company, position, folder, delta, resume status)
```

### Inter-step contract

`ATS_Report.yaml` is the contract between sessions:

| Field | Written by | Read by |
|:---|:---|:---|
| `render_mode` | Session 1 | Sessions 2, 3 |
| `resume_style` | Session 1 | Session 2 |
| `language` | Session 1 | Sessions 2, 3 |
| `application_source` | Session 1 | Session 3, Obsidian sync |
| `skill_gaps` | Session 1 | Bash (stuffing decision), Session 2 |
| `improvement_blueprint` | Session 1 | Session 2 |
| `role_archetype` | Session 1 | Session 2 |
| `closest_candidate_location` | Session 1 | Sessions 2, 3 |
| `post_rewrite_ats_score` | Session 2 | Bash (summary output) |

Keyword stuffing and score-boost decisions are not persisted to disk — the wrapper passes them inline via the session prompt.

### Parallelism

Bash launches Sessions 2 and 3 in parallel using `&` and `wait`:

```bash
run_session_bg "$RESUME_PROMPT" "resume" 900
RESUME_PID=$_BG_PID
run_session_bg "$CL_PROMPT" "coverletter" 600
CL_PID=$_BG_PID

wait "$RESUME_PID"
wait "$CL_PID"
```

`run_session_bg` sets a global `_BG_PID` variable instead of `$(...)` capture, because `$(...)` runs the function in a subshell and orphans the backgrounded process.

### Non-interactive CLI flags

The wrapper accepts all pipeline options as CLI flags so it runs without `select` prompts or TTY input:

| Flag | Maps to | Skips |
|:---|:---|:---|
| `--render` | `render_mode` | First Action render `select` |
| `--style` | `resume_style` | First Action style `select` |
| `--source` | `app_source` | First Action source `select` |
| `--language` | `language` | First Action language `select` |
| `--weak-tie` | `weak_tie_contact` | Referral contact `read` |
| `--stuffing` | `stuffing_choice` | Keyword stuffing `select` |
| `--score-boost` | `score_boost_mode` | Score-boost `select` |

When a flag is provided, the corresponding `select`/`read` prompt is skipped and the flag value is used directly. This allows the agent to launch the wrapper via a single non-interactive `bash` call.

---

## Token Optimization

### Architecture-level savings

| Technique | What it does | Impact |
|:---|:---|:---|
| **3 isolated sessions** | Each session starts with clean context — no cross-step accumulation | ~6M tokens saved vs single-session |
| **Bash compilation** | PDF compilation, parseability, watermark, sync all run in bash (0 tokens) | ~1M tokens saved vs agent-handled compilation |
| **Condensed catalog** | Step 1 reads 21KB catalog (no bullets) instead of 49KB | ~28KB context saved per Step 1 session |
| **Selected projects extraction** | Step 2 reads 7KB (6 projects with bullets) instead of 49KB full catalog | ~42KB context saved per Step 2 session |
| **Non-interactive CLI flags** | Parent agent does 1 `ask` + 1 `bash` call instead of 28 `hub` calls to feed `select` menus | ~1.3M tokens saved in parent session |

### Token consumption

| Mode | Per run | Cost | Notes |
|:---|:---|:---|:---|
| Single-session (old) | ~8M | $0.13 | Agent handles all steps in one conversation |
| Wrapper v1 (interactive select) | ~3.4M | $0.07 | 3 sessions + bash, but parent feeds menus via `hub` (28 API calls) |
| **Wrapper v2 (CLI flags)** | **~2M** | **$0.04** | Parent does 1 `ask` + 1 `bash` (4 API calls). 3 child sessions unchanged |

Measured on deviceNow Data & BI Analyst run (2026-09-03): 3.4M tokens across 4 sessions, 57 API calls, $0.07. Wrapper v2 with CLI flags projects to ~2M by eliminating the parent's `hub` monitoring overhead.

---

## Project Catalog

`okf/project_catalog.yaml` — single source of truth. 15 projects, each with:

| Field | Type | Description |
|:---|:---|:---|
| `title` | string | Project title |
| `description` | string | One-line project description |
| `business_problem` | string | Business problem solved |
| `key_metrics` | string | Quantified metrics (authoritative — cite verbatim, never invent) |
| `transferable_skills` | list | Skills that transfer across domains |
| `technologies` | string | Comma-separated tech list |
| `archetypes` | list | Role archetypes this project fits |
| `repo_url` | string | GitHub URL (empty string if none) |
| `bullets` | list (8-10) | Detailed project bullets with metrics |
| `keywords` | list | Search/matching keywords |

### Condensed catalog

`okf/project_catalog_condensed.yaml` — same 15 projects without the `bullets` field (21KB vs 49KB). Generated by `extract_projects.py --condensed`. Step 1 reads this for ranking.

### Selected projects extraction

After Step 1 ranks the top 6 projects, `extract_projects.py --from-project-info` reads `project_info.md` (written by Session 1), matches titles against the full catalog, and extracts full bullet data for only those 6 projects into `selected_projects.yaml` (~7KB). Step 2 reads this instead of the 49KB full catalog.

```bash
# Generate condensed catalog (run once, checked into repo)
python extract_projects.py --condensed --catalog okf/project_catalog.yaml --output okf/project_catalog_condensed.yaml

# Extract full data for ranked projects (run by wrapper after Step 1)
python extract_projects.py --from-project-info path/to/project_info.md --catalog okf/project_catalog.yaml --output selected_projects.yaml
```

---

## File Inventory

### Wrapper Script

| File | Role |
|:---|:---|
| `run_pipeline.sh` | Bash-orchestrated wrapper (~920 lines). Launches 3 OMP sessions, handles compilation, fix loops, sync. Non-interactive CLI flags for agent mode. |
| `extract_projects.py` | Condensed catalog generation + selected projects extraction (3 modes: `--condensed`, `--from-project-info`, `--titles`) |

### Pipeline Scripts (12 Python files)

| File | Role |
|:---|:---|
| `config.py` | Location lookup, candidate info, `SKILL_DIR` constant |
| `yaml_to_pdf.py` | PDF compilation entry point (routes YAML to renderers) |
| `resume_parseability.py` | ATS parse-integrity audit on compiled PDF |
| `stamp_photo.py` | Candidate photo stamping onto LaTeX-mode resume PDFs |
| `check_watermarks.py` | AI watermark/provenance check (3 layers: Unicode, C2PA, metadata) |
| `check_duplicate_application.py` | Duplicate application detection (Obsidian vault + filesystem) |
| `organize_applications.py` | Application folder organization (date tree sort) |
| `obsidian_sync_core.py` | Obsidian sync core logic |
| `obsidian_folder_sort.py` | Folder sorting logic |
| `sync_to_obsidian.py` | Obsidian sync entry point |
| `track_outcomes.py` | Application outcome tracking |
| `okf_diversity_audit.py` | Weekly diversity audit (standalone) |

### Renderers (14 files in `renderers/`)

| File | Role |
|:---|:---|
| `__init__.py` | Package init |
| `utils.py` | Shared utilities (`escape_latex`, color constants, `run_pdflatex`, font registration) |
| `resume_common.py` | Shared resume helpers (`HEADERS`, `get_resume_language`, `get_photo_path`, `stamp_photo_on_pdf`) |
| `resume.py` | Resume renderer dispatcher (reads `render_mode` + `resume_style`) |
| `resume_latex_us.py` | Resume LaTeX renderer (US style) |
| `resume_reportfallback_us.py` | Resume ReportLab renderer (US style) |
| `resume_latex_german.py` | Resume LaTeX renderer (German style, Lebenslauf section order) |
| `resume_reportfallback_german.py` | Resume ReportLab renderer (German style) |
| `cover_letter.py` | Cover letter renderer dispatcher |
| `cover_letter_latex.py` | Cover letter LaTeX renderer |
| `cover_letter_reportfallback.py` | Cover letter ReportLab renderer |
| `job_description.py` | Job description renderer (ReportLab) |
| `ats_report.py` | ATS report renderer (ReportLab) |
| `parseability_report.py` | Parseability report renderer (ReportLab) |

### Pipeline Step Docs (6 `.md` files)

| File | Role | Size |
|:---|:---|:---|
| `SKILL.md` | Master orchestration, guardrails, Trigger Action, hard constraints | ~14KB |
| `00_jd_fetch.md` | Step 0: JD scraping from URLs | ~4KB |
| `01_ats_and_jd_archival.md` | Step 1: ATS scoring, JD archival, LLM project ranking | ~10KB |
| `02_resume_and_visual_audit.md` | Step 2: Resume rewrite, layout audit, parseability | ~16KB |
| `03_cover_letter.md` | Step 3: Cover letter generation | ~5KB |
| `99_completion_checklist.md` | Post-pipeline verification (lazy-loaded) | ~3KB |

### Prompt Templates (4 files in `prompts/`)

| File | Role |
|:---|:---|
| `step1.md` | Step 1 session prompt reference |
| `step2.md` | Step 2 session prompt reference |
| `step3.md` | Step 3 session prompt reference |
| `score_boost.md` | Score-Boost measures reference (conditional, user-opt-in) |

### Data Files

| File | Role |
|:---|:---|
| `okf/project_catalog.yaml` | 15-project catalog (49KB, source of truth with bullets) |
| `okf/project_catalog_condensed.yaml` | 15 projects without bullets (21KB, Step 1 input) |
| `okf/base_files/english/` | 4 English archetype base resumes + 1 generic fallback (5 files) |
| `okf/base_files/german/` | 1 German base resume (covers all archetypes) |
| `okf/project_mappings.yaml` | Obsidian sync project name mappings |
| `okf/skill_mappings.yaml` | Obsidian sync skill mappings |
| `okf/.jd_cache/` | JD URL cache (7-day TTL, sha1-keyed) |
| `okf/.location_cache.json` | Cached location lookups |

### Tests (2 files)

| File | Role |
|:---|:---|
| `tests/test_utils.py` | Renderer utils tests |
| `tests/test_llm_search.py` | LLM ranking smoke test (catalog validation + 3 JD archetypes) |

---

## Design Decisions

### Why bash orchestration over single-session

In a single agent session, context accumulates across all 3 steps. Step 3 carries the entire history of Step 1 + Step 2 — ATS scoring YAML, project ranking, compile logs, audit results. This is pure overhead: Step 3 only needs `ATS_Report.yaml`, `project_info.md`, and `Job_Description.yaml` (all on disk).

Bash orchestration gives each step a clean context via separate OMP sessions. The YAML schemas are the contract between steps. Bash handles compilation (0 tokens) between sessions. If a step fails, the wrapper can re-launch just that step with the same disk inputs.

### Why CLI flags over interactive select menus

The first wrapper version used `select` menus for all options. When launched via `bash` (non-interactive), `select` hits EOF and the script dies. The agent then had to use `hub start` + 7 `hub send` calls to feed the menus, burning 1.4M tokens in the parent session alone.

CLI flags (`--render`, `--style`, `--source`, `--language`, `--stuffing`, `--score-boost`) let the agent ask via `ask` once, pass everything as flags, and do a single `bash` call. Parent session drops from 28 API calls (1.4M tokens) to 4 API calls (~100K tokens).

### Why condensed catalog + extraction

Step 1 needs project metadata for ranking but not the 8-10 bullets per project (those are for Step 2's resume writing). The condensed catalog (21KB vs 49KB) saves ~28KB of context in the Step 1 session. After ranking, `extract_projects.py` pulls full bullet data for only the 6 ranked projects (7KB), so Step 2 gets exactly what it needs without loading all 15 projects' bullets.

### Why LLM ranking over algorithmic search

Tested against 10 real JDs, the LLM ranker won or tied on 10/10 and was never beaten by the algorithm. It correctly distinguishes AI roles from DE roles, prioritizes Power BI projects for BI roles, and handles synonyms/transferable skills natively. The algorithmic system required synonyms.yaml, body-skill allowlists, embedding models, and a vector database. The LLM ranker requires only a catalog YAML file.

### Photo path resolution

`get_photo_path()` in `renderers/resume_common.py` resolves relative photo paths (e.g. `okf/SAGAR_MARTHANDAN_foto.jpg` in YAML) against `SKILL_DIR` from `config.py`, not the current working directory. This is critical because `stamp_photo.py` runs from the application folder (via `cd "$app_dir"` in `compile_resume`), but the photo file lives in the skill directory. Without this fix, `os.path.exists("okf/SAGAR_MARTHANDAN_foto.jpg")` resolves to the wrong directory and returns False.

### Font rule

LaTeX mode renders in Latin Modern Roman 10 (`lmodern`). The `.tex` preamble must never be patched to change fonts. A keyword miss in the parseability audit means the YAML wording is unrecoverable in the PDF text layer — fix by adjusting YAML wording (de-parenthesize, split strings, remove special characters), not by swapping fonts.

---

## What Was Removed (vs. okf-cv)

| Component | Why |
|:---|:---|
| `okf_portfolio_search.py` | OKF phrase matching — replaced by LLM judgment |
| `zvec_hybrid_search.py` | Zvec embeddings + score fusion — replaced by LLM |
| `embedding_server.py` | SentenceTransformer TCP daemon — no embeddings needed |
| `okf_lint.py` | Frontmatter linter — no frontmatter (catalog YAML is source) |
| `okf_learn.py` | Self-learning keyword enrichment — no keyword matching to enrich |
| `okf_utils.py` | Shared utils (tokenize, stopwords) — only used by deleted files |
| `resume_jd_similarity.py` | Cosine similarity via Zvec — no Zvec |
| `okf/portfolio/` (16 .md) | Individual project files — replaced by catalog YAML |
| `okf/synonyms.yaml` | Synonym map — LLM handles synonyms natively |
| `okf/noise_words.yaml` | Noise word filter — only used by okf_learn.py |
| `okf/phrase_patterns.yaml` | Phrase patterns — only used by okf_learn.py |
| `okf/zvec_db/` | Vector database — no embeddings |

---

## Weekly Review: Diversity Audit

`okf_diversity_audit.py` is a standalone tool for weekly review, not run per application. It reports:
- ATS vendor clustering (warns at >=3 applications to the same vendor in 14 days)
- Referral rate (warns at <20%)

Run: `/home/sagar/Skills/llm-cv/.venv/bin/python okf_diversity_audit.py`
