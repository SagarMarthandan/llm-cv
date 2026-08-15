# Pipeline Step 1: ATS Check & Job Description Archival

> **READ-ONLY SKILL FILES — HARD GUARDRAIL:** The `renderers/` directory, all top-level pipeline scripts (`yaml_to_pdf.py`, `config.py`, `resume_parseability.py`, etc.), `okf/base_files/`, `okf/project_catalog.yaml`, and all pipeline step docs are **PERMANENTLY READ-ONLY** during this step. The model MUST NOT edit, patch, or modify any of these files. **The ONLY files the model writes in this step are** `ATS_Report.yaml`, `Job_Description.yaml`, `Job_Description.pdf`, and `project_info.md` (inside the current application folder). This rule has no exceptions.

> **AGENT EXECUTION RULES:** Follow the Tool-Call Execution Protocol in `SKILL.md` §"Agent Execution & Anti-Spinning Rules". Do not emit multi-paragraph planning prose or un-called YAML drafts before tool calls. Keep commentary to 1 sentence per action. Batch independent tool calls.

> **YAML SAFETY RULES (NON-NEGOTIABLE):**
>
> JD text and resume content frequently contain characters that break YAML parsing (`: ` followed by space, leading `-`, `#`, unbalanced quotes, `>`/`|` at start of value). To prevent parse failures:
>
> 1. **Quote all string values** that could contain `:`, `-`, `#`, `>`, `|`, `{`, `}`, `[`, `]`, or quotes. Use double quotes: `company: "SAP SE"`.
> 2. **Use block scalars (`|`)** for multi-line content (JD overview paragraphs, bullet text longer than one line):
>    ```yaml
>    content: |
>      The data engineer will build and maintain pipelines...
>    ```
> 3. **Never paste raw JD text directly into a YAML value without quoting or block-scaling it.** JDs almost always contain colons (e.g., "Requirements:") that will break parsing.
> 4. **After writing each YAML file**, validate it by running `/home/sagar/Skills/llm-cv/.venv/bin/python -c "import yaml; yaml.safe_load(open('FILENAME'))"` before proceeding to compilation. If it fails, fix the quoting and re-validate.

## Objective
Analyze the target job description (JD) against the candidate's base resume and project portfolio to detect gaps, classify the role archetype, calculate an ATS score, and structure the clean JD for archival.

## Inputs
- **Job Description (JD):** Paste target JD text at the bottom. The JD text may arrive from either (a) the user pasting it directly, or (b) Step 0 (JD Fetch) scraping it from a URL — in case (b), Step 0 also passes forward a `source_url` (string, optional) and the detected ATS vendor, which Step 1 should record in `Job_Description.yaml` (see §"Job_Description.yaml Schema") and reuse in §"0c. ATS Vendor Inference" without re-inferring. Step 1's behavior is otherwise identical for both input paths.
- **Base Resume & Portfolio:** Loaded from the local `okf/` folder inside the skill directory. Archetype-specific base resumes are selected based on the JD's role archetype (e.g. `okf/base_files/english/resume_data_engineer.md`, `okf/base_files/english/resume_data_analyst.md`, `okf/base_files/english/resume_analytics_engineer.md`, `okf/base_files/english/resume_ai_data_engineer.md`). Falls back to `okf/base_files/english/resume.md` for unmatched archetypes. German equivalents use `_de` suffix (e.g. `resume_data_engineer_de.md`).

## Execution Rules

### 0a. Name the Session
Per SKILL.md §"Name the Session" — extract Company Name and Job Role from the JD and rename this session to `[Company Name] — [Job Role]`.

### 0b. Pre-Scoring: Verify Dependencies & Load Base Files
Before any scoring or analysis, perform the following verification and loading steps:
1. **Python Environment (no action needed):** All pipeline dependencies are pre-installed in the project-local virtual environment at `/home/sagar/Skills/llm-cv/.venv/`. **All `python` commands in this pipeline MUST use the absolute path `/home/sagar/Skills/llm-cv/.venv/bin/python`** verbatim, regardless of the current working directory. Do NOT run `pip install` — the venv is already provisioned and gitignored. Dependencies: `pyyaml`, `reportlab`, `pypdf` (no embedding or vector DB dependencies needed).
2. **Load base resume:** Load the candidate's base resume from the detected language folder. The pipeline uses **archetype-specific base resumes** to maximize pre-rewrite ATS scores:
   - First, detect the JD's primary role archetype from the job title and description. The supported archetypes are:
     - `Data Engineer` → `resume_data_engineer.md`
     - `Data Analyst` → `resume_data_analyst.md`
     - `Analytics Engineer` → `resume_analytics_engineer.md`
     - `AI Data Engineer` → `resume_ai_data_engineer.md`
   - Load the matching archetype base resume from `okf/base_files/english/` (or `okf/base_files/german/` for German JDs — append `_de` to the filename, e.g. `resume_data_engineer_de.md`).
   - If the archetype doesn't match any of the 4 specific bases, fall back to the generic `resume.md` (or `resume_de.md` for German).
   *(Note: You do not need to load a global project_info.md file in Step 1, because the LLM ranking in Step 1 will dynamically generate a tailored project_info.md file inside the application folder).*

Do not proceed to scoring without first loading the base resume file. All gap analysis and keyword comparisons must reference the loaded resume content.

### 0c. ATS Vendor Inference & Application Source
Before scoring, gather monoculture-counter metadata:

1. **ATS Vendor Inference:** Scan the JD text and any target application URL for common ATS system footprints:
   - `myworkdayjobs.com` → `Workday`
   - `personio.de` / `personio.com` → `Personio`
   - `successfactors.eu` / `successfactors.com` → `SAP SuccessFactors`
   - `greenhouse.io` → `Greenhouse`
   - `lever.co` → `Lever`
   - `taleo.net` → `Taleo`
   - If none found, default to `Unknown`.
2. **Application Source Selection:** Prompt the user for the application source. Valid values: `Cold Apply`, `Referral`, `LinkedIn Connection`, `Direct`.
   - If the source is `Cold Apply` and the vendor is known (not `Unknown`), output a warning advising the user to check their network for weak ties before submitting.
   - If the source is `Referral` or `LinkedIn Connection`, prompt for the optional `weak_tie_contact` (name or role of the contact).

> **Note:** The diversity audit (`okf_diversity_audit.py`) is no longer run automatically per application. It is a standalone tool for weekly review — see `docs/ARCHITECTURE.md` §"Weekly Review: Diversity Audit". For per-application outcome and channel tracking, use `track_outcomes.py report` (see README).

### 1. Requirements & Archetype Detection
- Scan candidate-facing profile requirements.
- Classify the JD into exactly one primary role archetype (e.g., Data Engineering, Analytics Engineering, Data Analyst, AI Engineer, AI/LLMOps, Agentic/Automation, ML Engineering, Backend/Platform Engineering).
- Save selection and a one-sentence rationale under `role_archetype` in the YAML output.
- **Secondary archetype:** If the JD clearly spans two domains (e.g., requires both ML engineering and data platform work), assign a `secondary` archetype with its own one-sentence rationale. If the JD is focused on a single domain, omit the `secondary` field entirely.

### 2. German-Market ATS Scoring Matrix
- Grade the current resume against a German-market calibrated matrix (0-100 total) using **4 equally-weighted categories** (25 points each):
  - `keywords_and_terminology` (max 25)
  - `experience_relevance` (max 25)
  - `technical_skills` (max 25)
  - `soft_skills_and_language` (max 25)
- **Formatting is NOT scored.** Instead, emit a separate non-scored `formatting_quality` verdict (see below) that classifies the resume's formatting/parsability as one of `Excellent`, `Good`, `Average`, or `Bad`. If the verdict is `Average` or `Bad`, populate `suggestions` with concrete fixes. This keeps formatting feedback visible without diluting the 100-point score.
- Save category details and total score in `ats_score_matrix`, and the formatting verdict in `formatting_quality`, in the YAML output.
- **Score Flag (informational only, not a gate):** This 0-100 score is a self-assessment by the same model performing the rewrite, run against no external ATS system — it has no established correlation with real recruiter/interview outcomes and MUST NOT block or delay submission. If `total_score < 85`, set `score_gate_verdict: REVIEW` and populate `remedy_suggestions` as a structured list (see schema) so the user can see the specific weak points, but proceed to Step 2 regardless. If `>= 85`, set `score_gate_verdict: PROCEED`. Never halt the pipeline on this score alone.

### 3. Skill Gap Analysis (P2)
After scoring and project selection, extract a `skill_gaps` list:
- Extract a `required_skills` list from the JD — technologies, tools, and methodologies explicitly mentioned as required or strongly preferred.
- Collect `resume_skills` from the base resume's technical skills section and `project_skills` from the matched projects in `project_info.md` (technologies + keywords).
- Compute `skill_gaps = required_skills - (resume_skills ∪ project_skills)`.
- Store the result as a flat list of strings under `skill_gaps` in `ATS_Report.yaml`.
- The agent uses this list during Step 2 to make targeted additions where justified (add to skills section, weave into project descriptions, or note as genuine gaps).

> **ANTI-HALLUCINATION GUARDRAIL — Skill Gaps:** The `skill_gaps` list must contain ONLY skills/technologies explicitly mentioned in the JD text as required or strongly preferred. Do not add skills the model thinks "might be relevant" or "are commonly associated with this role." Every entry must be traceable to a specific phrase in the JD. If unsure whether a skill is required vs. merely mentioned, exclude it from `skill_gaps` (it will still appear in `keyword_inventory` if absent from the resume).

### 4. Contextual Placement Weighting (P4)
After the 4-category ATS score is computed, perform a contextual placement check on critical JD keywords:
- Extract the top critical keywords from the JD (the same keywords used in the `keywords_and_terminology` scoring category).
- For each keyword, check which sections of the base resume contain it: `skills`, `projects`, or `experience`.
- Apply a placement multiplier per keyword:
  - Found in skills section only: **1.0x**
  - Found in project summary only: **1.2x**
  - Found in experience bullet only: **1.3x**
  - Found in multiple sections: **1.5x**
  - Not found: omit from the list (already captured in `skill_gaps` or `keyword_inventory`)
- Store results under `placement_breakdown` in `ATS_Report.yaml`:
  ```yaml
  placement_breakdown:
    keywords:
      - keyword: "Kafka"
        sections_found: ["skills", "projects", "experience"]
        multiplier: 1.5
  ```
- This sub-report is informational — it does not change the 4-category score. It highlights where evidence-based keyword usage is strong (multiple sections) and where it is weak (skills section only).

### 5. Improvement Blueprint Generation
Populate each field of `improvement_blueprint` as follows:
- **`bullet_point_density_audit`:** For each bullet in the base resume's experience and projects sections, check if it contains a quantified metric (number, percentage, or time unit). List any bullets that are metric-free as items requiring quantification.
- **`project_swap_directive`:** Compare each project in the portfolio against the JD archetype. List projects that are misaligned under `remove_projects`. List archetype-aligned projects from `project_info.md` that are not currently in the base resume under `add_projects`, each with a one-sentence `justification`. Confirm exactly 3 (or 4 if score improves) are selected.
- **`keyword_inventory`:** Extract only JD keywords that are **absent from the base resume** (gap-only approach). Do not list keywords already present. Categorize absences into `hard_skills`, `methodologies`, and `domain_terms`.
- **`technical_skills_tuning`:** List tools/technologies to add (present in JD, absent from resume skills section) and to remove (present in resume skills section but irrelevant or distracting for this role).
- **`quantified_outcomes`:** For each metric-free bullet identified in the density audit, suggest a concrete revised version that adds a plausible quantified outcome.

> **ANTI-HALLUCINATION GUARDRAIL — Improvement Blueprint:**
>
> - **`project_swap_directive.add_projects`:** Every project name under `add_projects` MUST match a `title` in `okf/project_catalog.yaml` exactly. Do not suggest adding projects that don't exist in the catalog. The `justification` field explains why a real catalog project fits the JD, not why a fabricated project would.
> - **`quantified_outcomes.suggested`:** Suggested revisions must use metrics that are either (a) already present in the base resume bullet's source material, or (b) derivable from the project catalog bullets. Do not fabricate plausible-sounding numbers (e.g., "reduced latency by 40%") if no such metric exists in the source data. If no metric can be sourced, suggest a qualitative improvement instead (e.g., "add the specific tool name used" or "mention the data volume processed") rather than inventing a number.
> - **`technical_skills_tuning.add`:** Only list tools/technologies that appear in the JD AND are present in the project catalog or base resume. Do not suggest adding skills the candidate has never used.

### 6. Job Description Archival & Location Extraction
- Strip web tracking, cookies, duplicate fields, and metadata from the raw JD.
- Extract the job location from the raw JD (e.g., Munich, Berlin, Remote, etc.). Save it under a top-level `location` field in `Job_Description.yaml`.
- Structure into clean YAML sections (overview, requirements, responsibilities, stack) for permanent reference.

### 7. Candidate Location Selection
- The candidate has 4 candidate cities: **Kiel** (home), **Frankfurt**, **Berlin**, and **Köln**.
- **Static lookup + cache first:** Check the job location against the static geocode table and the persistent location cache in `config.py`. Run this Python one-liner to resolve:
  ```bash
  /home/sagar/Skills/llm-cv/.venv/bin/python -c "from config import nearest_candidate_city; print(nearest_candidate_city('[job_location]') or 'NOT_FOUND')"
  ```
  This checks the static `JOB_LOCATION_TO_CANDIDATE_CITY` table first, then falls back to `okf/.location_cache.json` (which stores locations previously resolved via web search). If either hits, no web search is needed.
- **Web search fallback:** If the lookup returns `NOT_FOUND`, use **web search** to determine which of the 4 cities is geographically nearest to the job location. Then cache the result so future applications with the same location skip the web search:
  ```bash
  /home/sagar/Skills/llm-cv/.venv/bin/python -c "from config import cache_location_result; cache_location_result('[job_location]', '[resolved_city, Germany]')"
  ```
- For remote, country-wide, or unspecified locations, default to **Kiel, Germany**.
- Save the result (e.g. `Frankfurt, Germany`) under `closest_candidate_location` in the root of `ATS_Report.yaml`.

## Output Target & Directory Structure
Create folder `/home/sagar/Applications/[Company Name] — [Job Role]/` and save three files:
- `ATS_Report.yaml`
- `Job_Description.yaml`
- `project_info.md` (tailored project portfolio generated via LLM ranking)

**Naming Convention:** Per SKILL.md — folder MUST be `/home/sagar/Applications/[Company Name] — [Job Role]/`. No arbitrary names or timestamps. Always use this absolute path — never create application folders relative to the agent's current working directory.

### A. `ATS_Report.yaml` Schema
```yaml
type: ats_report
company: "[Company Name]"      # Used by the PDF renderer for the report title
position: "[Job Position Title]"  # Used by the PDF renderer for the report subtitle
closest_candidate_location: "[Closest candidate location (Kiel, Frankfurt, Berlin, or Köln) determined via web search]"
ats_vendor: "[Inferred ATS vendor (Workday, Personio, SAP SuccessFactors, Greenhouse, Lever, Taleo, or Unknown)]"
application_source: "[Cold Apply, Referral, LinkedIn Connection, or Direct]"
weak_tie_contact: null  # Optional name/role of referral or LinkedIn contact
role_archetype:
  primary: "[Archetype Name]"
  secondary: "[Secondary Archetype — omit this field if JD is single-domain]"
  archetype_rationale: "[One sentence rationale for primary]"
  secondary_rationale: "[One sentence rationale for secondary — omit if secondary omitted]"
ats_score_matrix:
  keywords_and_terminology: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  experience_relevance: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  technical_skills: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  soft_skills_and_language: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  total_score: 0
formatting_quality:
  verdict: "Excellent"   # one of: Excellent | Good | Average | Bad
  notes: "[Optional one-line rationale]"
  suggestions: []        # Populate ONLY when verdict is Average or Bad
core_score_detractors: []
skill_gaps: []              # JD-required skills/technologies not present in base resume or matched projects
placement_breakdown:        # Contextual keyword placement weighting (P4)
  keywords: []
  # Each entry: { keyword: "...", sections_found: ["skills", "projects", "experience"], multiplier: 1.5 }
  # Multipliers: skills=1.0x, project summary=1.2x, experience bullet=1.3x, multiple sections=1.5x
improvement_blueprint:
  target_language_confirmation: "German/English"
  bullet_point_density_audit:
    - bullet: "[Exact bullet text from base resume]"
      issue: "No quantified metric"
  project_swap_directive:
    remove_projects: []
    add_projects: [{ name: "...", justification: "..." }]
    volume_constraint_check: "3 projects selected"
  keyword_inventory:
    hard_skills: []      # JD keywords absent from resume only
    methodologies: []    # JD methodologies absent from resume only
    domain_terms: []     # JD domain terms absent from resume only
  technical_skills_tuning:
    add: []
    remove: []
  quantified_outcomes:
    - original: "[Metric-free bullet]"
      suggested: "[Revised bullet with quantified outcome]"
  ats_threshold_calibration:
    meets_target: false
    score_gate_verdict: "REVIEW/PROCEED"
    remedy_suggestions:
      - "[Specific action: e.g., swap Project X for Project Y from portfolio]"
      - "[Specific action: e.g., add missing keyword 'dbt' to Technical Skills]"
      - "[Specific action: e.g., rewrite IBM bullet 3 to include a throughput metric]"
# post_rewrite_ats_score: populated by Step 2 only — do not fill during Step 1.
#   Includes: ats_score_matrix, score_delta, formatting_quality, score_gate_verdict, remaining_gaps
```

### B. `Job_Description.yaml` Schema
```yaml
type: job_description
company: "[Company Name]"
position: "[Job Position Title]"
location: "[Job Location — extracted from the job description]"
source_url: "[Optional — original job posting URL, populated when the JD arrived via Step 0 (JD Fetch). Omit this key entirely when the user pasted the JD manually.]"
sections:
  - title: "Core Role Overview & Context"
    content: "[Overview paragraph]"
  - title: "Target Profile Requirements"
    bullets:
      - "[Requirement]"
  - title: "Primary Responsibilities"
    bullets:
      - "[Responsibility]"
  - title: "Tech Stack & Tooling"
    bullets:
      - "[Tool/Skill]"
```

## LLM-Based Project Ranking & Compilation

After writing `ATS_Report.yaml` and `Job_Description.yaml`, generate the tailored project list and compile the PDFs:

### LLM-Based Project Ranking

Read `okf/project_catalog.yaml` (the condensed project catalog with 15 projects, each with 8-10 bullet points, keywords, technologies, archetypes, and repo URL).

> **ANTI-HALLUCINATION GUARDRAIL (NON-NEGOTIABLE):**
>
> You MUST select ONLY from the 15 projects listed in `okf/project_catalog.yaml`. You MUST NOT invent, create, derive, split, merge, or hallucinate new projects. Every project you rank must map 1:1 to an existing catalog entry by exact `title` match. Do not spin a bullet point or sub-aspect of one catalog project into a separate project — if two catalog projects share a theme (e.g., both involve Power BI + star schema), they are distinct entries but you must not fabricate a third derivative project from their overlapping aspects. The `repo_url` in your output MUST be the exact `repo_url` from the catalog entry — if you find yourself writing a bare profile URL like `https://github.com/SagarMarthandan` (without a specific repo path), you have hallucinated a project and must discard it immediately.

Rank the top 6 most relevant projects for this JD. Consider:
1. Direct technology/tool overlap with the JD
2. Transferable competencies (e.g. "data warehousing" transfers between BigQuery and Snowflake) — use each project's `transferable_skills` field as the primary signal here
3. Business-problem match — use each project's `business_problem` field to judge whether the project solves problems similar to the JD's responsibilities
4. Role archetype fit (data engineering vs BI vs AI vs analytics)
5. Project complexity and depth relevant to the role's seniority
6. Whether the project could be reframed for this role's seniority level

Write `project_info.md` in the application folder with the following format per project:

```markdown
# Tailored Project Portfolio

# [Project Title]
[Description from catalog]
Problem: [business_problem from catalog]
Tech: [technologies from catalog]
Archetypes: [archetypes from catalog]
Repo: [repo_url from catalog]
[First 2 bullets from catalog as context]
<!-- LLM Rank: [rank], Reason: [one sentence justification] -->
```

Repeat for all 6 ranked projects. Step 2 ignores HTML comments, so the `<!-- LLM Rank -->` line is transparent to the resume rewrite.

### Post-Ranking Validation (MANDATORY)

After writing `project_info.md`, verify every project title against the catalog:

```bash
/home/sagar/Skills/llm-cv/.venv/bin/python -c "
import yaml
with open('/home/sagar/Skills/llm-cv/okf/project_catalog.yaml') as f:
    catalog = {p['title'] for p in yaml.safe_load(f)['projects']}
print('Catalog projects:', len(catalog))
"
```

Cross-check each `# [Project Title]` heading in `project_info.md` against the catalog title set. If any title does not match exactly, you have hallucinated a project — remove it and replace it with the next-best real catalog project that was not already selected. Re-run this check until all 6 titles match catalog entries.

### Compilation Commands

```bash
cd "/home/sagar/Applications/[Company Name] — [Job Role]/"

# 1. Compile ATS Report
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf"

# 2. Compile Job Description
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "Job_Description.yaml" "Job_Description.pdf"
```

---
### ATTACHMENTS FOR PROCESSING
Paste the raw Job Description text below this line.
