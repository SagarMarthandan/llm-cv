# Pipeline Step 2: Resume Rewrite & Visual Layout Audit

> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules", §"Anti-Hallucination Principles". Only write to the application folder: `Resume.yaml`, `Resume.tex` / `SAGAR_MARTHANDAN_Resume.tex` / `SAGAR_MARTHANDAN_Lebenslauf.tex`, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml`, `Parseability_Report.pdf`.

## Objective
Generate a tailored resume (`Resume.yaml`) from Step 1's `ATS_Report.yaml`, audit layout, self-correct, and re-score ATS.

## Inputs
- **Base Resume:** `okf/base_files/english/resume.md` or `okf/base_files/german/resume_de.md` (per `language` key in `ATS_Report.yaml`)
- **Project Portfolio:** `project_info.md` in the company folder (from Step 1 LLM ranking)
- **ATS Report:** `ATS_Report.yaml` from the company folder — read `render_mode`, `resume_style`, `language`, `skill_gaps`, `improvement_blueprint`, `role_archetype`, `closest_candidate_location` from here. Use archived `Job_Description.yaml` for JD references — do not re-paste raw JD.

## First Action: Keyword Stuffing Decision

Present `skill_gaps` from `ATS_Report.yaml` and ask one question via `ask`:

- **Q1** "Step 1 found these skill gaps: [list]. How do you want to handle them?" — Header: "Keyword stuffing"
  - `Add all` — Add every `skill_gaps` skill to technical skills (user directive, anti-hallucination waived per SKILL.md §3)
  - `No stuffing` — Only add skills candidate genuinely knows (catalog/base resume)
  - `Selective` — User specifies which skills to add
- **Q2** (only if Selective) "Which skills to add?" — Header: "Skills to add" — free text

Store in `Resume.yaml`:
```yaml
keyword_stuffing: true    # true if Add all or Selective, false if No stuffing
user_directed_skills: []  # populated only if Selective
```

## 1. Document Rewrite & Project Selection

- **Archetype alignment:** Bias project order/phrasing toward archetype from Step 1.
- **Skill gap closure:** Apply per `keyword_stuffing` decision:
  - `Add all`: Add all `skill_gaps` to technical skills (user directive).
  - `Selective`: Add only `user_directed_skills` + genuine skills from `skill_gaps`.
  - `No stuffing`: Add only genuine skills (catalog/base resume). Note real gaps without fabricating.
- **Technical skills selection (ANTI-STUFFING):** Include only skills the candidate genuinely knows that are relevant to this JD. Do NOT list every technology from every project. Prioritize: (1) JD-required skills the candidate has, (2) core tools from selected projects, (3) adjacent skills that strengthen the profile. Omit irrelevant technologies even if known. A focused, credible skills block reads better than an exhaustive inventory that looks like ATS keyword stuffing.
- **Project tools:** List only the 3-5 most JD-relevant tools used in that project, not every technology from the catalog entry. Irrelevant tools dilute the signal.
- **Language:** Translate fully to user-selected language (not auto-detected). Set `language` key in `Resume.yaml`.
- **Location:** Read `closest_candidate_location` from `ATS_Report.yaml`, set as `contact_info.location`.
- **Employment dates:** Copy exactly from base resume. Never generalize or omit.
- **Project URLs:** Copy `repo_url` verbatim from `Repo:` line in `project_info.md`. If empty, omit `[GitHub]` link.
- **Resume variation:** Set `resume_variation` in `Resume.yaml`:
  - `Balanced` (default): 3 projects, 4 experience bullets
  - `Project-Heavy`: 4 projects with verbose descriptions, simplified skills
  - `Skills-Heavy`: 3 projects, expanded technical skills
- **Section order:**
  - **US Style** (`resume_style: us`): Summary → Technical Skills → Projects → Professional Experience → Education → Spoken Languages
  - **German Style** (`resume_style: german`): Summary → Professional Experience → Education → Technical Skills → Spoken Languages

> **ANTI-HALLUCINATION — Project Sourcing:** Every project must come from `project_info.md` (sourced from `okf/project_catalog.yaml`). No inventing/splitting/merging. `name` must match `project_info.md` exactly. `repo_url` verbatim from `Repo:` line. Metrics from catalog `key_metrics` only — reframe for JD context, never invent.

### German Style — Independent Data Engineering Entry
Projects are NOT a separate section. They're `project_bullets` under a special experience entry:
```yaml
- company: "Independent Data Engineering & Professional Development"
  date: "Jan 2023 – April 2025"
  title: "Data Engineer"  # concrete role, never Architect/Lead/Manager
  project_bullets:
    - name: "[Project Title]"
      repo_url: "[from project_info.md]"
      bullets:
        - "[Summary with quantified metrics]"
  bullets:
    - "Also worked with [additional technologies] during this period."
```
- Date MUST end at April 2025 (candidate is now studying economics). Start: Jan 2023.
- Title: concrete role (Data Engineer, Analytics Engineer, etc.). Never Architect/Lead/Manager/Remote.
- First 3 `project_bullets` = JD-aligned projects from `project_info.md`. Each must include quantified metrics.
- `bullets` list = single "other tools" bullet after project bullets.

## 2. Structural & Layout Constraints

Resume MUST fill exactly ONE full A4 page — no empty space at bottom, no spill to page 2. Half-empty = FAIL.

| Element | English | German |
|---------|---------|--------|
| Summary | 2 lines, ≤200 chars | 2 lines, ≤170 chars |
| Project summary | exactly 3 lines, 180-240 chars | exactly 3 lines, 160-220 chars |
| Experience bullets | ≤105 chars, 1 line each | same |
| IBM bullets | exactly 4 | exactly 4 |
| Staff 4 bullets | exactly 2 | exactly 2 |
| Project name+tools | ≤120 chars | ≤120 chars |

- **Filenames:** English → `SAGAR_MARTHANDAN_Resume.pdf`/`.tex`. German → `SAGAR_MARTHANDAN_Lebenslauf.pdf`/`.tex`.
- **Summary:** No tool-listing (tools go in Technical Skills). Positioning statement: who you are + what you do + outcome. Must NOT lead with standalone year-count tied to IBM. IBM (08/2014–12/2018) = only professional production experience, stated as background credential. Independent period (01/2023–04/2025) = self-directed learning, never "production experience."
- **Projects:** Select best 3-4 from 6 in `project_info.md`. Format: `name --- [GitHub] --- summary` (single paragraph, renderer joins bullets into prose). Name/em-dashes/link excluded from char count. Write exactly 3 bullets per project targeting 180-240 chars (160-220 German). Hard limit: 3 rendered lines, no more. Each bullet: one outcome + its key metric. No padding, no tech-listing (tools go in the `tools` field and Technical Skills section).
- **Render mode:** `latex` (default) or `reportfallback`. ReportFallback skips §4 and Steps B/C — single compile produces final PDF.

## 2.5 Space-Fill Directive (MANDATORY — One Full Page)

After initial compilation, resume MUST be full: content reaches bottom margin, ≤1 line trailing whitespace, no page-2 spill. If under-filled:

0. **Maximize character budgets first** (zero-risk): Summary → 200/170 chars. Projects → 180-240/160-220 chars. Experience bullets → 100-105 chars.
1. **Add technical skills** from `skill_gaps` (respect `keyword_stuffing` decision).
2. **Add one more project** from `project_info.md` (next-ranked, not already in resume). Same format, 3 bullets, 180-240 chars.
3. **Re-compile and re-audit.** Target: bottom margin reached, ≤1 line trailing whitespace, no gaps >2 empty lines, exactly 1 page. If overflow → trim or swap weaker project.
4. **Verify fullness on final PDF.** Last text line within bottom ~10% of page. If not, iterate 0-3.

> **ANTI-HALLUCINATION — Space-Fill:** Projects from `project_info.md` only. Skills from `skill_gaps` (if `keyword_stuffing: false`, only genuine skills). No inventing projects or skills to fill space.

## 3. Visual Layout Audit & Stop-Slop Checks

- Apply **Stop-Slop** per SKILL.md §"Stop-Slop".
- **Tools-Line Deduplication:** No bullet that just names a header tool. Reinforcement allowed only with added action/outcome. Keep tools lines to 3-5 JD-aligned entries.
- **Orphan Punctuation:** Verify no orphan periods, double periods, spaces before punctuation. Run `--check-tex` and scan PDF.
- **Page Fill Density (MANDATORY):** (a) exactly 1 page, (b) last line within bottom ~10%, (c) no internal gap >2 empty lines. Report as `page_fill_density` in `Layout_Audit_Report.yaml`.
- **Self-Correction:** If violations, immediately adjust text parameters. v2 only if >3 bullets changed or entire section restructured.
- Write findings to `Layout_Audit_Report.yaml`.

## 4. LaTeX Project Format Polish (Post-Processing)

Renderer produces `name --- [GitHub] --- summary` directly from YAML bullets. Optional prose refinement on generated `.tex`:

1. No bullet points — renderer already joins into prose. Don't reintroduce `\begin{itemize}`.
2. No separate "Tools:" line — weave tools into description prose.
3. Keep `name --- [GitHub] --- summary` structure. Name/separators/link excluded from char count.
4. Quantification: every project needs ≥1 metric from catalog `key_metrics` (verbatim or reframed). If none exists, omit rather than fabricate.
5. Length: 180-240 chars (160-220 German), exactly 3 lines. No exceptions.
6. Keyword preservation: all tools/technologies from YAML bullets must appear in prose.
7. Active voice. No adverbs ending in `-ly`. No em-dashes except `---` separators.

## 5. Post-Rewrite ATS Rescoring

- Re-run 4-category ATS matrix (25pts each, 100 total) on final polished resume.
- Re-issue `formatting_quality` verdict. Calculate `score_delta`.
- Update `post_rewrite_ats_score` block in existing `ATS_Report.yaml` (do NOT overwrite pre-rewrite section).
- Surface score delta to user. ATS_Report.pdf recompile happens in Step C.

## 6. Resume Parseability Audit (Mandatory Post-Compilation)

Run after final resume PDF is compiled:
```bash
cd "/home/sagar/Applications/[Company Name] — [Job Role]/"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/resume_parseability.py" "SAGAR_MARTHANDAN_Resume.pdf" "Resume.yaml"
# German: substitute "SAGAR_MARTHANDAN_Lebenslauf.pdf"
```

**Checks:** Unicode integrity (zero replacement glyphs), keyword recovery (100% from YAML), section headers (6 US / 5 German), contact info (5/5), text structure.

**Pass:** All checks pass. **Auto-recovery:** If fail, script re-compiles with ReportFallback renderer and re-audits. Use `--no-recovery` to debug manually.

> **FONT RULE:** Keyword misses are YAML wording problems, NOT font problems. Fix by de-parenthesizing, splitting strings, removing special characters. NEVER patch `.tex` preamble fonts (see SKILL.md §Font Rule).

## 7. Post-Generation Anti-Hallucination Validation (MANDATORY)

After writing `Resume.yaml`, before final compilation:
```bash
/home/sagar/Skills/llm-cv/.venv/bin/python -c "
import yaml
with open('/home/sagar/Skills/llm-cv/okf/project_catalog.yaml') as f:
    catalog = {p['title'] for p in yaml.safe_load(f)['projects']}
with open('Resume.yaml') as f:
    resume = yaml.safe_load(f)
names = [p['name'] for p in resume.get('projects', [])]
for exp in resume.get('professional_experience', []):
    names += [pb['name'] for pb in exp.get('project_bullets', [])]
for n in names:
    print(f'  [{\"OK\" if n in catalog else \"HALLUCINATED\"}] {n}')
"
```
If any name doesn't match catalog exactly → replace with real catalog project. Re-run until all match.

## Optional: Add One More Project

1. Read `project_info.md` — pick next-ranked project not already in resume. If user names a specific project, use it (must exist in catalog).
2. Write single-paragraph: `name --- [GitHub] --- summary` (180-240 chars / 160-220 German, ≥1 metric, 3 lines max).
3. Insert: US style → `projects` list. German style → `project_bullets` under Independent Data Engineering entry.
4. Recompile + re-run parseability audit. Must stay on one page.

## Output Schemas

### A. `Layout_Audit_Report.yaml`
```yaml
type: layout_audit_report
eye_test_diagnostics:
  page_fill_density: { status: "Pass/Fail", feedback: "Exactly 1 page, no trailing whitespace, no page-2 spill. Fail = under-filled page." }
  page_boundary_splits: { status: "Pass/Fail", feedback: "..." }
  summary_cognitive_load: { status: "Pass/Fail", feedback: "..." }
  skills_block_density: { status: "Pass/Fail", feedback: "..." }
  bullet_wrap_and_line_length: { status: "Pass/Fail", feedback: "..." }
  section_layout_balance: { status: "Pass/Fail", feedback: "..." }
  education_and_project_inline_formatting: { status: "Pass/Fail", feedback: "..." }
  stop_slop_and_ai_writing_tells: { status: "Pass/Fail", feedback: "..." }
  tools_line_deduplication: { status: "Pass/Fail", feedback: "..." }
direct_visual_refactoring_actions: []
optimized_v2_generated: false
```

### B. `Resume.yaml`
```yaml
type: resume
language: "English/German"
render_mode: "latex"  # latex | reportfallback
resume_variation: "Balanced"  # Balanced | Project-Heavy | Skills-Heavy
keyword_stuffing: false
user_directed_skills: []
contact_info:
  name: "SAGAR MARTHANDAN"
  location: "[closest_candidate_location from ATS_Report.yaml]"
  phone: "+49 176 74138359"
  email: "sagar.marthandan@yahoo.com"
  linkedin: "linkedin.com/in/sagarmarthandan"
  github: "github.com/SagarMarthandan"
  visa: "Authorized to work in Germany"
  availability: "Immediately available"
summary: "[2 lines, <=200 chars (<=170 German), no tool names]"
technical_skills:
  - category: "[Category]"
    skills: ["[Skill]"]
projects:
  - name: "[Project Name]"
    repo_url: "[from project_info.md]"
    tools: ["[Tool]"]  # 3-5 most JD-relevant, used for parseability audit
    bullets: ["[Outcome bullet]"]  # exactly 3, joined into prose (180-240 chars EN / 160-220 DE)
professional_experience:
  - company: "[Company]"
    location: "[City]"
    date: "[MM/YYYY – MM/YYYY]"
    title: "[Title]"
    bullets: ["[<=105 chars]"]
education:
  - degree: "[Degree]"
    university: "[University]"
    date: "[MM/YYYY or 'present']"
languages: ["[Language (Level)]"]
```

### C. `post_rewrite_ats_score` (added to existing ATS_Report.yaml)
```yaml
post_rewrite_ats_score:
  ats_score_matrix:
    keywords_and_terminology: { max_score: 25, current_score: 0, evaluation_criteria: "" }
    experience_relevance:      { max_score: 25, current_score: 0, evaluation_criteria: "" }
    technical_skills:          { max_score: 25, current_score: 0, evaluation_criteria: "" }
    soft_skills_and_language:  { max_score: 25, current_score: 0, evaluation_criteria: "" }
    total_score: 0
  score_delta: 0
  formatting_quality:
    verdict: "Excellent"  # Excellent | Good | Average | Bad
    notes: ""
    suggestions: []
  score_gate_verdict: "PROCEED/HOLD"
  remaining_gaps: []
```

## Compilation Commands

### LaTeX Mode (Steps A–D)
```bash
cd "/home/sagar/Applications/[Company Name] — [Job Role]/"

# Step A: Generate .tex source (no PDF yet)
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "Resume.yaml" "SAGAR_MARTHANDAN_Resume.pdf" --tex-only
# German: substitute "SAGAR_MARTHANDAN_Lebenslauf.pdf"

# Step B: Prose refinement + char count check
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/resume_parseability.py" --check-tex "SAGAR_MARTHANDAN_Resume.tex"
# German: substitute "SAGAR_MARTHANDAN_Lebenslauf.tex"

# Step C: Final compilation (double pdflatex) + photo stamp + ATS report recompile
pdflatex -interaction=nonstopmode "SAGAR_MARTHANDAN_Resume.tex"
pdflatex -interaction=nonstopmode "SAGAR_MARTHANDAN_Resume.tex"
# German: substitute "SAGAR_MARTHANDAN_Lebenslauf.tex"

/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/stamp_photo.py" "SAGAR_MARTHANDAN_Resume.pdf" "Resume.yaml"
# German: substitute "SAGAR_MARTHANDAN_Lebenslauf.pdf"

/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf"

# Step D: Parseability audit
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/resume_parseability.py" "SAGAR_MARTHANDAN_Resume.pdf" "Resume.yaml"
# German: substitute "SAGAR_MARTHANDAN_Lebenslauf.pdf"
```

### ReportFallback Mode (single compile + audit)
```bash
cd "/home/sagar/Applications/[Company Name] — [Job Role]/"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "Resume.yaml" "SAGAR_MARTHANDAN_Resume.pdf"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/stamp_photo.py" "SAGAR_MARTHANDAN_Resume.pdf" "Resume.yaml"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/resume_parseability.py" "SAGAR_MARTHANDAN_Resume.pdf" "Resume.yaml"
```

---
### INPUTS FOR PROCESSING
Load from company folder (Step 1 outputs). Do not re-paste:
- `ATS_Report.yaml` — improvement blueprint and role archetype
- `project_info.md` — tailored project list

---
**Next:** Proceed to Step 3 — read `03_cover_letter.md`.
