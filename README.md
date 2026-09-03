# LLM-CV

ATS-optimized resume and cover letter tailoring pipeline. Paste a job description (or a URL) and get a tailored resume + cover letter as compiled PDFs, an archived JD, and an ATS score report.

## How It Works

The agent asks 4 configuration questions, then launches `run_pipeline.sh` which orchestrates 3 isolated OMP sessions via bash. Each session gets a focused prompt a flash model can handle. Bash handles all compilation, fix loops, and Obsidian sync. No subagent spawning.

```
User says "llm-cv" + JD
    │
    ├── Agent asks 4 questions (render mode, style, source, language)
    │
    └── Agent launches run_pipeline.sh with all flags via ONE bash call
            │
            ├── Session 1: ATS + JD archival + project ranking (reads 21KB condensed catalog)
            ├── [bash] Compile Step 1 PDFs + extract selected projects → selected_projects.yaml
            ├── [bash] Duplicate application check
            ├── Session 2: Resume writer + ATS rescoring (reads 7KB selected_projects.yaml)  ┐ parallel
            ├── Session 3: Cover letter writer (reads project_info.md)                       ┘
            └── [bash] Compile all PDFs + fix loop + photo stamp + watermark check + Obsidian sync
```

No vector databases. No embedding models. No keyword matching algorithms. The LLM is the ranker.

## Quick Start

```bash
cd /home/sagar/Skills/llm-cv

# Interactive (prompts for all options)
./run_pipeline.sh --url "https://careers.forto.com/..."
./run_pipeline.sh "paste JD text here"
./run_pipeline.sh --file jd.txt

# Non-interactive (all options via CLI flags — agent mode)
./run_pipeline.sh --url "https://..." \
    --render latex --style german --source "Cold Apply" --language English \
    --stuffing none --score-boost auto
```

Outputs land in `/home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/`.

### CLI Flags

| Flag | Values | Default |
|:---|:---|:---|
| `--url` / `--file` / positional | JD source | required |
| `--render` | `latex` / `reportfallback` | `latex` |
| `--style` | `us` / `german` | `us` |
| `--source` | `Cold Apply` / `Referral` / `LinkedIn Connection` / `Direct` | `Cold Apply` |
| `--language` | `English` / `German` | auto-detect from JD |
| `--weak-tie` | Contact name/role | required if source is Referral/LinkedIn |
| `--stuffing` | `none` / `all` / `selective` | `none` |
| `--score-boost` | `auto` / `yes` / `no` | `auto` (applies when ATS score < 85) |

## Prerequisites

- **Python 3.10+** with `pyyaml`, `reportlab`, `pypdf` (in `.venv/`)
- **TeX Live** (`pdflatex`) for LaTeX-mode PDFs
- **OMP CLI** (`omp`) at `~/.local/bin/omp` for session launching
- **Candidate photo** (`okf/SAGAR_MARTHANDAN_foto.jpg`) — stamped onto LaTeX-mode resume PDFs

```bash
uv venv .venv && uv pip install --python .venv/bin/python pyyaml reportlab pypdf
sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-lang-german
```

## Pipeline Steps

| Step | What happens | Outputs |
|:---|:---|:---|
| **0** (optional) | Scrape JD from URL. Jina Reader for JS-SPA sites, webfetch for static, manual paste fallback. | Clean JD text |
| **1** | ATS scoring (4-category matrix, 0-100), archetype detection, LLM project ranking (15 → top 6 from condensed 21KB catalog), JD archival, location tailoring. | `ATS_Report.yaml/.pdf`, `Job_Description.yaml/.pdf`, `project_info.md` |
| **[bash]** | Compile Step 1 PDFs. Extract full project data for ranked projects via `extract_projects.py`. | `selected_projects.yaml` (~7KB) |
| **Dup** | Duplicate application check against Obsidian vault + Applications tree. User chooses: proceed, abort, or reuse prior resume. | stdout |
| **2** | Resume rewrite from `selected_projects.yaml` (7KB, not 49KB full catalog). Skill gap closure, keyword stuffing, 3-line project summaries, optional Score-Boost Mode. Post-rewrite ATS rescoring. | `Resume.yaml`, `SAGAR_MARTHANDAN_Resume.pdf` |
| **3** (parallel with 2) | Cover letter generation (DIN 5008 Form B for German, business letter for English), metric-grounded prose. | `Cover_Letter.yaml`, `SAGAR_MARTHANDAN_Cover_Letter.pdf` |
| **[bash]** | Compile resume (pdflatex x2 → stamp photo → parseability audit → watermark check). Compile cover letter. Fix loop if parseability fails. Obsidian sync + folder sort. | Final PDFs, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml/.pdf` |

## Bash-Orchestrated Architecture

`run_pipeline.sh` is the default and only mode for pipeline runs. It launches 3 OMP sessions via bash and handles all compilation between them.

**Why not single-session:** A single-session run consumes ~8M tokens ($0.13). The wrapper uses 3 isolated sessions + bash compilation = ~2M tokens ($0.04). The agent's only job is to ask 4 questions and launch the wrapper.

### Session flow

```
Session 1 (Step 1): ATS + ranking     ~13 API calls
    reads: SKILL.md + 01_ats_and_jd_archival.md + condensed catalog (21KB) + base resume
    writes: ATS_Report.yaml, Job_Description.yaml, project_info.md
    ↓ session ends — clean context

[bash] Compile Step 1 PDFs + extract_projects.py → selected_projects.yaml (7KB)
[bash] Duplicate application check
[bash] Keyword stuffing + score-boost decisions (from CLI flags)

Session 2 (Step 2): Resume writer      ~11 API calls     ┐ parallel
    reads: SKILL.md + 02_resume_and_visual_audit.md + selected_projects.yaml (7KB) + ATS_Report.yaml
    writes: Resume.yaml, updates ATS_Report.yaml with post_rewrite_ats_score
    ↓ session ends                                          │
                                                              │
Session 3 (Step 3): Cover letter       ~5 API calls       ┘
    reads: SKILL.md + 03_cover_letter.md + project_info.md + ATS_Report.yaml
    writes: Cover_Letter.yaml
    ↓ session ends

[bash] Compile resume (pdflatex x2 → stamp photo → parseability → watermark)
[bash] Compile cover letter (yaml_to_pdf → watermark)
[bash] Obsidian sync + sort
```

### Inter-step contract

`ATS_Report.yaml` carries `render_mode`, `resume_style`, `language`, `application_source`, `skill_gaps`, `improvement_blueprint`, `role_archetype`, `closest_candidate_location` — all read by Sessions 2 and 3 from disk. The wrapper passes keyword stuffing and score-boost decisions inline via the session prompt.

### Token consumption

| Mode | Per run | Cost | Notes |
|:---|:---|:---|:---|
| Single-session (old) | ~8M | $0.13 | Agent handles all steps in one conversation |
| Wrapper v1 (interactive) | ~3.4M | $0.07 | 3 sessions + bash, but parent feeds `select` menus via `hub` |
| **Wrapper v2 (CLI flags)** | **~2M** | **$0.04** | Parent does 1 `ask` + 1 `bash` call. 3 child sessions unchanged |

### Bug fixes in wrapper v2

- **`run_session_bg` stdout pollution:** `log()` echoed to stdout, mixing with PID capture. Fixed: redirect to `>&2`.
- **`$(...)` subshell orphans background process:** `PID=$(run_session_bg ...)` runs in a subshell; the backgrounded `timeout` is reparented to init, so `wait $PID` fails. Fixed: use global `_BG_PID=$!` variable.
- **`find` breaks on paths with spaces:** `for f in $(find ...)` splits "Company — Role" into words. Fixed: `while IFS= read -r` with process substitution.
- **`ls` pipefail exit 2:** Glob mismatch under `set -e` + `pipefail` caused cosmetic exit 2 at pipeline end. Fixed: `set +e` around the `ls | awk` pipeline.
- **Photo path resolution:** `get_photo_path()` checked relative paths from the application folder cwd, but photo paths in YAML are relative to the skill directory. Fixed: resolve relative paths against `SKILL_DIR` from `config.py`.

## Condensed Catalog

`okf/project_catalog_condensed.yaml` — same 15 projects as the full catalog but without the `bullets` field (21KB vs 49KB). Step 1 reads this for project ranking. After ranking, `extract_projects.py --from-project-info` extracts full bullet data for only the 6 ranked projects into `selected_projects.yaml` (~7KB), which Step 2 reads instead of the full 49KB catalog.

```bash
# Regenerate condensed catalog
.venv/bin/python extract_projects.py --condensed --catalog okf/project_catalog.yaml --output okf/project_catalog_condensed.yaml

# Extract full data for ranked projects
.venv/bin/python extract_projects.py --from-project-info path/to/project_info.md --catalog okf/project_catalog.yaml --output selected_projects.yaml
```

## Photo Stamping

Resumes compiled in LaTeX mode automatically get the candidate's headshot stamped onto the top-right corner of page 1 as a post-processing step.

- **LaTeX mode:** Photo stamped automatically (1.40in, top-right)
- **ReportFallback mode:** No photo stamping
- **Disable per-application:** Set `contact_info.photo: null` in `Resume.yaml`
- **Custom photo:** Set `contact_info.photo: okf/path/to/photo.jpg` in `Resume.yaml` (relative to skill dir)
- **Override default:** Set `LLM_CV_CANDIDATE_PHOTO` env var

Relative photo paths in YAML are resolved against the skill directory (`SKILL_DIR` from `config.py`), not the current working directory. This ensures stamping works regardless of where `stamp_photo.py` is invoked from.

## AI Watermark Check

After every resume and cover letter compilation, `check_watermarks.py` scans the generated YAML and PDF files for AI provenance marks across three layers:

| Layer | What it checks |
|:---|:---|
| **A — Invisible Unicode** | Zero-width chars, bidi controls, tag characters, variation selectors, space homoglyphs in YAML text |
| **B — C2PA binary markers** | JUMBF, c2pa, contentcredentials in PDF non-stream data (stream-stripped to avoid false positives) |
| **C — PDF metadata** | XMP packets, AI vendor strings (Claude, Anthropic, OpenAI, SynthID, Content Credentials) |

Exit 0 = clean, exit 1 = marks found. Detection only — does not modify files.

## Score-Boost Mode

When the initial ATS score from Step 1 is below 85, the wrapper can apply score-boosting measures before launching Step 2. Pass `--score-boost auto` (default) to apply automatically when score < 85, or `--score-boost yes`/`no` to force.

Four measures (full detail in `prompts/score_boost.md`):

1. **Student Framing** — leads summary with "M.Sc. student in [field] and [archetype]" for intern/student roles
2. **Exact JD Phrase Weaving** — weaves distinctive JD verb phrases into truthful bullet prose
3. **Real Adjacent Skills** — re-adds streaming/API skills if JD demands them and base resume has them
4. **Itemized Scoring Rubric** — post-rewrite rescoring against explicit JD term lists with matched/unmatched items

All measures respect anti-hallucination rules — no fabricating capabilities or metrics.

## Duplicate Application Check

Before the resume rewrite, `check_duplicate_application.py` searches the Obsidian vault and Applications filesystem tree for prior applications to the same company + role.

- **Normalizes** company names (strips GmbH, AG, SE & Co. KG) and role titles (strips `(m/w/d)`, `(all genders)`)
- **Thresholds:** company similarity >= 0.88, role similarity >= 0.82 (lowered to 0.77 when company is near-exact)
- **Options:** Proceed (rewrite anyway), Abort (stop), Reuse prior resume (copy as Step 2 starting point)

## Project Catalog

`okf/project_catalog.yaml` — single source of truth. 15 projects, each with title, description, business_problem, key_metrics, transferable_skills, technologies, archetypes, repo_url, bullets (8-10), keywords.

`key_metrics` is the authoritative metric source — cited verbatim, never invented.

## File Structure

```
llm-cv/
├── SKILL.md                          # Agent-facing pipeline orchestration (always in context)
├── 00_jd_fetch.md                    # Step 0: URL → JD text
├── 01_ats_and_jd_archival.md         # Step 1: ATS + ranking + archival
├── 02_resume_and_visual_audit.md     # Step 2: Resume rewrite + audit
├── 03_cover_letter.md                # Step 3: Cover letter
├── 99_completion_checklist.md        # Post-pipeline verification (lazy-loaded)
├── run_pipeline.sh                   # Bash-orchestrated wrapper (v3, ~920 lines)
├── extract_projects.py               # Condensed catalog + selected projects extraction
├── prompts/                          # Session prompt templates (reference docs)
│   ├── step1.md
│   ├── step2.md
│   ├── step3.md
│   └── score_boost.md
├── config.py                         # Location lookup, candidate info, SKILL_DIR
├── yaml_to_pdf.py                    # PDF compilation entry point
├── resume_parseability.py            # ATS parse-integrity audit
├── stamp_photo.py                    # Candidate photo stamping (LaTeX only)
├── sync_to_obsidian.py               # Obsidian sync entry point
├── check_watermarks.py               # AI watermark/provenance check
├── check_duplicate_application.py    # Duplicate application detection
├── track_outcomes.py                 # Outcome tracking
├── okf_diversity_audit.py            # Weekly diversity audit (standalone)
├── renderers/                        # 14 LaTeX + ReportLab renderers
├── okf/
│   ├── project_catalog.yaml          # 15-project catalog (49KB, source of truth)
│   ├── project_catalog_condensed.yaml # 15 projects without bullets (21KB, Step 1 input)
│   ├── base_files/                   # 5 English + 1 German base resumes
│   ├── .jd_cache/                    # JD URL cache (7-day TTL)
│   └── .location_cache.json          # Cached location lookups
├── tests/
│   ├── test_utils.py                 # Renderer utils tests
│   └── test_llm_search.py            # LLM ranking smoke test
├── docs/
│   ├── ARCHITECTURE.md               # Deep technical reference
│   └── CHANGELOG.md                  # Version history
└── requirements.txt
```

## Testing

```bash
.venv/bin/python tests/test_utils.py        # Renderer utils tests
.venv/bin/python tests/test_llm_search.py   # Catalog validation + ranking for 3 JD archetypes
```

## Documentation

| Document | Description |
|:---|:---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline flow, file inventory, design decisions |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [SKILL.md](SKILL.md) | Agent-facing skill metadata and execution rules |

## Self-Refresh

Type `llm-cv refresh` to reload the skill from ground truth. The agent copies `SKILL.md` to the CLI's skill store and ingests all supporting `.md` files (00-03, 99).
