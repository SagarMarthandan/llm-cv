# Step 1 Session Prompt Template

This file documents the prompt structure used by `run_pipeline.sh` for Step 1.
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
2. Write ATS_Report.yaml, Job_Description.yaml, project_info.md
3. Compile ATS_Report.pdf and Job_Description.pdf
4. Store all First Action answers in the appropriate YAML files

Do NOT ask any questions — all answers are provided above.
Do NOT proceed to Step 2. This session handles Step 1 only.
```

## What Step 1 Reads
- `SKILL.md` (via skill://llm-cv)
- `01_ats_and_jd_archival.md`
- `okf/project_catalog.yaml` (for LLM project ranking)
- `okf/base_files/{english|german}/resume_*.md` (base resume)

## What Step 1 Writes
- `ATS_Report.yaml`, `ATS_Report.pdf`
- `Job_Description.yaml`, `Job_Description.pdf`
- `project_info.md`

## Token Budget (with Phase 3 slimming)
- Base context: ~13K tokens (SKILL.md 3.5K + 01_doc 2.4K + catalog 12K + base resume 1.1K)
- API calls: ~10
- Total: ~130K tokens (vs ~820K in single-session mode)
