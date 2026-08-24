# Score-Boost Measures

> Applied conditionally when `ats_score_matrix.total_score` < 85 AND the user opts in.
> Measures 1-3 apply during §1 (Document Rewrite). Measure 4 applies during §5 (Post-Rewrite ATS Rescoring).
> Compilation/verification steps are already covered by §2-4 and Steps A-D — no duplicate chain here.
> **Anti-Hallucination still applies:** these measures enhance framing and surface real adjacent skills. They do NOT permit fabricating capabilities, metrics, or experience.

## Measure 1: Student Framing

If the JD is an intern/Werkstudent/student role AND the candidate is currently enrolled (education entry with date "present"), lead the summary with "M.Sc. student in [field] and [archetype], ..." instead of a bare title. Still exactly 2 lines, ≤200 chars EN / ≤170 DE, no tool names.

## Measure 2: Exact JD Phrase Weaving

Scan `Job_Description.yaml` for distinctive verb phrases (e.g. "data transformation workflows", "Python-based bots and utilities", "SQL queries and stored procedures"). Weave at least 1 exact phrase into truthful bullet prose. Rules: phrase must be genuinely matched by the candidate's work (no capability fabrication); longest phrase goes in the German-style Independent entry's single "other tools" bullet (≤105 chars, 1 line); project bullets stay 180-240 chars total / exactly 3 lines.

## Measure 3: Real Adjacent Skills

If the JD demands bots/automation/API work and the base resume contains a streaming/API category (Apache Kafka, Redis, REST APIs, JSON/HTML/PDF parsing, AWS SQS), re-add it as its own Technical Skills row even if the current JD-anchored block dropped it. Replace weak-signal filler instead of growing the block (e.g. generic plotting libs): 1-page fill must hold.

## Measure 4: Itemized Scoring Rubric

Mandatory for `post_rewrite_ats_score` when Score-Boost is active. Score each of the 4 categories against an explicit enumerated list of JD term groups, not impressions. Write the matched/unmatched item lists inside `evaluation_criteria`. Unmatched terms carry a parenthetical reason: "(excluded by user)" if the user excluded them, "(not in candidate's evidence)" otherwise; mirror that phrasing in `remaining_gaps`. Every score point must trace to a string present in `Resume.yaml` or a documented fact. Do not inflate: the category ceiling is real JD-stack coverage. Target ≥88 only if the itemized rubric genuinely supports it.
