# LLM-CV

ATS-optimized resume and cover letter tailoring pipeline. Paste a job description (or a URL) and get a tailored resume + cover letter as compiled PDFs, an archived JD, and an ATS score report.

## How It Works

The agent asks 4 configuration questions, then launches `run_pipeline.sh` in two stages. The pipeline makes 3 direct OpenRouter API calls via `api_pipeline.py` — no OMP sessions, no subagent spawning. A 10.5K-token static system prompt (step docs, golden examples, constraints) is sent with `cache_control` on every call, so OpenRouter caches the prefix at ~10x discount after the first call.

```
User says "llm-cv" + JD (URL, file, or pasted text)
    │
    ├── [if URL] Agent scrapes JD via firecrawl_scrape → saves to /tmp/llm-cv-jd.txt
    ├── Agent asks 4 questions (render mode, style, source, language)
    │
    ├── Stage 1: run_pipeline.sh --stage 1 --file /tmp/llm-cv-jd.txt ...
    │       │
    │       ├── Step 1 API call: ATS + JD archival + project ranking (reads 21KB condensed catalog)
    │       ├── [bash] Compile Step 1 PDFs + extract selected projects → selected_projects.yaml
    │       └── Prints APP_DIR, SKILL_GAPS, ATS_SCORE to stdout
    │
    ├── Agent reads SKILL_GAPS, asks user about keyword stuffing
    │
    └── Stage 2: run_pipeline.sh --stage 2 --app-dir ... --stuffing ... --force
            │
            ├── Step 2 API call: Resume writer + ATS rescoring (reads 7KB selected_projects.yaml)  ┐ parallel
            ├── Step 3 API call: Cover letter writer (reads project_info.md)                       ┘
            └── [bash] Compile all PDFs + fix loop + photo stamp + watermark check + Obsidian sync
```

3 API calls total (+ optional fix calls). Model: qwen/qwen3.8-flash with reasoning disabled. Cost: ~$0.01/run. Time: ~1-2 min/run.

## Quick Start

```bash
cd /home/sagar/Skills/llm-cv

# Interactive (prompts for all options)
./run_pipeline.sh --url "https://careers.forto.com/..."
./run_pipeline.sh "paste JD text here"
./run_pipeline.sh --file jd.txt

# Non-interactive — Stage 1 (agent mode)
./run_pipeline.sh --file /tmp/llm-cv-jd.txt \
    --render latex --style german --source "Cold Apply" --language English \
    --stage 1

# Non-interactive — Stage 2 (agent mode)
./run_pipeline.sh \
    --stage 2 --app-dir "/home/sagar/Applications/Company — Role" \
    --render latex --style german --language English \
    --stuffing none --score-boost yes --force
```

Outputs land in `/home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/`.

### CLI Flags

| Flag | Values | Default |
|:---|:---|:---|
| `--file` / `--url` / positional | JD source | required |
| `--stage` | `1` / `2` | full pipeline (no flag) |
| `--app-dir` | application folder path | required for stage 2 |
| `--render` | `latex` / `reportfallback` | `latex` |
| `--style` | `us` / `german` | `us` |
| `--source` | `Cold Apply` / `Referral` / `LinkedIn Connection` / `Direct` | `Cold Apply` |
| `--language` | `English` / `German` | auto-detect from JD |
| `--weak-tie` | Contact name/role | required if source is Referral/LinkedIn |
| `--stuffing` | `none` / `all` / `selective` | `none` |
| `--user-skills` | Skills to add (Selective) | required if stuffing=selective |
| `--score-boost` | `yes` / `no` | `yes` (always on) |
| `--force` | skip duplicate check prompt | required for non-interactive stage 2 |

## Prerequisites

- **Python 3.10+** with `pyyaml`, `reportlab`, `pypdf` (in `.venv/`)
- **TeX Live** (`pdflatex`) for LaTeX-mode PDFs
- **OpenRouter API key** stored in OMP's SQLite DB (`~/.omp/agent/agent.db`, table `auth_credentials`, provider `openrouter`)
- **Firecrawl MCP tool** available (for URL-based JD scraping)
- **Candidate photo** (`okf/SAGAR_MARTHANDAN_foto.jpg`) — stamped onto LaTeX-mode resume PDFs

```bash
uv venv .venv && uv pip install --python .venv/bin/python pyyaml reportlab pypdf
sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-lang-german
```

## Pipeline Steps

| Step | What happens | Outputs |
|:---|:---|:---|
| **0** (optional) | Agent scrapes JD from URL via Firecrawl MCP tool. Fallback: pipeline fetches via Jina Reader. | Clean JD text at `/tmp/llm-cv-jd.txt` |
| **1** | ATS scoring (4-category matrix, 0-100), archetype detection, LLM project ranking (15 → top 6 from condensed 21KB catalog), JD archival, location tailoring. Direct API call. | `ATS_Report.yaml/.pdf`, `Job_Description.yaml/.pdf`, `project_info.md` |
| **[bash]** | Compile Step 1 PDFs. Extract full project data for ranked projects via `extract_projects.py`. | `selected_projects.yaml` (~7KB) |
| **2** | Resume rewrite from `selected_projects.yaml` (7KB). Skill gap closure, keyword stuffing, 3-bullet project summaries with mandatory quantitative metrics. Post-rewrite ATS rescoring. Direct API call. | `Resume.yaml`, `SAGAR_MARTHANDAN_Resume.pdf` |
| **3** (parallel with 2) | Cover letter generation (DIN 5008 Form B for German, business letter for English), metric-grounded prose. Direct API call. | `Cover_Letter.yaml`, `SAGAR_MARTHANDAN_Cover_Letter.pdf` |
| **[bash]** | Compile resume (pdflatex x2 → stamp photo → parseability audit → watermark check). Compile cover letter. Fix loop if parseability fails. Obsidian sync + folder sort. | Final PDFs, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml/.pdf` |

## Direct API Architecture

`api_pipeline.py` makes 3 direct OpenRouter API calls. No OMP sessions, no subagent spawning. Python reads input files, builds one prompt per step, calls the API, parses YAML from the response, writes output files. Bash handles all parallelism, compilation, and coordination.

### Static-First Cache Architecture

A 10.5K-token `SYSTEM_PROMPT` is loaded once at module import via `_load_system_prompt()`. It contains:
- Full step docs (02_resume_and_visual_audit.md, 03_cover_letter.md)
- Score-boost measures (prompts/score_boost.md)
- Guardrails, resume constraints, German/US schema templates
- John Deere golden resume + cover letter as few-shot examples

Sent as system message with `cache_control: {"type": "ephemeral"}` in content array format. After the first call, OpenRouter caches the prefix at ~10x discount. Cache hits observed: 0% (cold) → 60% → 80% across a run.

Variable user message contains only JD, ATS report, config, task instructions — no guardrails or constraints (those are in the static system prompt).

### 2-Stage Pipeline Split

Keyword stuffing is asked AFTER Step 1 when skill gaps are known, not blind upfront. Stage 1 prints `APP_DIR`, `SKILL_GAPS`, `ATS_SCORE` to stdout. Agent reads these, asks user, then launches stage 2.

### Token consumption

| Mode | Per run | Cost | API calls | Notes |
|:---|:---|:---|:---|:---|
| Single-session (old) | ~8M | $0.13 | ~63 | Agent handles all steps in one conversation |
| Wrapper v2 (OMP sessions) | ~2M | $0.04 | ~29 | 3 OMP sessions + bash, CLI flags |
| **Direct API v4** | **~50K** | **~$0.01** | **3 + fix** | 3 OpenRouter calls + bash compilation. Prompt caching. |

### Compilation

`lib/compile.sh` (199 lines) contains all compilation functions, sourced by `run_pipeline.sh`:
- `compile_step1_pdfs()` — ATS_Report.pdf + Job_Description.pdf
- `compile_resume()` — tex → pdflatex x2 → stamp_photo → parseability → watermark
- `compile_cover_letter()` — yaml_to_pdf → watermark
- `generate_layout_audit()` — Layout_Audit_Report.yaml

## Page Fill Directive

Resumes must fill the ENTIRE text area between margins, top to bottom. The renderer uses 0.4in margins on A4. If content stops 15-20% short of the bottom margin, the resume looks unfinished. Fill the page by adding MORE CONTENT, not longer prose:

- 5-6 technical_skills categories (not 4) with 5-7 skills each
- 5th project from selected_projects.yaml if 4 projects leave visible empty space
- 5th-6th IBM bullet (max 105 chars) if still short
- NEVER extend bullet prose to fill space — long bullets are an eyesore for recruiters

Every project bullet must contain at least one quantitative metric (a number: %, count, latency, size, duration). A bullet without a number is a hard FAIL.

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

## AI Watermark Check

After every resume and cover letter compilation, `check_watermarks.py` scans the generated YAML and PDF files for AI provenance marks across three layers:

| Layer | What it checks |
|:---|:---|
| **A — Invisible Unicode** | Zero-width chars, bidi controls, tag characters, variation selectors, space homoglyphs in YAML text |
| **B — C2PA binary markers** | JUMBF, c2pa, contentcredentials in PDF non-stream data (stream-stripped to avoid false positives) |
| **C — PDF metadata** | XMP packets, AI vendor strings (Claude, Anthropic, OpenAI, SynthID, Content Credentials) |

Exit 0 = clean, exit 1 = marks found. Detection only — does not modify files.

## Score-Boost Mode

Score-boost is always on (`--score-boost yes`). Four measures (full detail in `prompts/score_boost.md`):

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
- **Non-interactive:** Pass `--force` to skip the interactive prompt (required for agent-launched stage 2)

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
├── api_pipeline.py                   # Direct OpenRouter API calls (3 steps + fix)
├── run_pipeline.sh                   # 2-stage bash orchestrator (615 lines)
├── lib/compile.sh                    # Compilation functions (199 lines, sourced)
├── extract_projects.py               # Condensed catalog + selected projects extraction
├── prompts/                          # Reference docs (score_boost.md etc.)
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
