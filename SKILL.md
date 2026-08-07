---
name: llm-cv
description: >-
  Use when the user explicitly says "llm-cv" or "llm-cv refresh". LLM-based project ranking from a condensed catalog. Runs a 3-step pipeline: ATS analysis & JD archival, resume rewrite & layout audit, and cover letter generation. Trigger ONLY on the exact keywords "llm-cv" (to run the pipeline) and "llm-cv refresh" (to reload the skill from ground truth). Do NOT trigger on generic keywords like "resume", "cover letter", "ATS", "apply", "job description" — those are reserved for the llm-cv skill. When the user provides a URL instead of pasted JD text, an optional Step 0 (JD Fetch) scrapes the posting and hands the clean JD text to Step 1.
dependencies: python>=3.10, pyyaml, reportlab, pypdf, stop-slop
---

# LLM-CV Pipeline

> **Scope note:** During pipeline execution, only read `SKILL.md`, `00_jd_fetch.md`, `01_ats_and_jd_archival.md`, `02_resume_and_visual_audit.md`, `03_cover_letter.md`, and the Python scripts they reference. Do NOT read `README.md`, `CHANGELOG.md`, or `docs/` — they are human documentation and consume context tokens without contributing to pipeline execution.

> **READ-ONLY SKILL FILES — HARD GUARDRAIL (NON-NEGOTIABLE):**
>
> The following files and directories are **PERMANENTLY READ-ONLY** during any pipeline run, resume generation, cover letter generation, or any user-requested modification to a resume, application, or generated output:
> - `SKILL.md`, `00_jd_fetch.md`, `01_ats_and_jd_archival.md`, `02_resume_and_visual_audit.md`, `03_cover_letter.md` — pipeline step docs
> - `config.py`, `yaml_to_pdf.py`, `resume_parseability.py`, `organize_applications.py`, `obsidian_sync_core.py`, `obsidian_folder_sort.py`, `sync_to_obsidian.py`, `track_outcomes.py`, `okf_diversity_audit.py` — top-level scripts
> - `renderers/` — the ENTIRE renderers directory (every `.py` file inside it, including `utils.py`, `resume_common.py`, `resume.py`, `resume_latex_us.py`, `resume_reportfallback_us.py`, `resume_latex_german.py`, `resume_reportfallback_german.py`, `cover_letter.py`, `cover_letter_latex.py`, `cover_letter_reportfallback.py`, `job_description.py`, `ats_report.py`, `parseability_report.py`)
> - `okf/base_files/` — base resume markdown files (english + german)
> - `okf/project_catalog.yaml` — condensed project catalog (16 projects with bullets, keywords, tech stack, archetypes, repo URL); read by the agent in Step 1 for LLM-based ranking
> - `okf/project_mappings.yaml`, `okf/skill_mappings.yaml` — Obsidian sync data files
> - `requirements.txt`, `.gitignore`, `llm-cv.code-workspace`
>
> **The model MUST NOT edit, modify, patch, rename, delete, or in any way alter any of these files during a pipeline run or when asked to tweak a resume.** These files define the pipeline infrastructure, renderers, and source-of-truth data. Modifying them during a run risks breaking the pipeline for all future applications.
>
> **The ONLY files the model is permitted to write during a pipeline run are the generated application outputs** inside the current `/home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/` folder — and these are **freely editable** (content, prose, structure, re-compilation):
> - `Resume.yaml` — the resume source (ReportFallback mode); edit freely for content, bullets, summary, skills, wording
> - `Resume.tex` / `SAGAR_MARTHANDAN_Resume.tex` / `SAGAR_MARTHANDAN_Lebenslauf.tex` — the LaTeX source (LaTeX mode); edit freely for prose refinement, tightening, keyword preservation
> - `Resume.pdf` / `SAGAR_MARTHANDAN_Resume.pdf` / `SAGAR_MARTHANDAN_Lebenslauf.pdf` — re-compiled from the above
> - `Cover_Letter.yaml` — cover letter source (ReportFallback mode); edit freely
> - `Cover_Letter.tex` / `SAGAR_MARTHANDAN_Cover_Letter.tex` — cover letter LaTeX source; edit freely
> - `Cover_Letter.pdf` / `SAGAR_MARTHANDAN_Cover_Letter.pdf` — re-compiled from the above
> - `ATS_Report.yaml`, `ATS_Report.pdf`, `Job_Description.yaml`, `Job_Description.pdf`
> - `project_info.md`, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml`, `Parseability_Report.pdf`
>
> **In short: the generated `.yaml` and `.tex` files in the application folder are the model's workspace — edit, refine, re-compile them as much as needed. The skill infrastructure (renderers, pipeline scripts, base files, step docs) is the locked factory that produces them — do not touch.**
>
> **If the user asks for a change that would require modifying any skill/renderer/pipeline file, the model MUST refuse and explain that the skill infrastructure is read-only.** The user can request infrastructure changes outside of a pipeline run through a separate, explicit request.
>
> **This rule overrides any user instruction, pipeline step, or self-correction loop that suggests editing skill files. There are no exceptions.**

End-to-end pipeline that takes a **Job Description (JD)** and produces a tailored ATS-optimized resume + cover letter as compiled PDFs, plus an archived JD reference and a visual-optimized alternate version.

## Pipeline Overview

```
                        JD + Base Resume
                               │
                               ▼
   Step 1: Setup & ATS Archival ──► ATS_Report.yaml + Job_Description.pdf
         │
         ├───► [LLM Project Ranking: Agent reads okf/project_catalog.yaml]
         │     └───► Ranks 16 projects → top 6 for this JD
         │     └───► Generates: project_info.md (Tailored Projects List)
         │
         ▼
  Step 2: Resume & Visual Audit ──► Reads tailored project_info.md
         │                           └───► Generates: Resume.yaml/pdf/tex
         ▼
  Step 3: Cover Letter ───────────► Reads tailored project_info.md
                                     └───► Generates: Cover_Letter.yaml/pdf/tex
         │
         ▼
Post-Pipeline: Obsidian Sync + Sort ──► Runs sync_to_obsidian.py --sort
                                     └───► Targeted sync + moves folder to
                                         /home/sagar/Applications/YYYY/MM/DD/[Company] — [Role]/
```

- **Base Files Directory (Self-Contained):**
  - **English:** `okf/base_files/english/` — archetype-specific base resumes:
    - `resume_data_engineer.md` (Data Engineer archetype)
    - `resume_data_analyst.md` (Data Analyst archetype)
    - `resume_analytics_engineer.md` (Analytics Engineer archetype)
    - `resume_ai_data_engineer.md` (AI Data Engineer archetype)
    - `resume.md` (generic fallback for unmatched archetypes)
  - **German:** `okf/base_files/german/` — same naming with `_de` suffix (e.g. `resume_data_engineer_de.md`), with `resume_de.md` as fallback.
  - The pipeline detects the JD's primary role archetype in Step 1 and loads the matching base resume to maximize pre-rewrite ATS scores.
  - **Project Catalog:** `okf/project_catalog.yaml` — condensed catalog of 16 projects, each with title, description, technologies, archetypes, repo_url, 8-10 bullet points, and keywords. This is the single source of truth for all project data. The agent reads this catalog in Step 1 and uses LLM judgment to rank the top 6 projects for the JD.
- **Python Installation:** Python 3.10+ with all dependencies pre-installed in a project-local virtual environment at `/home/sagar/Skills/llm-cv/.venv/`. **All pipeline scripts MUST be invoked with the venv Python binary** — do NOT use the system `python3`. The venv interpreter path is the absolute path `/home/sagar/Skills/llm-cv/.venv/bin/python` — use this exact path verbatim in every command, regardless of the current working directory. Dependencies: `pyyaml`, `reportlab`, `pypdf` (see [requirements.txt](file:///home/sagar/Skills/llm-cv/requirements.txt)). The venv is gitignored and already provisioned on this machine — do NOT run `pip install` during a pipeline run.
- **Working Directory:** `/home/sagar/Applications/` (absolute path — always create application folders here, never relative to the agent's CWD)
- **Pipeline Script Structure:**
  - `yaml_to_pdf.py` — entry point; routes YAML files to the correct renderer
  - `okf/project_catalog.yaml` — Condensed project catalog (16 projects with bullets, keywords, tech stack, archetypes, repo URL); read by the agent in Step 1 for LLM-based ranking
  - `sync_to_obsidian.py` — Syncs application data to Obsidian vault as linked notes for graph-view navigation (run after Step 3)
  - `renderers/utils.py` — shared utilities (`escape_latex`, color constants, `run_pdflatex`, font registration including Calibri)
  - `renderers/resume_common.py` — shared resume helpers (`HEADERS`, `get_resume_language`)
  - `renderers/resume.py` — Resume renderer dispatcher (reads `render_mode` + `resume_style`, routes to 4 renderer combinations)
  - `renderers/resume_latex_us.py` — Resume LaTeX renderer (US style) + parse-integrity audit
  - `renderers/resume_reportfallback_us.py` — Resume ReportLab renderer (US style, LM Roman 10 font)
  - `renderers/resume_latex_german.py` — Resume LaTeX renderer (German style: Lebenslauf section order)
  - `renderers/resume_reportfallback_german.py` — Resume ReportLab renderer (German style, LM Roman 10, same German section order)
  - `renderers/cover_letter.py` — Cover Letter renderer dispatcher (reads `render_mode`, routes to latex or reportfallback)
  - `renderers/cover_letter_latex.py` — Cover Letter LaTeX renderer
  - `renderers/cover_letter_reportfallback.py` — Cover Letter ReportLab renderer (LM Roman 10 font, same layout as LaTeX)
  - `renderers/job_description.py` — Job Description renderer (ReportLab only)
  - `renderers/ats_report.py` — ATS Report renderer (ReportLab only)
  - `renderers/parseability_report.py` — Parseability Report renderer (ReportLab only, LM Roman 10)
  - `resume_parseability.py` — ATS parse-integrity audit script; checks PDF text layer for unicode corruption, keyword recovery, section headers, and contact info extraction; outputs `Parseability_Report.yaml` + `Parseability_Report.pdf` (run after resume compilation in Step 2). If the audit fails, automatically re-compiles the resume with the ReportLab fallback renderer (style-aware) and re-audits. Use `--no-recovery` to disable.
  - `organize_applications.py` — Sorts application folders into a Year/Month/Date tree (run after Obsidian sync)

## General Writing & Style Rules (Stop-Slop)

To ensure all generated text sounds authentic and human, the pipeline step outputs (particularly resume bullet points and cover letter prose) must adhere to the **Stop-Slop** writing guidelines:
- **Core Principle:** Strictly eliminate predictable AI tells, structures, and rhythms.
- **Strict Active Voice:** Ensure every sentence leads with active human action. Avoid passive constructions.
- **Absolute Adverb Ban:** Do not use any adverbs ending in `-ly` or softening emphasis crutches (like *successfully*, *effectively*, *genuinely*, *actually*, *really*).
- **Zero Em-Dashes:** Punctuation em-dashes (`—`) are prohibited; use commas or periods.
- **No Throat-Clearing:** Start sentences directly. Cut preview/recap statements (e.g., *"at its core"*, *"it is worth noting"*, *"the reality is"*).

## Input Required

The user must provide:
1. **Job Description** — paste the full JD text
2. (Optional) **Language override** — if the user wants the output in a specific language different from the JD language

## First Action: Select Render Mode & Resume Style

Before executing any pipeline step, ask the user two questions:

### Question 1: Render Mode

Use the `ask_user_question` tool with a single-select question:

- **Question:** "Which render mode should the resume and cover letter use?"
- **Header:** "Render mode"
- **Options:**
  - `LaTeX` — Compile via pdflatex (primary). Produces a `.tex` source file alongside the PDF. Projects are rendered in `name --- [GitHub] --- summary` single-paragraph format directly by the renderer. The agent may optionally refine the prose post-compilation.
  - `ReportFallback` — Compile via ReportLab using the LM Roman 10 font (TTF version installed locally). No `.tex` file is produced. Projects are rendered in the same `name --- [GitHub] --- summary` single-paragraph format automatically. Use this when pdflatex is unavailable or when a LM Roman 10-styled PDF is preferred.

### Question 2: Resume Style

Use the `ask_user_question` tool with a single-select question:

- **Question:** "Which resume style should be used?"
- **Header:** "Resume style"
- **Options:**
  - `US Style` — US-convention section order: Summary → Technical Skills → Projects → Professional Experience → Education → Spoken Languages.
  - `German Style` — German Lebenslauf convention: Summary → Professional Experience → Education → Technical Skills → Spoken Languages. No separate Projects section — the 3 JD-aligned projects are folded into the Professional Experience section as `project_bullets` under an "Independent Data Engineering & Professional Development" entry (rendered in `name --- [GitHub] --- summary` format with quantified metrics), plus a 4th plain-text bullet for other skills/tools. The entry date ends at April 2025 (candidate is now studying economics). The title uses a concrete role (e.g., `Data Engineer`, `Analytics Engineer`) — never `Architect`/`Lead`/`Manager`. Required for German market applications.

### Storing the Selections

Both selections MUST be written as top-level keys in `Resume.yaml` and `Cover_Letter.yaml`:
- LaTeX → `render_mode: latex`
- ReportFallback → `render_mode: reportfallback`
- US Style → `resume_style: us`
- German Style → `resume_style: german`

The renderers read these keys and dispatch accordingly. If `render_mode` is missing, `latex` is assumed. If `resume_style` is missing, `us` is assumed (backward compatible). Both choices apply to the resume for this application.

## Second Action: Name the Session

Before executing any pipeline step, extract the **Company Name** and **Job Role/Position** from the JD and rename this session/conversation to `[Company Name] — [Job Role]`. This makes it easy to identify which agent is handling which application in the sidebar/session list when running multiple agents in parallel. Examples:
- `SAP — Senior Data Engineer`
- `Google Cloud — AI/ML Engineer`
- `Deutsche Bank — Analytics Engineer`

## Agent Execution & Anti-Spinning Rules (Mandatory)

In agentic IDEs (Devin, Claude Code, Oh My Pi, etc.), emitting lengthy planning prose before a tool call triggers the system loop-guard interrupt — causing UI buffer clears (large blank vertical gaps) and forced tool-call retries. To prevent this:

1. **Tool-Call Priority:** NEVER output multi-paragraph planning prose, un-called YAML drafts, or consecutive Markdown headers in pure text without issuing a tool call. Every turn must perform concrete tool actions (`write`, `edit`, `exec`). Do not draft full YAML files or bullet lists in prose before writing them — write them directly with a `write` or `edit` call.
2. **Terse Action Commentary:** Limit reasoning prose before a tool call to 1 concise sentence describing the immediate action. Do not narrate the full plan, the full YAML structure, or the full bullet list before acting.
3. **Batch Tool Calls:** When multiple independent file writes or edits are needed, issue them in a single turn (parallel tool calls) rather than one-per-turn with prose between each.

These rules apply to ALL pipeline steps (0, 1, 2, 3) and all post-pipeline actions.

## Execution — Run All 3 Steps Sequentially

### STEP 0 (optional): JD Fetch — URL → Job Description Text

Run Step 0 **only** when the user provides a job posting URL (or asks to "scrape this posting" / "fetch this job link") instead of pasting raw JD text. If the user pastes raw JD text directly, **skip Step 0** and go straight to Step 1.

Read and execute the full instructions in [00_jd_fetch.md](file:///home/sagar/Skills/llm-cv/00_jd_fetch.md).

Fetches the rendered job posting from the URL, extracts the clean JD text, validates it against a JD-shape heuristic (role title + company + ≥2 JD section markers + >200 chars + not a login/error page), and hands the text to Step 1. Strategy routing: known JS-SPA vendors (LinkedIn, Workday, Greenhouse, Lever, SuccessFactors, Personio) go straight to Jina Reader (`https://r.jina.ai/<url>`) and skip the doomed local `webfetch` attempt; static / Unknown vendors try `webfetch` first then Jina. If both strategies fail (rate limit, login wall, failed validation), the user is prompted to paste the JD manually — manual paste is always available as the final fallback and is never locked out.

**Output:** Clean JD text (handed to Step 1 as the "pasted JD text" input — Step 1's contract is unchanged), plus `source_url` and detected ATS vendor passed forward to Step 1. Cache entries are written to `okf/.jd_cache/<sha1(url)>.txt` (7-day TTL) for re-runs of the same URL.

---

### STEP 1: Setup, ATS Analysis & Job Description Archival

Read and execute the full instructions in [01_ats_and_jd_archival.md](file:///home/sagar/Skills/llm-cv/01_ats_and_jd_archival.md).

Parses and archives the job description, scores the base resume, performs location tailoring via web search to find the closest candidate city, and generates a tailored project list using LLM-based project ranking (the agent reads `okf/project_catalog.yaml` and ranks the top 6 projects for the JD using its own judgment).

**ATS Scoring Model:** 4 equally-weighted categories of 25 points each (total = 100) — Keywords & Terminology, Experience Relevance, Technical Skills, Soft Skills & Language. Formatting is **not scored**; instead a non-scored `formatting_quality` verdict (`Excellent` / `Good` / `Average` / `Bad`) is emitted with suggested changes when `Average` or `Bad`. This score is informational only (self-graded, no measured correlation with real interview outcomes) — it never blocks the pipeline: `PROCEED` if total >= 85, else `REVIEW` (with `remedy_suggestions` populated for visibility, but Step 2 always proceeds).

**Output:** `ATS_Report.yaml`, `ATS_Report.pdf`, `Job_Description.yaml`, `Job_Description.pdf`, and `project_info.md` in `[Company Name] — [Job Role]/` folder.

**Naming Convention (Critical):** The application folder and session name MUST be `[Company Name] — [Job Role]` extracted from the JD. No arbitrary names or timestamps. See `01_ats_and_jd_archival.md` for details.

---

### STEP 2: Resume Rewrite & Visual Layout Audit

Read and execute the full instructions in [02_resume_and_visual_audit.md](file:///home/sagar/Skills/llm-cv/02_resume_and_visual_audit.md).

Rewrites the resume based on the ATS Improvement Blueprint and the tailored project list. Compiles the resume via LaTeX, performs a visual layout audit and Stop-Slop check, updates the post-rewrite ATS score, and runs the parse-integrity audit (`resume_parseability.py`) to verify the PDF text layer is ATS-parseable.

**Output:** `Resume.yaml`, `Layout_Audit_Report.yaml`, `SAGAR_MARTHANDAN_Resume.pdf` / `SAGAR_MARTHANDAN_Lebenslauf.pdf` (and `Resume_v2.pdf` / `Lebenslauf_v2.pdf` if needed), `Parseability_Report.yaml`, and `Parseability_Report.pdf`.

---

### STEP 3: Cover Letter Generation & Compilation

Read and execute the full instructions in [03_cover_letter.md](file:///home/sagar/Skills/llm-cv/03_cover_letter.md).

Generates a formal, metric-grounded cover letter standard conforming to German Geschäftsbrief layout in the target JD language.

**Output:** `Cover_Letter.yaml` and `SAGAR_MARTHANDAN_Cover_Letter.pdf` / `SAGAR_MARTHANDAN_Anschreiben.pdf`.

---

## Post-Pipeline: Add One More Project

After the pipeline completes, the user may ask to add an additional project to the resume (e.g., "add a 4th project", "add one more project"). Follow the procedure in [02_resume_and_visual_audit.md §"Optional: Add One More Project"](file:///home/sagar/Skills/llm-cv/02_resume_and_visual_audit.md).

Summary: pick the next-ranked project from `project_info.md`, write it in the same `name --- [GitHub] --- summary` format, insert into `Resume.yaml` (`projects` list for US style, `project_bullets` for German style), recompile, and re-run the parse-integrity audit. If the resume spills to 2 pages, trim or swap a weaker project.

---

## Error Handling

If the compilation fails:
1. Check stdout/stderr console logs for PyYAML parser errors or ReportLab layout exceptions.
2. Verify YAML formatting is correct (e.g. check for unquoted colons, incorrect indentations).
3. If there's a layout overflow, trim the text length in the resume YAML.

## Completion Checklist

After all 3 steps complete, verify:
- [ ] `ATS_Report.yaml` exists in the company folder with pre and post rewrite scores, including `closest_candidate_location`
- [ ] `ATS_Report.pdf` is generated and `post_rewrite_ats_score` block is populated
- [ ] `ATS_Report.yaml` contains a non-scored `formatting_quality` verdict (pre- and post-rewrite) with `suggestions` populated only if verdict is `Average` or `Bad`
- [ ] `Job_Description.yaml` (with `location` key) & `Job_Description.pdf` are generated
- [ ] `project_info.md` (tailored project list) is generated in the company folder
- [ ] `Resume.yaml` & `SAGAR_MARTHANDAN_Resume.pdf` / `SAGAR_MARTHANDAN_Lebenslauf.pdf` are generated with the tailored closest location
- [ ] `SAGAR_MARTHANDAN_Resume.tex` / `SAGAR_MARTHANDAN_Lebenslauf.tex` & `SAGAR_MARTHANDAN_Cover_Letter.tex` / `SAGAR_MARTHANDAN_Anschreiben.tex` are preserved in the folder
- [ ] `Layout_Audit_Report.yaml` is generated with all eye-test diagnostics at Pass status
- [ ] `Parseability_Report.yaml` & `Parseability_Report.pdf` are generated with overall status PASS (100% keyword recovery, all section headers detected, 5/5 contact fields, no unicode corruptions)
- [ ] `Cover_Letter.yaml` & `SAGAR_MARTHANDAN_Cover_Letter.pdf` / `SAGAR_MARTHANDAN_Anschreiben.pdf` are generated with the tailored closest location in the sender address and date fields
- [ ] Professional Experience bullets are single-line, <= 105 chars (per 02 §Layout Constraints)
- [ ] Projects in `name --- [GitHub] --- summary` format, summary <= 300 chars (<= 280 German), <= 3 lines (per 02 §Layout Constraints)
- [ ] Summary is exactly 2 lines, <= 200 chars (<= 170 German) (per 02 §Layout Constraints) — STRICT, no compromise
- [ ] Cover letter fits one page, 250–320 words (180–240 German) (per 03 §Structure)
- [ ] All files match the target JD language and comply with the Stop-Slop guidelines
- [ ] `sync_to_obsidian.py` has synced the application to the Obsidian vault (check `<vault>/Job Search/` for notes)
- [ ] `sync_to_obsidian.py --sort` has moved the folder into `/home/sagar/Applications/YYYY/MM/DD/[Company Name] — [Job Role]/`

## Self-Refresh

When the user says "llm-cv refresh" or similar:

1. **Identify this CLI/harness.** Determine what CLI environment you're running under (Devin, Claude Code, agy, opencode, etc.) and its skill/workflows directory location.

2. **Locate the ground truth `SKILL.md`.** First check `skills/llm-cv/SKILL.md` on the local filesystem. If that file is missing, unreadable, or appears stale, pull the latest version directly from the GitHub repository at **https://github.com/SagarMarthandan/llm-cv** (path: `skills/llm-cv/SKILL.md`) via `webfetch` or `git pull` — that GitHub repo is the canonical source of truth and may be used as a fallback whenever local ground truth files are not available.

3. **Copy `SKILL.md`** from the located ground truth (local or GitHub) to this CLI's active skill store path.

4. **Confirm the load** via this CLI's skill resolution mechanism (e.g. `skill://llm-cv` if supported, otherwise by reading back the destination file).

5. **Ingest all supporting docs** — read every `.md` file in `skills/llm-cv/` (the step files 00_*.md, 01_*.md, 02_*.md, 03_*.md, and any others) to load the full pipeline into context. If any supporting doc is missing locally, fetch it from **https://github.com/SagarMarthandan/llm-cv** using the same fallback as step 2.

Do not perform any other actions.
