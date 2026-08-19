# LLM-CV Architecture

## Overview

LLM-CV is an ATS-optimized resume and cover letter generation pipeline. It replaces the previous algorithmic search engine (OKF phrase matching + Zvec semantic embeddings) with a single LLM-based ranking step where the pipeline agent reads a condensed project catalog and selects the best projects for the job description using its own judgment.

### Design Philosophy

- **LLM judgment over algorithmic matching:** The LLM ranker correctly distinguishes AI roles from DE roles, prioritizes Power BI projects for BI roles, and understands domain relevance — all without maintaining synonyms, allowlists, or transferable skills.
- **Single source of truth:** One `project_catalog.yaml` file replaces 16 portfolio `.md` files, a synonyms map, a body-skill allowlist, and a transferable skills definition.
- **Minimal dependencies:** Only `pyyaml`, `reportlab`, `pypdf` — no vector databases, embedding models, or ML frameworks.
- **Cost:** ~400K tokens per application in session-split mode (~1.6M for 4 runs). Single-session mode: ~2.5M tokens/run. See [Token Optimization](../README.md#token-optimization) for details.

---

## Pipeline Flow

```
Step 0 (optional): JD Fetch — URL → clean JD text
    └── Jina Reader for JS-SPA vendors, webfetch fallback, manual paste safety net

Step 1: ATS Analysis & JD Archival
    ├── Load archetype-specific base resume
    ├── ATS scoring (4-category German-market matrix, 0-100)
    ├── LLM Project Ranking:
    │   ├── Read okf/project_catalog.yaml (16 projects)
    │   ├── Read Job_Description.yaml
    │   ├── Rank 16 projects → top 6 for this JD
    │   └── Write project_info.md directly (no Python script)
    ├── Skill gap analysis
    ├── Contextual placement weighting
    ├── ATS vendor inference & application source
    └── Location tailoring (static lookup + web search fallback)
    → Outputs: ATS_Report.yaml/.pdf, Job_Description.yaml/.pdf, project_info.md

Step 2: Resume Rewrite & Visual Layout Audit
    ├── Read project_info.md + ATS_Report.yaml
    ├── Generate Resume.yaml (archetype-tailored, skill gap closure)
    ├── Compile via LaTeX (or ReportLab fallback)
    ├── Visual layout audit (character counts, page splits, Stop-Slop)
    ├── Parse-integrity audit (resume_parseability.py)
    └── Post-rewrite ATS rescoring
    → Outputs: Resume.yaml, SAGAR_MARTHANDAN_Resume.pdf, Layout_Audit_Report.yaml, Parseability_Report.yaml/.pdf

Step 3: Cover Letter Generation
    ├── Read project_info.md + ATS_Report.yaml + Job_Description.yaml
    ├── Generate Cover_Letter.yaml (DIN 5008 Form B, metric-grounded)
    └── Compile via LaTeX (or ReportLab fallback)
    → Outputs: Cover_Letter.yaml, SAGAR_MARTHANDAN_Cover_Letter.pdf

Post-Pipeline:
    ├── sync_to_obsidian.py --sort (Obsidian vault sync + folder sort)
    └── okf_diversity_audit.py (standalone weekly tool, not per-application)
```

---

## Project Catalog

`okf/project_catalog.yaml` is the single source of truth for all project data. It contains 16 projects, each with:

| Field | Type | Description |
|:---|:---|:---|
| `title` | string | Project title |
| `description` | string | One-line project description |
| `technologies` | string | Comma-separated tech list |
| `archetypes` | list | Role archetypes this project fits |
| `repo_url` | string | GitHub URL (empty string if none) |
| `bullets` | list (8-10) | Detailed project bullets with metrics |
| `keywords` | list | Search/matching keywords |

The agent reads this catalog in Step 1 and ranks the top 6 projects for the JD. The ranking considers:
1. Direct technology/tool overlap
2. Transferable competencies
3. Role archetype fit
4. Project complexity and seniority relevance
5. Reframing potential for the role's seniority level

---

## File Inventory

### Pipeline Scripts (9 Python files)

| File | Role |
|:---|:---|
| `config.py` | Location lookup, candidate cities, geocode table |
| `yaml_to_pdf.py` | PDF compilation entry point (routes YAML to renderers) |
| `resume_parseability.py` | ATS parse-integrity audit on compiled PDF |
| `organize_applications.py` | Application folder organization |
| `obsidian_sync_core.py` | Obsidian sync core logic |
| `obsidian_folder_sort.py` | Folder sorting logic |
| `sync_to_obsidian.py` | Obsidian sync entry point |
| `track_outcomes.py` | Application outcome tracking |
| `okf_diversity_audit.py` | Weekly diversity audit (standalone) |

### Renderers (14 files in `renderers/`)

All LaTeX/ReportLab renderers are unchanged from the original pipeline. See `renderers/__init__.py` for the package structure.

### Pipeline Step Docs (6 `.md` files)

| File | Role |
|:---|:---|
| `SKILL.md` | Master pipeline orchestration, guardrails, writing rules |
| `00_jd_fetch.md` | Step 0: JD scraping from URLs |
| `01_ats_and_jd_archival.md` | Step 1: ATS scoring, JD archival, LLM project ranking |
| `02_resume_and_visual_audit.md` | Step 2: Resume rewrite, layout audit, parseability |
| `03_cover_letter.md` | Step 3: Cover letter generation |
| `99_completion_checklist.md` | Post-pipeline verification (lazy-loaded, read only at end) |

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
| `okf/project_catalog.yaml` | 16-project catalog (single source of truth) |
| `okf/base_files/english/` | 5 English archetype base resumes |
| `okf/base_files/german/` | 5 German archetype base resumes |
| `okf/project_mappings.yaml` | Obsidian sync project name mappings |
| `okf/skill_mappings.yaml` | Obsidian sync skill mappings |
| `okf/.location_cache.json` | Cached location lookups for config.py |
| `okf/.font_cache.json` | Font cache for PDF renderers |

### Tests (2 files)

| File | Role |
|:---|:---|
| `tests/test_utils.py` | Renderer utils tests (unchanged) |
| `tests/test_llm_search.py` | LLM ranking smoke test |

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

### project_info.md Format

The output format uses LLM reasoning comments instead of algorithmic diagnostics:
```markdown
<!-- LLM Rank: 1, Reason: Strongest overlap with JD: Spark batch processing, Terraform IaC... -->
```

Step 2 ignores HTML comments, so this change is transparent to the resume rewrite.

---

## Weekly Review: Diversity Audit

`okf_diversity_audit.py` is a standalone tool for weekly review, not run per application. It reports:
- ATS vendor clustering (warns at ≥3 applications to the same vendor in 14 days)
- Referral rate (warns at <20%)

Run: `/home/sagar/Skills/llm-cv/.venv/bin/python okf_diversity_audit.py`
