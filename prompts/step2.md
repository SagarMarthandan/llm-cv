# Session 2 Prompt Template (Resume Writer + ATS Rescoring)

This file documents the prompt structure used by `run_pipeline.sh` for Session 2.
Session 2 is a dedicated OMP session launched by bash (parallel with Session 3).
The wrapper script generates this dynamically — this file is for reference.

## Prompt Structure

```
Run the llm-cv pipeline Step 2 ONLY. Write a resume YAML file.

Read skill://llm-cv (SKILL.md) and 02_resume_and_visual_audit.md for full instructions.

Application folder: {app_dir}

First Action answers (already collected — do NOT use the ask tool):
- render_mode: {latex|reportfallback}
- resume_style: {us|german}
- language: {English|German}
- keyword_stuffing: {true|false}
- user_directed_skills: "{comma-separated skills — only if Selective}"
- score_boost_mode: {true|false}
- initial_ats_score: {integer}

Read these files from the application folder:
- ATS_Report.yaml (improvement_blueprint, role_archetype, skill_gaps, closest_candidate_location)
- selected_projects.yaml (6 ranked projects with full bullets — use this INSTEAD of the full catalog)
- Job_Description.yaml (for JD references — do NOT re-paste raw JD)
- okf/base_files/{english|german}/resume_*.md (base resume — detect archetype from ATS_Report.yaml)
- prompts/score_boost.md (only if score_boost_mode is true)

Write Resume.yaml to the application folder following the schema in 02_resume_and_visual_audit.md.

Key constraints (NON-NEGOTIABLE):
- Exactly 3 bullets per project, 180-240 chars EN / 160-220 DE, hard 3-line render limit
- Summary: 2 lines, ≤200 chars EN / ≤170 DE, no tool names
- Experience bullets: ≤105 chars, 1 line each
- JD-relevant technical skills only (anti-stuffing)
- Project tools: 3-5 most JD-relevant per project
- Anti-hallucination: only projects from selected_projects.yaml, metrics from catalog key_metrics
- Stop-slop: active voice, no -ly adverbs, no em-dashes (except --- separators)
- Font rule: LaTeX uses lmodern, never patch preamble
- Page fill: must fill exactly 1 A4 page, zero empty trailing lines

After writing Resume.yaml, do the Post-Rewrite ATS Rescoring (§5 of 02_resume_and_visual_audit.md):
- Re-run the 4-category ATS matrix (25pts each, 100 total) on the final resume
- Write the post_rewrite_ats_score block to ATS_Report.yaml (APPEND, do NOT overwrite the pre-rewrite section)
- Calculate score_delta and set score_gate_verdict (PROCEED/HOLD)

Do NOT compile any PDFs. Just write Resume.yaml and update ATS_Report.yaml.
Do NOT ask any questions — all answers are provided above.
When you are done, print: "STEP 2 COMPLETE"
```

## What Session 2 Reads
- `SKILL.md` (via skill://llm-cv)
- `02_resume_and_visual_audit.md`
- `ATS_Report.yaml` (from disk — Step 1 output)
- `selected_projects.yaml` (~7KB — extracted by bash from project_info.md + full catalog)
- `Job_Description.yaml` (from disk — Step 1 output)
- `okf/base_files/{english|german}/resume_*.md` (base resume)
- `prompts/score_boost.md` (only if score_boost_mode is true)

## What Session 2 Writes
- `Resume.yaml`
- `ATS_Report.yaml` updated with `post_rewrite_ats_score` block
- PDFs compiled by bash after session ends

## Token Budget
- Context: ~14K tokens (SKILL.md 5.5K + 02_doc 4K + selected_projects 1.8K + ATS_Report 2K + base resume 1.1K)
- API calls: ~10
- Total: ~120K tokens
