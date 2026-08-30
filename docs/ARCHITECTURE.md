# LLM-CV Architecture

## Overview

LLM-CV is an ATS-optimized resume and cover letter generation pipeline. The agent reads a condensed project catalog, ranks the top 6 projects for the JD using LLM judgment, rewrites the resume to close skill gaps, compiles everything to PDF, and syncs to an Obsidian vault.

### Design Philosophy

- **LLM judgment over algorithmic matching:** The LLM ranker correctly distinguishes AI roles from DE roles, prioritizes Power BI projects for BI roles, and understands domain relevance — all without maintaining synonyms, allowlists, or transferable skills.
- **Single source of truth:** One `project_catalog.yaml` file replaces 16 portfolio `.md` files, a synonyms map, a body-skill allowlist, and a transferable skills definition.
- **Minimal dependencies:** Only `pyyaml`, `reportlab`, `pypdf` — no vector databases, embedding models, or ML frameworks.
- **Token-efficient:** Documentation slimmed 56%, guardrails de-duplicated, lazy loading, and session splitting reduce token consumption by 84% per run (~400K vs ~2.5M). See [Token Optimization](../README.md#token-optimization).

---

## Pipeline Flow

### Single-Session Mode (interactive)

All steps run in one agent conversation. Context accumulates across steps.

```
Step 0 (optional): JD Fetch — URL → clean JD text
    └── Jina Reader for JS-SPA vendors, webfetch fallback, manual paste safety net

Step 1: ATS Analysis & JD Archival
    ├── Load archetype-specific base resume (per user's language selection)
    ├── ATS scoring (4-category German-market matrix, 0-100)
    ├── LLM Project Ranking:
    │   ├── Read okf/project_catalog.yaml (15 projects)
    │   ├── Rank 15 projects → top 6 for this JD
    │   └── Write project_info.md directly (no Python script)
    ├── Skill gap analysis
    ├── Contextual placement weighting
    ├── ATS vendor inference & application source
    ├── Location tailoring (static lookup + web search fallback)
    └── Persist First Action selections (render_mode, resume_style, language) in ATS_Report.yaml
    → Outputs: ATS_Report.yaml/.pdf, Job_Description.yaml/.pdf, project_info.md

Step 2: Resume Rewrite & Visual Layout Audit
    ├── Read project_info.md + ATS_Report.yaml (render_mode, resume_style, language from here)
    ├── Keyword stuffing decision (user chooses: Add all / No stuffing / Selective)
    ├── Generate Resume.yaml (archetype-tailored, skill gap closure)
    ├── Compile via LaTeX (tex-only → pdflatex × 2 → stamp photo) or ReportLab fallback (NO photo stamping)
    ├── Visual layout audit (character counts, page splits, Stop-Slop, page-fill density, zero empty trailing lines)
    ├── Parse-integrity audit (resume_parseability.py — auto-recovers via ReportFallback)
    ├── AI watermark check (check_watermarks.py — scans YAML + PDF for C2PA, XMP, invisible Unicode, vendor strings)
    └── Post-rewrite ATS rescoring (updates post_rewrite_ats_score in ATS_Report.yaml)

Step 3: Cover Letter Generation
    ├── Read ATS_Report.yaml + Job_Description.yaml + project_info.md (render_mode, language from ATS_Report.yaml)
    ├── Generate Cover_Letter.yaml (DIN 5008 Form B, metric-grounded)
    ├── Compile via LaTeX (or ReportLab fallback)
    ├── AI watermark check (check_watermarks.py — scans Cover_Letter.yaml + PDF)
    └── Obsidian vault sync + folder sort

Post-Pipeline:
    ├── sync_to_obsidian.py --sort (Obsidian vault sync + folder sort)
    ├── stamp_photo.py (LaTeX mode only — stamps candidate photo onto resume PDF; NEVER used in ReportFallback mode)
```

### Session-Split Mode (token-efficient — recommended)

`run_pipeline.sh` runs each step as a separate OMP session with clean context. Steps chain via disk files (YAML outputs). No cross-step context accumulation.

```
Session 1 (Step 1): ~10 API calls, ~20K base context
    reads: SKILL.md + 01_ats_and_jd_archival.md + project_catalog.yaml + base resume
    writes: ATS_Report.yaml, Job_Description.yaml/.pdf, project_info.md
    ↓ session ends — clean context

Session 2 (Step 2): ~12 API calls, ~11K base context
    reads: SKILL.md + 02_resume_and_visual_audit.md + ATS_Report.yaml + project_info.md + base resume
    writes: Resume.yaml, Resume.tex, Resume.pdf, Layout_Audit_Report.yaml, Parseability_Report.yaml/.pdf, watermark check (check_watermarks.py)
    ↓ session ends — clean context

Session 3 (Step 3): ~8 API calls, ~8K base context
    reads: SKILL.md + 03_cover_letter.md + ATS_Report.yaml + Job_Description.yaml + project_info.md
    writes: Cover_Letter.yaml, Cover_Letter.pdf, watermark check (check_watermarks.py), Obsidian notes
```

**Inter-step contract:** `ATS_Report.yaml` carries `render_mode`, `resume_style`, `language`, `application_source`, `skill_gaps`, `improvement_blueprint`, `role_archetype`, `closest_candidate_location` — all read by Step 2 and Step 3 from disk. The wrapper script collects the keyword stuffing decision (not persisted to disk) between Step 1 and Step 2 and passes it inline in the Step 2 prompt.

**Manual re-runs:** Each step can be re-run independently. Launch an OMP session with the appropriate prompt (see `prompts/step1.md`, `prompts/step2.md`, `prompts/step3.md` for reference). The agent reads previous step outputs from disk.

---

## Token Optimization Architecture

Five techniques applied to minimize token consumption for LLM-based agent runtimes:

### 1. De-duplicated Guardrails

Shared rules (read-only, anti-hallucination, YAML safety, Stop-Slop) live in `SKILL.md` only. Step docs reference them with 1-line pointers:

```
> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules", §"Anti-Hallucination Principles".
```

Each step doc keeps only its writable-files list. Saves ~8,800 base tokens.

### 2. Slimmed Documentation

All 5 docs condensed by 50-62%: prose → tables, verbose explanations → bullets, YAML schemas preserved verbatim. Total skill docs: 117,906 → 51,979 bytes (56% reduction). Saves ~16,500 base tokens.

### 3. Lazy Loading

Only the current step doc is read — not all 4 at once. Each step doc ends with `**Next:** Proceed to Step N — read N_*.md`. `SKILL.md` instructs: "Read only the step doc for the step you're executing." Saves ~5,000 base tokens.

### 4. Extracted Completion Checklist

The 30+ item completion checklist moved to `99_completion_checklist.md`, read only at pipeline end. Saves ~2,500 base tokens across 25+ API calls where it's not needed.

### 5. Session Splitting

`run_pipeline.sh` runs each step as a separate OMP session. Each session starts with a clean context — no accumulation from previous steps. The YAML schemas are the contract between steps. Saves ~2M tokens/run.

### Token Consumption Comparison

| Mode | Per run | 4 runs | Quota (60M) | Resumes/month |
|:---|:---|:---|:---|:---|
| Original (pre-optimization) | ~2.5M | ~10M | 16.7% | ~24 |
| Single-session (doc slimming) | ~2.0M | ~8M | 13.3% | ~30 |
| **Session-split (all optimizations)** | **~400K** | **~1.6M** | **2.7%** | **~149** |

> **Prompt caching note:** On nanoGPT subscription plans, cached tokens still count toward quota at full rate. Doc slimming and session splitting are the only levers for subscription users.

---

## Project Catalog

`okf/project_catalog.yaml` is the single source of truth for all project data. It contains 15 projects, each with:

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

The agent reads this catalog in Step 1 and ranks the top 6 projects for the JD. The ranking considers:
1. Direct technology/tool overlap
2. Transferable competencies (via `transferable_skills` field)
3. Business-problem match (via `business_problem` field)
4. Role archetype fit
5. Project complexity and seniority relevance
6. Reframing potential for the role's seniority level

`key_metrics` is the authoritative metric source — the agent cites it verbatim and never invents numbers beyond it.

---

## File Inventory

### Pipeline Scripts (11 Python files)
| File | Role |
|:---|:---|
| `config.py` | Location lookup, candidate cities, geocode table |
| `yaml_to_pdf.py` | PDF compilation entry point (routes YAML to renderers) |
| `resume_parseability.py` | ATS parse-integrity audit on compiled PDF (auto-recovers via ReportFallback) |
| `stamp_photo.py` | Candidate photo stamping onto LaTeX-mode resume PDFs (NEVER used in ReportFallback mode) |
| `check_watermarks.py` | AI watermark/provenance check — scans YAML + PDF for C2PA, XMP, invisible Unicode, vendor strings (run after every compilation) |
| `organize_applications.py` | Application folder organization (date tree sort) |
| `obsidian_sync_core.py` | Obsidian sync core logic |
| `obsidian_folder_sort.py` | Folder sorting logic |
| `sync_to_obsidian.py` | Obsidian sync entry point |
| `track_outcomes.py` | Application outcome tracking |
| `okf_diversity_audit.py` | Weekly diversity audit (standalone) |

### Renderers (14 files in `renderers/`)

| File | Role |
|:---|:---|
| `utils.py` | Shared utilities (`escape_latex`, color constants, `run_pdflatex`, font registration) |
| `resume_common.py` | Shared resume helpers (`HEADERS`, `get_resume_language`) |
| `resume.py` | Resume renderer dispatcher (reads `render_mode` + `resume_style`) |
| `resume_latex_us.py` | Resume LaTeX renderer (US style) + parse-integrity audit |
| `resume_reportfallback_us.py` | Resume ReportLab renderer (US style, LM Roman 10) |
| `resume_latex_german.py` | Resume LaTeX renderer (German style, Lebenslauf section order) |
| `resume_reportfallback_german.py` | Resume ReportLab renderer (German style, LM Roman 10) |
| `cover_letter.py` | Cover Letter renderer dispatcher (reads `render_mode`) |
| `cover_letter_latex.py` | Cover Letter LaTeX renderer |
| `cover_letter_reportfallback.py` | Cover Letter ReportLab renderer (LM Roman 10) |
| `job_description.py` | Job Description renderer (ReportLab only) |
| `ats_report.py` | ATS Report renderer (ReportLab only) |
| `parseability_report.py` | Parseability Report renderer (ReportLab only, LM Roman 10) |
| `__init__.py` | Package init |

### Pipeline Step Docs (6 `.md` files)

| File | Role | Size (optimized) |
|:---|:---|:---|
| `SKILL.md` | Master pipeline orchestration, guardrails, writing rules | 16KB (was 32KB) |
| `00_jd_fetch.md` | Step 0: JD scraping from URLs | 4KB (was 9KB) |
| `01_ats_and_jd_archival.md` | Step 1: ATS scoring, JD archival, LLM project ranking | 10KB (was 24KB) |
| `02_resume_and_visual_audit.md` | Step 2: Resume rewrite, layout audit, parseability | 16KB (was 43KB) |
| `03_cover_letter.md` | Step 3: Cover letter generation | 5KB (was 10KB) |
| `99_completion_checklist.md` | Post-pipeline verification (lazy-loaded, read only at end) | 3KB (new) |

### Session Splitting

| File | Role |
|:---|:---|
| `run_pipeline.sh` | Wrapper script: runs 3 separate OMP sessions, chains via disk |
| `prompts/step1.md` | Step 1 session prompt template (reference) |
| `prompts/step2.md` | Step 2 session prompt template (reference) |
| `prompts/step3.md` | Step 3 session prompt template (reference) |

### Data Files

| File | Role |
|:---|:---|
| `okf/project_catalog.yaml` | 15-project catalog (single source of truth) |
| `okf/base_files/english/` | 4 English archetype base resumes + 1 generic fallback (5 files) |
| `okf/base_files/german/` | 1 German base resume (covers all archetypes) |
| `okf/project_mappings.yaml` | Obsidian sync project name mappings |
| `okf/skill_mappings.yaml` | Obsidian sync skill mappings |
| `okf/.jd_cache/` | JD URL cache (7-day TTL, sha1-keyed) |
| `okf/.location_cache.json` | Cached location lookups for config.py |
| `okf/.font_cache.json` | Font cache for PDF renderers |

### Tests (2 files)

| File | Role |
|:---|:---|
| `tests/test_utils.py` | Renderer utils tests (30 tests) |
| `tests/test_llm_search.py` | LLM ranking smoke test (catalog validation + 3 JD archetypes) |

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
| Daemon/cache files | Embedding server state, lint cache, learning log — all obsolete |

---

## Design Decisions

### Why LLM Ranking Over Algorithmic Search

Tested against 10 real JDs from the Applications folder, the LLM ranker won or tied on 10/10 JDs and was never beaten by the algorithm. It correctly:
- Distinguished AI roles from DE roles
- Prioritized Power BI projects for BI roles
- Understood domain relevance (mobility projects for mobility companies)
- Handled synonyms, transferable skills, and semantic matching natively

The algorithmic system required maintaining synonyms.yaml, body-skill allowlists, transferable_skills definitions, embedding models, and a vector database. The LLM ranker requires only a catalog YAML file.

### Why 8-10 Bullets Per Project

The catalog bullets provide the LLM with enough context to make informed ranking decisions. More signal per project = better rankings. The additional ~200-250 tokens per application is negligible.

### Why Session Splitting

In a single agent session, context accumulates across all 3 steps. Step 3 carries the entire history of Step 1 + Step 2 — all the ATS scoring YAML, project ranking, compile logs, audit results. This is pure overhead: Step 3 only needs `ATS_Report.yaml`, `project_info.md`, and `Job_Description.yaml` (all on disk).

Session splitting gives each step a clean context. The YAML schemas are the contract between steps — no conversation history needed. If a step fails, the wrapper script can re-launch just that step with the same disk inputs.

### project_info.md Format

The output format uses LLM reasoning comments instead of algorithmic diagnostics:
```markdown
<!-- LLM Rank: 1, Reason: Strongest overlap with JD: Spark batch processing, Terraform IaC... -->
```

Step 2 ignores HTML comments, so this change is transparent to the resume rewrite.

### Font Rule

LaTeX mode renders in Latin Modern Roman 10 (`lmodern`). The `.tex` preamble must never be patched to change fonts. A keyword miss in the parseability audit means the YAML wording is unrecoverable in the PDF text layer — fix by adjusting YAML wording (de-parenthesize, split strings, remove special characters), not by swapping fonts.

---

## Weekly Review: Diversity Audit

`okf_diversity_audit.py` is a standalone tool for weekly review, not run per application. It reports:
- ATS vendor clustering (warns at ≥3 applications to the same vendor in 14 days)
- Referral rate (warns at <20%)

Run: `/home/sagar/Skills/llm-cv/.venv/bin/python okf_diversity_audit.py`
