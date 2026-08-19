# Pipeline Step 1: ATS Check & Job Description Archival

> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules", §"Anti-Hallucination Principles". Only write to the application folder: `ATS_Report.yaml`, `Job_Description.yaml`, `Job_Description.pdf`, `project_info.md`.

## Objective
Analyze JD against base resume and project portfolio: detect gaps, classify archetype, calculate ATS score, structure clean JD for archival, and generate tailored project list.

## Inputs
- **JD:** Paste at bottom. May come from user paste or Step 0 (which also passes `source_url` + ATS vendor).
- **Base Resume:** Loaded from `okf/base_files/` per language selection. Archetype-specific: `resume_data_engineer.md`, `resume_data_analyst.md`, `resume_analytics_engineer.md`, `resume_ai_data_engineer.md`, fallback `resume.md`. German: `_de` suffix, `resume_de.md` covers all archetypes.

## Execution

### 0a. Name the Session
Per SKILL.md §"Name the Session" — extract Company Name and Job Role from JD, rename session to `[Company Name] — [Job Role]`.

### 0b. Load Base Files
- Python: `/home/sagar/Skills/llm-cv/.venv/bin/python` (absolute path, verbatim). No `pip install`.
- Detect archetype from JD → load matching base resume per language selection. Fallback to `resume.md`/`resume_de.md` if unmatched.

### 0c. ATS Vendor Inference & Application Source
- **Vendor:** Scan JD/URL for footprints: `myworkdayjobs.com`→Workday, `personio.de`→Personio, `successfactors.eu`→SAP SuccessFactors, `greenhouse.io`→Greenhouse, `lever.co`→Lever, `taleo.net`→Taleo. Default: `Unknown`. Reuse vendor from Step 0 if provided.
- **Application source:** Read from First Action (do NOT re-prompt). If `Cold Apply` + known vendor → warn user to check network. If `Referral`/`LinkedIn Connection` → read `weak_tie_contact` from First Action.
- **Persist First Action selections:** Write `render_mode`, `resume_style`, `language`, `application_source`, and `weak_tie_contact` (if applicable) as top-level keys in `ATS_Report.yaml`. These persist across session boundaries so Step 2 and Step 3 can read them from disk.

### 1. Requirements & Archetype Detection
- Classify JD into one primary archetype. Save with one-sentence rationale under `role_archetype`.
- If JD spans two domains, assign `secondary` archetype with rationale. Omit if single-domain.

### 2. ATS Scoring Matrix
- 4 equally-weighted categories (25pts each, 100 total): `keywords_and_terminology`, `experience_relevance`, `technical_skills`, `soft_skills_and_language`.
- Formatting NOT scored. Emit separate `formatting_quality` verdict (`Excellent`/`Good`/`Average`/`Bad`) with `suggestions` if Average/Bad.
- **Informational only — never blocks:** `PROCEED` if ≥85, else `REVIEW` with `remedy_suggestions`. Step 2 always proceeds.

### 3. Skill Gap Analysis
- Extract `required_skills` from JD (explicitly required/strongly preferred only).
- `resume_skills` from base resume + `project_skills` from matched projects.
- `skill_gaps = required_skills - (resume_skills ∪ project_skills)`. Store as flat list.

> **ANTI-HALLUCINATION — Skill Gaps:** Only JD-explicitly-required skills. No "might be relevant" or "commonly associated" skills. Every entry traceable to JD text.

### 4. Contextual Placement Weighting
- For each critical JD keyword, check which resume sections contain it: skills (1.0x), project summary (1.2x), experience bullet (1.3x), multiple sections (1.5x). Not found → omit.
- Store under `placement_breakdown.keywords`. Informational — does not change the 4-category score.

### 5. Improvement Blueprint
- **`bullet_point_density_audit`:** Flag metric-free experience/project bullets.
- **`project_swap_directive`:** List misaligned projects under `remove_projects`. List archetype-aligned projects from `project_info.md` not in base resume under `add_projects` (each with justification). Confirm 3 (or 4) selected.
- **`keyword_inventory`:** JD keywords absent from resume only. Categorize: `hard_skills`, `methodologies`, `domain_terms`.
- **`technical_skills_tuning`:** Tools to add (in JD + catalog/base resume) and remove (irrelevant for this role).
- **`quantified_outcomes`:** For each metric-free bullet, suggest revision using catalog `key_metrics` or base resume source. No fabrication.

> **ANTI-HALLUCINATION — Blueprint:** `add_projects` must match catalog titles exactly. `quantified_outcomes.suggested` must use catalog metrics or qualitative improvements — no fabricated numbers. `technical_skills_tuning.add` only tools the candidate has used.

### 6. JD Archival & Location Extraction
- Strip web tracking/metadata. Extract job location → `location` in `Job_Description.yaml`.
- Structure into clean YAML sections: overview, requirements, responsibilities, stack.

### 7. Candidate Location Selection
- 4 candidate cities: Kiel (home), Frankfurt, Berlin, Köln.
- **Static lookup first:** `python -c "from config import nearest_candidate_city; print(nearest_candidate_city('[job_location]') or 'NOT_FOUND')"`
- **Web search fallback** if NOT_FOUND, then cache: `python -c "from config import cache_location_result; cache_location_result('[job_location]', '[resolved_city, Germany]')"`
- Remote/unspecified → Kiel, Germany. Save as `closest_candidate_location` in `ATS_Report.yaml`.

## Output Directory
Create `/home/sagar/Applications/[Company Name] — [Job Role]/`. Save: `ATS_Report.yaml`, `Job_Description.yaml`, `project_info.md`.

### A. `ATS_Report.yaml` Schema
```yaml
type: ats_report
company: "[Company Name]"
position: "[Job Position Title]"
render_mode: "latex"  # latex | reportfallback — from First Action (persisted for Step 2/3 in session-split mode)
resume_style: "us"    # us | german — from First Action
language: "English"   # English | German — from First Action
closest_candidate_location: "[Kiel/Frankfurt/Berlin/Köln, Germany]"
ats_vendor: "[Workday/Personio/SAP SuccessFactors/Greenhouse/Lever/Taleo/Unknown]"
application_source: "[Cold Apply/Referral/LinkedIn Connection/Direct]"
weak_tie_contact: null
role_archetype:
  primary: "[Archetype Name]"
  secondary: "[Secondary — omit if single-domain]"
  archetype_rationale: "[One sentence]"
  secondary_rationale: "[One sentence — omit if secondary omitted]"
ats_score_matrix:
  keywords_and_terminology: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  experience_relevance: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  technical_skills: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  soft_skills_and_language: { max_score: 25, current_score: 0, evaluation_criteria: "..." }
  total_score: 0
formatting_quality:
  verdict: "Excellent"  # Excellent | Good | Average | Bad
  notes: ""
  suggestions: []  # Only when Average or Bad
core_score_detractors: []
skill_gaps: []
placement_breakdown:
  keywords: []  # { keyword, sections_found, multiplier }
improvement_blueprint:
  target_language_confirmation: "[English or German]"
  bullet_point_density_audit:
    - bullet: "[Exact bullet text]"
      issue: "No quantified metric"
  project_swap_directive:
    remove_projects: []
    add_projects: [{ name: "...", justification: "..." }]
    volume_constraint_check: "3 projects selected"
  keyword_inventory:
    hard_skills: []
    methodologies: []
    domain_terms: []
  technical_skills_tuning:
    add: []
    remove: []
  quantified_outcomes:
    - original: "[Metric-free bullet]"
      suggested: "[Revised with quantified outcome]"
  ats_threshold_calibration:
    meets_target: false
    score_gate_verdict: "REVIEW/PROCEED"
    remedy_suggestions: []
# post_rewrite_ats_score: populated by Step 2 only
```

### B. `Job_Description.yaml` Schema
```yaml
type: job_description
company: "[Company Name]"
position: "[Job Position Title]"
location: "[Job Location from JD]"
source_url: "[Optional — from Step 0. Omit if user pasted JD manually.]"
sections:
  - title: "Core Role Overview & Context"
    content: "[Overview paragraph]"
  - title: "Target Profile Requirements"
    bullets: ["[Requirement]"]
  - title: "Primary Responsibilities"
    bullets: ["[Responsibility]"]
  - title: "Tech Stack & Tooling"
    bullets: ["[Tool/Skill]"]
```

## LLM-Based Project Ranking & Compilation

### Ranking
Read `okf/project_catalog.yaml` (15 projects). Rank top 6 for this JD by: technology overlap, transferable skills, business-problem match, archetype fit, complexity/seniority, reframing potential.

> **ANTI-HALLUCINATION — Ranking:** Select ONLY from 15 catalog projects. No inventing/splitting/merging. Every project maps 1:1 by exact `title` match. `repo_url` must be exact catalog entry — bare profile URL = hallucination red flag.

Write `project_info.md` in application folder:
```markdown
# Tailored Project Portfolio

# [Project Title]
[Description from catalog]
Problem: [business_problem]
Metrics: [key_metrics — cite verbatim]
Tech: [technologies]
Archetypes: [archetypes]
Repo: [repo_url]
[First 2 bullets from catalog]
<!-- LLM Rank: [rank], Reason: [one sentence] -->
```
Repeat for all 6. Step 2 ignores HTML comments.

### Post-Ranking Validation (MANDATORY)
```bash
/home/sagar/Skills/llm-cv/.venv/bin/python -c "
import yaml
with open('/home/sagar/Skills/llm-cv/okf/project_catalog.yaml') as f:
    catalog = {p['title'] for p in yaml.safe_load(f)['projects']}
print('Catalog projects:', len(catalog))
"
```
Cross-check each `# [Project Title]` heading against catalog. If mismatch → replace with next-best real catalog project. Re-run until all 6 match.

### Compilation
```bash
cd "/home/sagar/Applications/[Company Name] — [Job Role]/"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf"
/home/sagar/Skills/llm-cv/.venv/bin/python "/home/sagar/Skills/llm-cv/yaml_to_pdf.py" "Job_Description.yaml" "Job_Description.pdf"
```

---
### ATTACHMENTS FOR PROCESSING
Paste the raw Job Description text below this line.

---
**Next:** Proceed to Step 2 — read `02_resume_and_visual_audit.md`.
