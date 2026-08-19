# Step 3 Session Prompt Template

This file documents the prompt structure used by `run_pipeline.sh` for Step 3.
The wrapper script generates this dynamically — this file is for reference/manual use.

## Prompt Structure

```
Run the llm-cv pipeline Step 3 ONLY. This is the final step.

Read skill://llm-cv (SKILL.md) and 03_cover_letter.md for full instructions.

Application folder: {app_dir}

Read these files from the application folder (do NOT re-paste):
- ATS_Report.yaml (Step 1 output — archetype, closest_candidate_location, application_source)
- Job_Description.yaml (Step 1 output — company, position, JD sections)
- project_info.md (Step 1 output — tailored project list with metrics)

First Action answers (already collected — do NOT use the ask tool):
- render_mode: {latex|reportfallback}
- language: {English|German}

Execute Step 3 completely:
1. Write Cover_Letter.yaml
2. Compile the cover letter PDF
3. Run Obsidian sync: sync_to_obsidian.py "{app_dir}" --sort

Do NOT ask any questions — all answers are provided above.
This is the final step — after completion, the pipeline is done.
```

## What Step 3 Reads
- `SKILL.md` (via skill://llm-cv)
- `03_cover_letter.md`
- `ATS_Report.yaml` (from disk — Step 1 output)
- `Job_Description.yaml` (from disk — Step 1 output)
- `project_info.md` (from disk — Step 1 output)

## What Step 3 Writes
- `Cover_Letter.yaml`
- `Cover_Letter.tex`/`SAGAR_MARTHANDAN_Cover_Letter.tex`
- `SAGAR_MARTHANDAN_Cover_Letter.pdf`/`Anschreiben.pdf`
- Obsidian vault notes (via sync_to_obsidian.py)

## Token Budget (with Phase 3 slimming)
- Base context: ~8K tokens (SKILL.md 3.5K + 03_doc 1.2K + ATS_Report ~2K + JD ~1K)
- API calls: ~8
- Total: ~120K tokens (vs ~660K in single-session mode)

## Total Pipeline (all 3 sessions)
- Combined: ~490K tokens (vs ~2.5M single-session)
- Savings: ~2M tokens per run (80% reduction)
