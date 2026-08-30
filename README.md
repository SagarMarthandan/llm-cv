# LLM-CV

ATS-optimized resume and cover letter tailoring pipeline. Paste a job description (or a URL) and get a tailored resume + cover letter as compiled PDFs, an archived JD, and an ATS score report.

## How It Works

The agent reads a 16-project catalog (`okf/project_catalog.yaml`), ranks the top 6 projects for the JD using LLM judgment, rewrites the resume to close skill gaps, compiles everything to PDF via LaTeX (or ReportLab fallback), and syncs to an Obsidian vault.

No vector databases. No embedding models. No keyword matching algorithms. The LLM is the ranker.

```
URL (optional) ──► Step 0: JD Fetch ──► Step 1: ATS + Project Ranking ──► Dup Check ──► Step 2: Resume ──► Step 3: Cover Letter ──► Obsidian Sync
                                         (catalog → top 6)                  (vault scan)         (rewrite + audit)    (DIN 5008)
```

## Quick Start

### Interactive (single session)

1. Paste a JD (or a job posting URL)
2. Type `execute llm-cv`
3. Answer the 4-question startup prompt (render mode, resume style, application source, language)
4. The agent runs all steps end-to-end and writes outputs to `/home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/`

### Token-efficient (session splitting — recommended)

```bash
cd /home/sagar/Skills/llm-cv
./run_pipeline.sh                          # interactive — prompts for JD
./run_pipeline.sh "paste JD text here"     # pass JD text directly
./run_pipeline.sh --url "https://..."      # fetch JD from URL (triggers Step 0)
./run_pipeline.sh --file jd.txt            # read JD from file
```

The wrapper script runs each pipeline step as a separate OMP session with clean context, chaining via disk files. This reduces token consumption by **84%** (~400K tokens/run vs ~2.5M single-session). See [Token Optimization](#token-optimization) below.

## Prerequisites

- **Python 3.10+** with `pyyaml`, `reportlab`, `pypdf` (in `.venv/`)
- **TeX Live** (`pdflatex`) for LaTeX-mode PDFs
- **Fonts**: Latin Modern Roman 10, CMU Concrete, Google Sans Code, Calibri/Carlito, Segoe UI, Cambria
- **Candidate photo** (`okf/SAGAR_MARTHANDAN_foto.jpg`) — automatically stamped onto the top-right corner of LaTeX-mode resume PDFs

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
| **2** | Resume rewrite (skill gap closure, keyword stuffing decision, archetype tuning, 3-line project summaries, JD-relevant skills only, optional Score-Boost Mode when initial ATS score < 85), LaTeX/ReportLab compilation (NO photo stamping in ReportFallback), visual layout audit (zero empty trailing lines), parse-integrity audit, AI watermark check. | `Resume.yaml`, `SAGAR_MARTHANDAN_Resume.pdf`, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml/.pdf` |
| **Dup** | Duplicate application check. Searches Obsidian vault + Applications filesystem tree for prior applications to the same company + role. Fuzzy-matches company (strips legal suffixes) and role (strips gender markers). User chooses: proceed, abort, or reuse prior resume as starting point. | `check_duplicate_application.py` output (stdout) |
| **3** | Cover letter generation (DIN 5008 Form B for German, business letter for English), metric-grounded prose, AI watermark check. | `Cover_Letter.yaml`, `SAGAR_MARTHANDAN_Cover_Letter.pdf` |
| **Post** | Obsidian vault sync + folder sort into date tree. | Obsidian notes, sorted application folder |

## Token Optimization

The pipeline documentation was optimized to minimize token consumption for LLM-based agent runtimes (DeepSeek, GLM, Claude, etc.). Five techniques are applied:

| Technique | What it does | Tokens saved/run |
|:---|:---|:---|
| **De-duplicated guardrails** | Shared rules (read-only, anti-hallucination, YAML safety, Stop-Slop) live in `SKILL.md` only; step docs reference them with 1-line pointers | ~8,800 base |
| **Slimmed docs** | Condensed verbose prose to tables, bullets, and compact schemas across all 5 docs (56% total reduction) | ~16,500 base |
| **Lazy loading** | Only the current step doc is read — not all 4 at once. Proceed-to-next directives chain steps | ~5,000 base |
| **Extracted checklist** | Completion checklist moved to `99_completion_checklist.md`, read only at pipeline end | ~2,500 base |
| **Session splitting** | `run_pipeline.sh` runs each step as a separate session with clean context — no cross-step accumulation | ~2,000,000/run |

### Token consumption comparison

| Mode | Per run | 4 runs | Quota (60M) | Resumes/month |
|:---|:---|:---|:---|:---|
| Original (pre-optimization) | ~2.5M | ~10M | 16.7% | ~24 |
| Single-session (doc slimming only) | ~2.0M | ~8M | 13.3% | ~30 |
| **Session-split (all optimizations)** | **~400K** | **~1.6M** | **2.7%** | **~149** |

> **Prompt caching note:** On nanoGPT subscription plans, cached tokens still count toward quota at full rate. Doc slimming and session splitting are the only levers for subscription users. PAYG users benefit from prompt caching as well.

## Photo Stamping

Resumes compiled in LaTeX mode automatically get the candidate's headshot (`okf/SAGAR_MARTHANDAN_foto.jpg`) stamped onto the top-right corner of page 1 as a post-processing step. The photo aligns with the name text at the top and sits just above the first section separator line.

- **LaTeX mode:** Photo stamped automatically (1.40in, top-right)
- **ReportFallback mode:** NO photo stamping — `stamp_photo.py` is never invoked; the `resume.py` dispatcher guards this with a `mode == 'latex'` check
- **Disable per-application:** Set `contact_info.photo: null` in `Resume.yaml`
- **Custom photo:** Set `contact_info.photo: /path/to/photo.jpg` in `Resume.yaml`
- **Override default:** Set `LLM_CV_CANDIDATE_PHOTO` env var

## AI Watermark Check

After every resume and cover letter compilation, `check_watermarks.py` scans the generated YAML and PDF files for AI provenance marks. The check runs automatically as the last step of each compilation block (Step 2 Step E, Step 3 compilation).

**Three detection layers** (adapted from the `remove-ai-marks` skill):

| Layer | What it checks |
|:---|:---|
| **A — Invisible Unicode** | Zero-width chars (ZWSP, ZWNJ, ZWJ, BOM), bidi controls (LRE/RLO/LRI), tag characters (U+E0001–E007F), variation selectors, space homoglyphs in YAML text |
| **B — C2PA binary markers** | JUMBF, c2pa, contentcredentials, c2ma in PDF non-stream data (strips FlateDecode streams to avoid false positives from compressed photo images) |
| **C — PDF metadata** | XMP packets (`<?xpacket`, `<x:xmpmeta`, `<rdf:RDF`), AI vendor strings in metadata fields (Claude, Anthropic, OpenAI, SynthID, AI generated, Content Credentials) |

**Exit codes:** 0 = clean, 1 = marks found, 2 = usage error. The script detects only — it does NOT modify files.

```bash
# Individual files
.venv/bin/python check_watermarks.py Resume.yaml SAGAR_MARTHANDAN_Resume.pdf

# Entire application folder
.venv/bin/python check_watermarks.py --dir "/path/to/application/"

# JSON output
.venv/bin/python check_watermarks.py --json Resume.yaml SAGAR_MARTHANDAN_Resume.pdf
```

## Score-Boost Mode

When the initial ATS score from Step 1 is below 85, the wrapper script asks the user whether to apply score-boosting measures before launching Step 2. The prompt shows the score and lists what each measure would change:

1. **Student Framing** — leads the summary with "M.Sc. student in [field] and [archetype]" for intern/student roles
2. **Exact JD Phrase Weaving** — weaves distinctive JD verb phrases into truthful bullet prose (e.g. "data transformation workflows", "SQL stored procedures")
3. **Real Adjacent Skills** — re-adds streaming/API skills (Kafka, Redis, REST APIs) if the JD demands bots/automation and the base resume has them
4. **Itemized Scoring Rubric** — post-rewrite rescoring against explicit JD term lists with matched/unmatched items for rigorous score justification

Measures 1-3 apply during the resume rewrite (Step 2 §1). Measure 4 applies during post-rewrite ATS rescoring (Step 2 §5). All measures respect anti-hallucination rules — no fabricating capabilities or metrics. Full detail in `prompts/score_boost.md`. If the score is ≥ 85, the prompt is skipped entirely.

## Duplicate Application Check

Before the resume rewrite begins, `run_pipeline.sh` runs `check_duplicate_application.py` to search the Obsidian vault (`~/Documents/Obsidian Vault/Job Search/Applications/`) and the Applications filesystem tree (`~/Applications/YYYY/MM/DD/`) for prior applications to the same company + role. The script:

- **Normalizes** company names (strips legal suffixes like GmbH, AG, SE & Co. KG) and role titles (strips gender markers like `(m/w/d)`, `(all genders)`) before fuzzy-matching with `SequenceMatcher`
- **Thresholds:** company similarity ≥ 0.88, role similarity ≥ 0.82 (lowered to 0.77 when company is near-exact match)
- **Deduplicates** Obsidian + filesystem hits by normalized (company, role, date), preferring Obsidian source for richer ATS score data
- **Self-excludes** the current application folder when run in `--app_dir` mode

If duplicates are found, the user is prompted with three options:

1. **Proceed** — rewrite the resume from scratch anyway
2. **Abort** — stop the pipeline
3. **Reuse prior resume** — copies the most recent prior `Resume.yaml` as the starting point for Step 2

Can also be run standalone:

```bash
.venv/bin/python check_duplicate_application.py <app_dir>           # read company/role from ATS_Report.yaml
.venv/bin/python check_duplicate_application.py --company "X" --position "Y"  # direct lookup
.venv/bin/python check_duplicate_application.py <app_dir> --json    # JSON output for programmatic use
```

## Project Catalog

`okf/project_catalog.yaml` — single source of truth for all project data. 16 projects, each with:

| Field | Description |
|:---|:---|
| `title` | Project title |
| `description` | One-line summary |
| `technologies` | Comma-separated tech stack |
| `archetypes` | Role archetypes this project fits |
| `bullets` | 8-10 detailed bullets with quantified metrics (catalog source; resume uses 3) |
| `keywords` | Search/matching keywords |

## File Structure

```
llm-cv/
├── SKILL.md                          # Agent-facing pipeline orchestration
├── 00_jd_fetch.md                    # Step 0: URL → JD text
├── 01_ats_and_jd_archival.md         # Step 1: ATS + ranking + archival
├── 02_resume_and_visual_audit.md     # Step 2: Resume rewrite + audit
├── 03_cover_letter.md                # Step 3: Cover letter
├── 99_completion_checklist.md        # Post-pipeline verification (lazy-loaded)
├── run_pipeline.sh                   # Session-splitting wrapper script
├── prompts/                          # Session prompt templates (reference docs)
│   ├── step1.md
│   ├── step2.md
│   ├── step3.md
│   └── score_boost.md                 # Score-Boost measures reference (conditional, user-opt-in)
├── config.py                         # Location lookup, candidate info
├── yaml_to_pdf.py                    # PDF compilation entry point
├── resume_parseability.py            # ATS parse-integrity audit
├── stamp_photo.py                    # Candidate photo stamping (LaTeX ONLY — never ReportFallback)
├── sync_to_obsidian.py               # Obsidian sync entry point
├── check_watermarks.py                # AI watermark/provenance check (run after every compilation)
├── check_duplicate_application.py      # Duplicate application detection (Obsidian vault + filesystem)
├── track_outcomes.py                 # Outcome tracking
├── okf_diversity_audit.py            # Weekly diversity audit (standalone)
├── renderers/                        # 14 LaTeX + ReportLab renderers
├── okf/
│   ├── project_catalog.yaml          # 16-project catalog (source of truth)
│   ├── project_mappings.yaml         # Obsidian sync mappings
│   ├── skill_mappings.yaml           # Obsidian sync mappings
│   ├── base_files/                   # 6 base resumes (unified 72-skill set, archetype-specific ordering)
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

## Session Splitting

`run_pipeline.sh` orchestrates 3 separate OMP sessions that chain via disk files:

```
Session 1 (Step 1): ~10 calls, ~20K base context
    ↓ writes ATS_Report.yaml, Job_Description.yaml, project_info.md to disk
    ↓ session ends — clean context
    ↓ wrapper runs duplicate application check against Obsidian vault + Applications tree
    ↓ if duplicate found: user chooses proceed / abort / reuse prior resume
    ↓ wrapper reads ATS score; if < 85, asks user about Score-Boost Mode
    ↓ passes score_boost_mode + keyword stuffing decision inline to Step 2

Session 2 (Step 2): ~12 calls, ~11K base context
    ↓ reads Step 1 outputs from disk
    ↓ writes Resume.yaml, compiles resume (NO photo stamping in ReportFallback), runs audits, runs AI watermark check
    ↓ session ends — clean context

Session 3 (Step 3): ~8 calls, ~8K base context
    ↓ reads Step 1+2 outputs from disk
    ↓ writes Cover_Letter.yaml, compiles, runs AI watermark check, runs Obsidian sync
```

**How steps chain:** The YAML schemas are the contract between steps. `ATS_Report.yaml` carries `render_mode`, `resume_style`, `language`, `application_source`, `skill_gaps`, `improvement_blueprint`, `role_archetype`, and `closest_candidate_location` — all read by Step 2 and Step 3 from disk. The wrapper script collects the keyword stuffing decision and Score-Boost Mode decision (not persisted to disk) between Step 1 and Step 2 and passes them inline. If the initial ATS score is < 85, the user is prompted to opt in to Score-Boost Mode before Step 2 launches.

**Manual re-runs:** Each step can be re-run independently by launching an OMP session with the appropriate prompt template (see `prompts/step1.md`, `prompts/step2.md`, `prompts/step3.md`). The agent reads previous step outputs from disk.

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
| [99_completion_checklist.md](99_completion_checklist.md) | Post-pipeline verification checklist |

## Self-Refresh

Type `refresh llm-cv` to reload the skill from ground truth. The agent locates `SKILL.md` on the local filesystem (or pulls from [GitHub](https://github.com/SagarMarthandan/llm-cv) as fallback), copies it to the CLI's skill store, and ingests all supporting `.md` files.
