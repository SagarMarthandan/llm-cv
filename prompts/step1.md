# Session 1 Prompt Template (ATS + Ranking)

This file documents the prompt structure used by `run_pipeline.sh` for Session 1.
The wrapper script generates this dynamically — this file is for reference/manual use.

## Prompt Structure

```
Run the llm-cv pipeline Step 1 ONLY. Do NOT proceed to Step 2 or Step 3.

Read skill://llm-cv (SKILL.md) and 01_ats_and_jd_archival.md for full instructions.

First Action answers (already collected — do NOT use the ask tool):
- render_mode: {latex|reportfallback}
- resume_style: {us|german}
- application_source: {Cold Apply|Referral|LinkedIn Connection|Direct}
- language: {English|German}
- weak_tie_contact: {name/role — only if Referral or LinkedIn Connection}

[If URL provided:]
The user provided a URL: {url}
First read 00_jd_fetch.md and fetch the JD from this URL, then proceed with Step 1.

[If JD text provided:]
Job Description (pasted by user):
---
{jd_text}
---

Execute Step 1 completely:
1. Create the application folder /home/sagar/Applications/[Company Name] — [Job Role]/
2. Write ATS_Report.yaml and Job_Description.yaml to that folder
3. Store all First Action answers in ATS_Report.yaml
4. Rank top 6 projects: read okf/project_catalog_condensed.yaml (15 projects, no bullets — 21KB).
   Rank by technology overlap, transferable skills, business-problem match, archetype fit,
   complexity/seniority, reframing potential.
5. Write project_info.md to the application folder (format in 01_ats_and_jd_archival.md)
6. Run the post-ranking validation script to verify all 6 project titles match the catalog

Do NOT compile any PDFs — compilation is handled by the wrapper script after you finish.
Do NOT ask any questions — all answers are provided above.
Do NOT proceed to Step 2. This session handles Step 1 only.
When you are done, print: "STEP 1 COMPLETE"
```

## What Session 1 Reads
- `SKILL.md` (via skill://llm-cv)
- `01_ats_and_jd_archival.md`
- `okf/project_catalog_condensed.yaml` (21KB, no bullets — for ranking)
- `okf/base_files/{english|german}/resume_*.md` (base resume)

## What Session 1 Writes
- `ATS_Report.yaml`
- `Job_Description.yaml`
- `project_info.md`
- PDFs compiled by bash after session ends

## Token Budget
- Context: ~13K tokens (SKILL.md 5.5K + 01_doc 2.4K + condensed catalog 5.3K + base resume 1.1K)
- API calls: ~8
- Total: ~100K tokens
