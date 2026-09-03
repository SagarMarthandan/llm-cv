# Session 3 Prompt Template (Cover Letter Writer)

This file documents the prompt structure used by `run_pipeline.sh` for Session 3.
Session 3 is a dedicated OMP session launched by bash in parallel with Session 2.
The wrapper script generates this dynamically — this file is for reference.

## Prompt Structure

```
Run the llm-cv pipeline Step 3 ONLY. Write a cover letter YAML file.

Read skill://llm-cv (SKILL.md) and 03_cover_letter.md for full instructions.

Application folder: {app_dir}

Read these files from the application folder:
- ATS_Report.yaml (render_mode, language, closest_candidate_location, application_source, weak_tie_contact, role_archetype)
- Job_Description.yaml (company, position, JD sections)
- project_info.md (tailored project list with metrics)

First Action answers (already collected — do NOT use the ask tool):
- render_mode: {latex|reportfallback}
- language: {English|German}

Write Cover_Letter.yaml to the application folder following the schema in 03_cover_letter.md.

Key constraints:
- Geschäftsbrief layout, max 4 paragraphs
- English: 250-320 words / German: 180-240 words (single A4 page)
- Ground tech skills in metrics from project_info.md
- No resume rehash — cover letter carries info the resume does not
- Integrate B1 German studies + GitHub portfolio
- Archetype-conditional: only mention LLMs/RAG for AI archetypes
- Anti-hallucination: metrics from project_info.md or catalog, no fabrication
- Stop-slop: active voice, no -ly adverbs, no em-dashes

Do NOT compile any PDFs. Just write Cover_Letter.yaml.
Do NOT ask any questions — all answers are provided above.
When you are done, print: "STEP 3 COMPLETE"
```

## What Session 3 Reads
- `SKILL.md` (via skill://llm-cv)
- `03_cover_letter.md`
- `ATS_Report.yaml` (from disk — Step 1 output)
- `Job_Description.yaml` (from disk — Step 1 output)
- `project_info.md` (from disk — Step 1 output)

## What Session 3 Writes
- `Cover_Letter.yaml`
- PDF compiled by bash after session ends

## Token Budget
- Context: ~10K tokens (SKILL.md 5.5K + 03_doc 1.2K + ATS_Report 2K + JD 1K + project_info 2K)
- API calls: ~6
- Total: ~60K tokens

## Total Pipeline (3 sessions + bash)
- Session 1 (ATS + ranking): ~100K tokens
- Session 2 (resume + ATS rescoring): ~120K tokens
- Session 3 (cover letter, parallel): ~60K tokens
- Bash compilation: 0 tokens
- Fix sessions (if needed): ~15K tokens each
- Combined: ~280K tokens (vs ~2.5M single-session)
- Savings: ~2.2M tokens per run (88% reduction)
- Flash-model safe: no subagent spawning, no hub wait, no wave coordination
