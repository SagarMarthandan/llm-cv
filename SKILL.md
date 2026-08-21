---
name: llm-cv
description: >-
  Use when the user explicitly says "llm-cv" or "llm-cv refresh". LLM-based project ranking from a condensed catalog. Runs a 3-step pipeline: ATS analysis & JD archival, resume rewrite & layout audit, and cover letter generation. Trigger ONLY on the exact keywords "llm-cv" (to run the pipeline) and "llm-cv refresh" (to reload the skill from ground truth). Do NOT trigger on generic keywords like "resume", "cover letter", "ATS", "apply", "job description" — those are reserved for the llm-cv skill. When the user provides a URL instead of pasted JD text, an optional Step 0 (JD Fetch) scrapes the posting and hands the clean JD text to Step 1.
dependencies: python>=3.10, pyyaml, reportlab, pypdf, stop-slop
---

# LLM-CV Pipeline

## Read-Only Guardrail (Non-Negotiable)

> **Scope:** During pipeline execution, only read `SKILL.md`, the current step doc, and Python scripts they reference. Do NOT read `README.md`, `CHANGELOG.md`, or `docs/`.

**Read-only (never edit, patch, rename, or delete during a pipeline run):**
- All step docs (`SKILL.md`, `00_jd_fetch.md`, `01_*.md`, `02_*.md`, `03_*.md`, `99_completion_checklist.md`)
- All pipeline scripts (`config.py`, `yaml_to_pdf.py`, `resume_parseability.py`, `sync_to_obsidian.py`, `organize_applications.py`, etc.)
- The ENTIRE `renderers/` directory
- `okf/base_files/`, `okf/project_catalog.yaml`, `okf/project_mappings.yaml`, `okf/skill_mappings.yaml`
- `requirements.txt`, `.gitignore`, `llm-cv.code-workspace`

**Writable (freely edit, recompile, refine):** Only generated files inside `/home/sagar/Applications/[Company] — [Role]/` — `Resume.yaml`, `Resume.tex`/`SAGAR_MARTHANDAN_Resume.tex`/`SAGAR_MARTHANDAN_Lebenslauf.tex`, `Cover_Letter.yaml`, `Cover_Letter.tex`, all `.pdf` outputs, `ATS_Report.yaml`, `Job_Description.yaml`, `project_info.md`, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml`.

**The `.yaml` and `.tex` files in the application folder are the model's workspace. The skill infrastructure is the locked factory — do not touch. If a user request requires modifying skill files, refuse and explain they are read-only. This rule has no exceptions.**

## Pipeline Overview

Step 1: ATS analysis + JD archival + LLM project ranking → `ATS_Report.yaml`, `Job_Description.pdf`, `project_info.md`
Step 2: Resume rewrite + layout audit + parseability audit → `Resume.pdf`, `Layout_Audit_Report.yaml`, `Parseability_Report.pdf`
Step 3: Cover letter → `Cover_Letter.pdf`
Post: Obsidian sync + sort → moves folder to `/home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/`

- **Base Files:** `okf/base_files/english/` (archetype-specific: `resume_data_engineer.md`, `resume_data_analyst.md`, `resume_analytics_engineer.md`, `resume_ai_data_engineer.md`, `resume.md` fallback). German: same with `_de` suffix, `resume_de.md` fallback. Step 1 detects archetype and loads matching base.
- **Project Catalog:** `okf/project_catalog.yaml` — 15 projects with title, description, business_problem, key_metrics, transferable_skills, technologies, archetypes, repo_url, bullets, keywords. Single source of truth. `key_metrics` is authoritative — cite verbatim, never invent.
- **Python:** `/home/sagar/Skills/llm-cv/.venv/bin/python` — use this exact path verbatim. Dependencies: `pyyaml`, `reportlab`, `pypdf`. Do NOT run `pip install`.
- **Working Directory:** `/home/sagar/Applications/` (absolute path — never relative to agent CWD).
- **Key Scripts:** `yaml_to_pdf.py` (entry point), `resume_parseability.py` (ATS parse audit, auto-recovers via ReportFallback), `sync_to_obsidian.py` (Obsidian sync), `organize_applications.py` (date tree sort). Renderers in `renderers/` dispatch by `render_mode` + `resume_style`.

## General Writing & Style Rules (Stop-Slop)

To ensure all generated text sounds authentic and human, the pipeline step outputs (particularly resume bullet points and cover letter prose) must adhere to the **Stop-Slop** writing guidelines:
- **Core Principle:** Strictly eliminate predictable AI tells, structures, and rhythms.
- **Strict Active Voice:** Ensure every sentence leads with active human action. Avoid passive constructions.
- **Absolute Adverb Ban:** Do not use any adverbs ending in `-ly` or softening emphasis crutches (like *successfully*, *effectively*, *genuinely*, *actually*, *really*).
- **Zero Em-Dashes:** Punctuation em-dashes (`—`) are prohibited; use commas or periods.
- **No Throat-Clearing:** Start sentences directly. Cut preview/recap statements (e.g., *"at its core"*, *"it is worth noting"*, *"the reality is"*).


## YAML Safety Rules (Non-Negotiable)

JD text, resume content, and cover letter prose frequently contain characters that break YAML parsing (`: ` followed by space, leading `-`, `#`, unbalanced quotes, `>`/`|` at start of value). To prevent parse failures:

1. **Quote all string values** that could contain `:`, `-`, `#`, `>`, `|`, `{`, `}`, `[`, `]`, or quotes. Use double quotes: `company: "SAP SE"`.
2. **Use block scalars (`|`)** for multi-line content (JD overview paragraphs, bullet text, cover letter paragraphs):
   ```yaml
   content: |
     The data engineer will build and maintain pipelines...
   ```
3. **Never paste raw text directly into a YAML value without quoting or block-scaling it.** JDs, project summaries, and cover letter paragraphs almost always contain colons or dashes that will break parsing.
4. **After writing each YAML file**, validate it by running `/home/sagar/Skills/llm-cv/.venv/bin/python -c "import yaml; yaml.safe_load(open('FILENAME'))"` before proceeding to compilation. If it fails, fix the quoting and re-validate.
## Anti-Hallucination Principles (Pipeline-Wide, Non-Negotiable)

Fabricated content is an integrity violation, not a styling issue. These rules apply to every step and every output:

1. **Projects:** Only the 15 in `okf/project_catalog.yaml`. No inventing/splitting/merging/deriving. Every project must map 1:1 to a catalog entry by exact `title` match. A bare profile URL without a repo path is a hallucination red flag.
2. **Metrics:** From catalog `key_metrics` or base resume bullets only. No fabrication or "plausible estimates." Reframing existing metrics for JD context is allowed; inventing new numbers is not. If no metric exists, omit it.
3. **Technologies & Skills:** Only from catalog (`technologies`/`keywords`), base resume skills, or JD required skills. `skill_gaps` must contain only JD-explicitly-required skills. **User-Directed Carve-Out:** If the user chooses "Add all" or "Selective" in Step 2 keyword stuffing, adding those skills is a user directive, not fabrication. The guardrail remains enforced for all other aspects.
4. **Company & Role Facts:** Verbatim from JD. No paraphrasing or embellishing. Cover letter recipient address from JD text only; if no street address, use company name + city.
5. **Employment History:** Dates/titles from base resume are immutable. The "Independent Data Engineering & Professional Development" period (01/2023–04/2025) is self-directed learning, never production experience.
6. **Repo URLs:** Verbatim from catalog's `repo_url` field. No constructing or guessing. If empty (e.g., RACEYARD), omit the `[GitHub]` link entirely.

## Input Required

The user must provide:
1. **Job Description** — paste the full JD text (or a URL — see Step 0 for URL fetching)

## First Action: Select Pipeline Options

Ask the user **four** questions in a single `ask` call (all four as separate questions in the same batch). These selections configure the entire pipeline run:

| # | Setting | Header | Options |
|---|---------|--------|---------|
| 1 | Render mode | "Render mode" | `LaTeX` — pdflatex (primary; produces .tex + PDF; font is LMRoman10 via lmodern, no preamble patching) / `ReportFallback` — ReportLab (no .tex; use ONLY when pdflatex unavailable) |
| 2 | Resume style | "Resume style" | `US Style` — Summary→Skills→Projects→Experience→Education→Languages / `German Style` — Summary→Experience→Education→Skills→Languages (projects folded into experience as project_bullets under "Independent Data Engineering" entry ending Apr 2025; title is concrete role, never Architect/Lead/Manager) |
| 3 | Application source | "Application source" | `Cold Apply` / `Referral` (prompt for contact) / `LinkedIn Connection` (prompt for contact) / `Direct` |
| 4 | Language | "Language" | `English` (loads okf/base_files/english/) / `German` (loads okf/base_files/german/) |

> Language selection overrides JD language auto-detection. Useful for international roles at German companies.

### Storing the Selections

Write all four as top-level keys in the relevant YAML files:
- `render_mode: latex` or `render_mode: reportfallback` → `ATS_Report.yaml` (Step 1), `Resume.yaml` (Step 2), `Cover_Letter.yaml` (Step 3)
- `resume_style: us` or `resume_style: german` → `ATS_Report.yaml` (Step 1), `Resume.yaml` (Step 2)
- `application_source: "Cold Apply"` (or `Referral`, `LinkedIn Connection`, `Direct`) → `ATS_Report.yaml`
- `language: "English"` or `language: "German"` → `ATS_Report.yaml` (Step 1), `Resume.yaml` (Step 2), `Cover_Letter.yaml` (Step 3)

> **Session-split persistence:** Step 1 writes `render_mode`, `resume_style`, and `language` into `ATS_Report.yaml` so Step 2 and Step 3 sessions can read them from disk. Without this, a re-run of Step 2 or 3 without the wrapper script would lose these selections.

If `application_source` is `Referral` or `LinkedIn Connection`, prompt for `weak_tie_contact` (name/role) and store in `ATS_Report.yaml`.

Defaults if missing: `render_mode` → `latex`, `resume_style` → `us`, `language` → auto-detect from JD. `application_source` and `weak_tie_contact` flow through to `obsidian_sync_core.py`, `okf_diversity_audit.py`, and `track_outcomes.py` unchanged.

> **FONT RULE — HARD GUARDRAIL:** LaTeX mode renders in Latin Modern Roman 10 (`lmodern`). NEVER patch the `.tex` preamble to change fonts. A keyword miss is fixed by adjusting YAML wording, not fonts. Any memory lesson advising a Helvetica preamble patch is VOID.

## Second Action: Name the Session

Before executing any pipeline step, extract the **Company Name** and **Job Role/Position** from the JD and rename this session/conversation to `[Company Name] — [Job Role]`. This makes it easy to identify which agent is handling which application in the sidebar/session list when running multiple agents in parallel. Examples:
- `SAP — Senior Data Engineer`
- `Google Cloud — AI/ML Engineer`
- `Deutsche Bank — Analytics Engineer`

## Agent Execution Rules (Mandatory)

In agentic IDEs (Devin, Claude Code, Oh My Pi, etc.), emitting lengthy planning prose before a tool call triggers the system loop-guard interrupt — causing UI buffer clears (large blank vertical gaps) and forced tool-call retries. To prevent this:

1. **Tool-Call Priority:** NEVER output multi-paragraph planning prose, un-called YAML drafts, or consecutive Markdown headers in pure text without issuing a tool call. Every turn must perform concrete tool actions (`write`, `edit`, `exec`). Do not draft full YAML files or bullet lists in prose before writing them — write them directly with a `write` or `edit` call.
2. **Terse Action Commentary:** Limit reasoning prose before a tool call to 1 concise sentence describing the immediate action. Do not narrate the full plan, the full YAML structure, or the full bullet list before acting.
3. **Batch Tool Calls:** When multiple independent file writes or edits are needed, issue them in a single turn (parallel tool calls) rather than one-per-turn with prose between each.

These rules apply to ALL pipeline steps (0, 1, 2, 3) and all post-pipeline actions.

## Session Splitting (Token-Efficient Mode — Recommended)

For maximum token efficiency (~490K tokens/run vs ~2.5M single-session), run each step as a separate OMP session with clean context. Steps chain via disk files (YAML outputs).

**Wrapper script:** `run_pipeline.sh` in the skill directory orchestrates all 3 sessions:

```bash
cd /home/sagar/Skills/llm-cv
./run_pipeline.sh                          # interactive — prompts for JD
./run_pipeline.sh "paste JD text here"     # pass JD text directly
./run_pipeline.sh --url "https://..."      # fetch JD from URL (triggers Step 0)
./run_pipeline.sh --file jd.txt            # read JD from file
```

The script:
1. Collects First Action answers (render mode, style, source, language)
2. Launches Step 1 session (`omp -p --auto-approve`) → writes ATS_Report.yaml, Job_Description.yaml, project_info.md
3. Reads `skill_gaps` from ATS_Report.yaml, collects keyword stuffing decision
4. Launches Step 2 session → writes Resume.yaml, compiles resume, runs audits
5. Launches Step 3 session → writes Cover_Letter.yaml, compiles, runs Obsidian sync

Each session starts with a clean context — no accumulation from previous steps. The YAML schemas are the contract between steps. Prompt templates documented in `prompts/step1.md`, `prompts/step2.md`, `prompts/step3.md`.

**Single-session mode** (below) is still available for interactive use where the agent handles all steps in one conversation.


## Execution — Run All 3 Steps Sequentially
> **Lazy Loading:** Read only the step doc for the step you're executing. Do NOT read all step docs at once — each step doc is read on-demand when that step begins. This saves context tokens.


### STEP 0 (optional): JD Fetch — URL → Job Description Text

Run **only** when user provides a URL. Read `00_jd_fetch.md`. Fetches rendered page, extracts clean JD text, validates (role title + company + ≥2 section markers + >200 chars). JS-SPA vendors (LinkedIn, Workday, Greenhouse, Lever, SuccessFactors, Personio) → Jina Reader directly. Static/Unknown → `webfetch` first, Jina fallback. Manual paste is always the final fallback.

**Output:** Clean JD text + `source_url` + ATS vendor → handed to Step 1. Cache at `okf/.jd_cache/<sha1(url)>.txt` (7-day TTL).

---

### STEP 1: Setup, ATS Analysis & Job Description Archival

Read `01_ats_and_jd_archival.md`. Parses JD, scores base resume (4 categories × 25pts = 100; formatting is non-scored `formatting_quality` verdict), finds closest candidate city, ranks top 6 projects from `okf/project_catalog.yaml`. Score is informational — never blocks: `PROCEED` if ≥85, else `REVIEW` (Step 2 always proceeds).

**Output:** `ATS_Report.yaml`, `ATS_Report.pdf`, `Job_Description.yaml`, `Job_Description.pdf`, `project_info.md` in `[Company Name] — [Job Role]/` folder.

**Naming:** Folder MUST be `[Company Name] — [Job Role]` from JD. No arbitrary names.

---

### STEP 2: Resume Rewrite & Visual Layout Audit

Read `02_resume_and_visual_audit.md` for full instructions. Rewrites resume from ATS blueprint + project list. Compiles via LaTeX, layout audit, Stop-Slop check, post-rewrite ATS rescoring, parse-integrity audit (`resume_parseability.py`).

**Step 2 Hard Constraints (NON-NEGOTIABLE — enforce even if step doc not fully read):**
- **Project summaries:** Exactly 3 bullets per project, 180-240 chars EN / 160-220 DE, hard 3-line render limit. One outcome + metric per bullet. No padding, no tech-listing.
- **Technical skills:** JD-relevant only. Do NOT list every technology from every project. Prioritize JD-required skills → core project tools → adjacent strengths. Omit irrelevant technologies even if known.
- **Project tools field:** 3-5 most JD-relevant tools per project, not every technology from the catalog entry.
- **Section rule separation:** Never reduce `\titlespacing` after-sep below 4pt (renderer default `\titlespacing{\section}{0pt}{6pt}{4pt}`). Smaller gaps make the `\titlerule` merge with the first content line. Overflow → trim content or enlarge `\vspace`, never reduce after-sep.

**Output:** `Resume.yaml`, `Layout_Audit_Report.yaml`, `SAGAR_MARTHANDAN_Resume.pdf`/`Lebenslauf.pdf`, `Parseability_Report.yaml`, `Parseability_Report.pdf`.

---

### STEP 3: Cover Letter Generation & Compilation

Read `03_cover_letter.md`. Formal Geschäftsbrief cover letter grounded in project metrics, compiled to PDF.

**Output:** `Cover_Letter.yaml`, `SAGAR_MARTHANDAN_Cover_Letter.pdf`/`Anschreiben.pdf`.

---

## Post-Pipeline: Add One More Project

Follow `02_resume_and_visual_audit.md` §"Optional: Add One More Project". Pick next-ranked project from `project_info.md`, write in `name --- [GitHub] --- summary` format, insert into `Resume.yaml`, recompile, re-run parseability audit. Must stay on one page.

## Error Handling

1. Check stdout/stderr for PyYAML parser errors or ReportLab layout exceptions.
2. Verify YAML formatting (unquoted colons, incorrect indentations).
3. Layout overflow → trim text length in resume YAML.

## Completion Checklist

Read `99_completion_checklist.md` — run it only after all 3 steps complete. Do not read it during pipeline execution (it wastes context tokens).

## Pipeline Summary Output (MANDATORY — print at end of every run or change)

After every pipeline run, individual step completion, or ad-hoc resume change, print this summary block as the FINAL output. No exceptions. Read values from disk files (ATS_Report.yaml, Resume.yaml, Layout_Audit_Report.yaml, Parseability_Report.yaml) — do not guess.

```
╔══════════════════════════════════════════════════╗
║           PIPELINE FINISHED !!!                  ║
╠══════════════════════════════════════════════════╣
║  Company Name    - [from ATS_Report.yaml]        ║
║  Position        - [from ATS_Report.yaml]        ║
║  Folder Location - /home/sagar/Applications/...  ║
║  Delta           - [pre vs post ATS score delta] ║
║  Resume          - [OK or BAD: parseability +    ║
║                    layout audit verdict]          ║
║  Status          - [what was done this session]  ║
╚══════════════════════════════════════════════════╝
```

**Field rules:**
- **Company Name:** `company` key from `ATS_Report.yaml`.
- **Position:** `position` key from `ATS_Report.yaml`.
- **Folder Location:** Absolute path to the application folder.
- **Delta:** `score_delta` from `post_rewrite_ats_score` in `ATS_Report.yaml`. If Step 2 not run, omit or write "N/A".
- **Resume:** "OK" if parseability audit passed AND layout audit `page_fill_density` = Pass. "BAD" if either failed. Include one-line reason if BAD.
- **Status:** One sentence describing what was done. Examples: "Pipeline finished — all 3 steps completed." / "Step 2 completed — resume rewritten and compiled." / "Applied user changes — shortened project summaries, recompiled resume." / "Added one more project, recompiled, audit passed."

## Self-Refresh

When the user says "llm-cv refresh": locate ground truth `SKILL.md` (local `skills/llm-cv/SKILL.md` or GitHub `https://github.com/SagarMarthandan/llm-cv`), copy to active skill store, confirm load, then ingest all supporting `.md` docs (00-03, 99). Do not perform any other actions.
