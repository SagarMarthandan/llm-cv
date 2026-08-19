# Step 2 Session Prompt Template

This file documents the prompt structure used by `run_pipeline.sh` for Step 2.
The wrapper script generates this dynamically — this file is for reference/manual use.

## Prompt Structure

```
Run the llm-cv pipeline Step 2 ONLY. Do NOT proceed to Step 3.

Read skill://llm-cv (SKILL.md) and 02_resume_and_visual_audit.md for full instructions.

Application folder: {app_dir}

Read these files from the application folder (do NOT re-paste):
- ATS_Report.yaml (Step 1 output — improvement blueprint, role archetype, skill_gaps)
- project_info.md (Step 1 output — tailored project list)

First Action answers (already collected — do NOT use the ask tool):
- render_mode: {latex|reportfallback}
- resume_style: {us|german}
- language: {English|German}

Keyword stuffing decision (already collected — do NOT use the ask tool):
- keyword_stuffing: {true|false}
- user_directed_skills: "{comma-separated skills — only if Selective}"

Execute Step 2 completely:
1. Write Resume.yaml with all projects, skills, experience
2. Compile the resume (LaTeX: tex-only → pdflatex × 2 → stamp photo; ReportFallback: single compile)
3. Run layout audit → Layout_Audit_Report.yaml
4. Post-rewrite ATS rescoring → update post_rewrite_ats_score in ATS_Report.yaml
5. Run parseability audit → Parseability_Report.yaml + .pdf
6. Recompile ATS_Report.pdf with post-rewrite scores

Do NOT ask any questions — all answers are provided above.
Do NOT proceed to Step 3. This session handles Step 2 only.
```

## What Step 2 Reads
- `SKILL.md` (via skill://llm-cv)
- `02_resume_and_visual_audit.md`
- `ATS_Report.yaml` (from disk — Step 1 output)
- `project_info.md` (from disk — Step 1 output)
- `okf/project_catalog.yaml` (for project verification)

## What Step 2 Writes
- `Resume.yaml`, `Resume.tex`/`SAGAR_MARTHANDAN_Resume.tex`/`Lebenslauf.tex`
- `SAGAR_MARTHANDAN_Resume.pdf`/`Lebenslauf.pdf`
- `Layout_Audit_Report.yaml`
- `Parseability_Report.yaml`, `Parseability_Report.pdf`
- Updates `ATS_Report.yaml` (post_rewrite_ats_score block)

## Token Budget (with Phase 3 slimming)
- Base context: ~11K tokens (SKILL.md 3.5K + 02_doc 4K + base resume 1.1K + ATS_Report ~2K)
- API calls: ~12
- Total: ~240K tokens (vs ~980K in single-session mode)
