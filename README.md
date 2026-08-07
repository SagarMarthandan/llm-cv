[//]: # (DEVELOPER DOCUMENTATION ONLY — not part of agent runtime context. Do not read this file during pipeline execution.)
# LLM-CV

ATS-optimized resume and cover letter tailoring pipeline. Paste a job description (or a URL) and get a tailored resume + cover letter as compiled PDFs, an archived JD, and an ATS score report.

## How It Works

The agent reads a 16-project catalog (`okf/project_catalog.yaml`), ranks the top 6 projects for the JD using LLM judgment, rewrites the resume to close skill gaps, compiles everything to PDF via LaTeX (or ReportLab fallback), and syncs to an Obsidian vault.

No vector databases. No embedding models. No keyword matching algorithms. The LLM is the ranker.

```
URL (optional) ──► Step 0: JD Fetch ──► Step 1: ATS + Project Ranking ──► Step 2: Resume ──► Step 3: Cover Letter ──► Obsidian Sync
                                         (catalog → top 6)                  (rewrite + audit)    (DIN 5008)
```

## Quick Start

1. Paste a JD (or a job posting URL)
2. Type `execute llm-cv`
3. The agent runs all steps end-to-end and writes outputs to `/home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/`

## Prerequisites

- **Python 3.12+** with `pyyaml`, `reportlab`, `pypdf` (in `.venv/`)
- **TeX Live** (`pdflatex`) for LaTeX-mode PDFs
- **Fonts**: Latin Modern Roman 10, CMU Concrete, Google Sans Code, Calibri/Carlito, Segoe UI, Cambria

```bash
# Create venv
uv venv .venv && uv pip install --python .venv/bin/python pyyaml reportlab pypdf

# TeX Live (Debian/Ubuntu)
sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-lang-german
```

## Pipeline Steps

| Step | What happens | Outputs |
|:---|:---|:---|
| **0** (optional) | Scrape JD from URL. Jina Reader for JS-SPA sites, webfetch for static, manual paste fallback. | Clean JD text |
| **1** | ATS scoring (4-category matrix, 0-100), archetype detection, LLM project ranking (16 → top 6), JD archival, location tailoring. | `ATS_Report.yaml/.pdf`, `Job_Description.yaml/.pdf`, `project_info.md` |
| **2** | Resume rewrite (skill gap closure, archetype tuning), LaTeX/ReportLab compilation, visual layout audit, parse-integrity audit. | `Resume.yaml`, `SAGAR_MARTHANDAN_Resume.pdf`, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml/.pdf` |
| **3** | Cover letter generation (DIN 5008 Form B for German, business letter for English), metric-grounded prose. | `Cover_Letter.yaml`, `SAGAR_MARTHANDAN_Cover_Letter.pdf` |
| **Post** | Obsidian vault sync + folder sort into date tree. | Obsidian notes, sorted application folder |

## Project Catalog

`okf/project_catalog.yaml` — single source of truth for all project data. 16 projects, each with:

| Field | Description |
|:---|:---|
| `title` | Project title |
| `description` | One-line summary |
| `technologies` | Comma-separated tech stack |
| `archetypes` | Role archetypes this project fits |
| `repo_url` | GitHub URL (empty string if none) |
| `bullets` | 8-10 detailed bullets with quantified metrics |
| `keywords` | Search/matching keywords |

## File Structure

```
llm-cv/
├── SKILL.md                          # Agent-facing pipeline orchestration
├── 00_jd_fetch.md                    # Step 0: URL → JD text
├── 01_ats_and_jd_archival.md         # Step 1: ATS + ranking + archival
├── 02_resume_and_visual_audit.md     # Step 2: Resume rewrite + audit
├── 03_cover_letter.md                # Step 3: Cover letter
├── config.py                         # Location lookup, candidate info
├── yaml_to_pdf.py                    # PDF compilation entry point
├── resume_parseability.py            # ATS parse-integrity audit
├── sync_to_obsidian.py               # Obsidian sync entry point
├── obsidian_sync_core.py             # Obsidian sync core logic
├── obsidian_folder_sort.py           # Folder sorting logic
├── organize_applications.py          # Application folder organization
├── track_outcomes.py                 # Outcome tracking
├── okf_diversity_audit.py            # Weekly diversity audit (standalone)
├── renderers/                        # 14 LaTeX + ReportLab renderers
├── okf/
│   ├── project_catalog.yaml          # 16-project catalog (source of truth)
│   ├── project_mappings.yaml         # Obsidian sync mappings
│   ├── skill_mappings.yaml           # Obsidian sync mappings
│   ├── base_files/                   # 5 English + 1 German base resumes
│   ├── .jd_cache/                    # JD URL cache (7-day TTL)
│   ├── .location_cache.json          # Cached location lookups
│   └── .font_cache.json              # Font cache
├── tests/
│   ├── test_utils.py                 # Renderer utils tests
│   └── test_llm_search.py            # LLM ranking smoke test
├── docs/
│   ├── ARCHITECTURE.md               # Deep technical reference
│   └── CHANGELOG.md                  # Version history
├── requirements.txt                  # pyyaml, reportlab, pypdf
├── .gitignore
└── llm-cv.code-workspace
```

## Testing

```bash
.venv/bin/python tests/test_utils.py        # 30 renderer tests
.venv/bin/python tests/test_llm_search.py   # Catalog validation + ranking for 3 JD archetypes
```

## Documentation

| Document | Description |
|:---|:---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline flow, file inventory, design decisions |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [SKILL.md](SKILL.md) | Agent-facing skill metadata and execution rules |
| [00_jd_fetch.md](00_jd_fetch.md) | Step 0 rules |
| [01_ats_and_jd_archival.md](01_ats_and_jd_archival.md) | Step 1 rules |
| [02_resume_and_visual_audit.md](02_resume_and_visual_audit.md) | Step 2 rules |
| [03_cover_letter.md](03_cover_letter.md) | Step 3 rules |

## Self-Refresh

Type `refresh llm-cv` to reload the skill from ground truth. The agent locates `SKILL.md` on the local filesystem (or pulls from [GitHub](https://github.com/SagarMarthandan/llm-cv) as fallback), copies it to the CLI's skill store, and ingests all supporting `.md` files.
