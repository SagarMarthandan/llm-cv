# llm-cv Token Optimization Plan

3-4 pipeline runs on nanoGPT (DeepSeek, subscription plan) consumed **12M tokens** out of a 60M quota (20% gone in 3-4 resumes). The cost is ~3-4M tokens per run. This is not a bug — it's the inherent O(N) context accumulation of stateless agent loops: every API call re-sends the entire conversation, so a ~43K token base context multiplied across ~30 tool calls per run = ~2.5-3M tokens.

> **Prompt caching does NOT help on nanoGPT subscription.** nanoGPT supports prompt caching (implicit, automatic for DeepSeek), but per their docs: "Cached input tokens do count toward your included input-token allowance. Whether a token is a cache hit or a cache miss, it still consumes the same amount of your allotted subscription units." Caching reduces latency and PAYG costs, but **does not reduce subscription quota consumption**. The only way to burn fewer quota tokens is to send fewer tokens — which is what this plan does.

## Current State (Measured)

### File sizes (the persistent context that gets re-sent every API call)

| File | Bytes | Lines | Tokens (≈bytes/4) |
|---|---|---|---|
| `SKILL.md` | 32,121 | 307 | 8,030 |
| `02_resume_and_visual_audit.md` | 42,792 | 446 | 10,698 |
| `01_ats_and_jd_archival.md` | 23,591 | 299 | 5,898 |
| `03_cover_letter.md` | 9,936 | 116 | 2,484 |
| `00_jd_fetch.md` | 9,466 | 115 | 2,367 |
| `okf/project_catalog.yaml` | 48,912 | 329 | 12,228 |
| Base resume (avg) | 4,500 | ~80 | 1,125 |
| **Total skill docs** | **171,318** | **1,692** | **~42,830** |

### Repeated content across files (pure waste)

| Repeated block | Occurrences | Est. tokens per block | Total wasted |
|---|---|---|---|
| READ-ONLY SKILL FILES guardrail | 5 (SKILL + 4 step docs) | ~800 | ~3,200 |
| AGENT EXECUTION RULES | 4 (step docs) | ~200 | ~600 |
| YAML SAFETY RULES | 3 (step docs) | ~400 | ~800 |
| ANTI-HALLUCINATION guardrails | 8 (across step docs) | ~300-600 | ~3,600 |
| Stop-Slop rules | 4 (SKILL + step docs) | ~200 | ~600 |
| **Total repeated waste** | | | **~8,800 tokens** |

That's ~8,800 tokens re-sent on every API call, 30 times per run, 3 runs = **~792K tokens of pure duplication**.

### Token cost breakdown per run (estimated)

```
Base context:          ~53,000 tokens (skill docs + catalog + system prompt + JD)
Tool calls per run:    ~30
Context growth:        ~2,000 tokens per tool result
Average context:       ~82,000 tokens
Tokens per run:        30 × 82,000 = ~2.5M
3 runs:                ~7.4M + Devin overhead = ~9.1M
```

### Where the tokens go (per run, 30 calls)

```
Skill docs re-sent 30×:     42,830 × 30 = 1,284,900  (52% of run)
Project catalog re-sent 30×: 12,228 × 30 =   366,840  (15% of run)
Tool results accumulating:  2,000 × 30  =    60,000   (2% of run)
System prompt re-sent 30×:  10,000 × 30 =   300,000   (12% of run)
JD text re-sent 30×:         3,000 × 30 =    90,000   (4% of run)
Context growth overhead:   ~1,200,000              (15% of run)
```

**The skill docs + catalog alone account for 67% of token consumption.** They are read once but re-sent on every single API call because the LLM is stateless.

---

## Optimization Strategy

### Principle: Reduce the base context size. Every token cut from the persistent context saves 30× per run (once per API call).

### Target: Cut base context from ~43K to ~22K tokens (49% reduction).

At 30 calls per run, that saves ~(43K - 22K) × 30 = **630K tokens per run**, ~1.9M across 3 runs. New estimated usage: ~7.2M → **~5.3M** for 3 runs (42% reduction).

---

## Phase 1: De-duplicate Repeated Blocks (Save ~8,800 tokens)

**Effort:** Low. **Risk:** None. **Savings:** ~8,800 base tokens × 30 calls = 264K/run.

### 1.1 Extract shared rules to SKILL.md, replace step doc copies with 1-line references

Currently each step doc (00, 01, 02, 03) re-prints the full READ-ONLY guardrail (~800 tokens), AGENT EXECUTION RULES (~200 tokens), YAML SAFETY RULES (~400 tokens), and multiple ANTI-HALLUCINATION blocks (~300-600 tokens each).

**Change:**
- Keep the full text of each shared rule in `SKILL.md` only.
- In each step doc, replace the full block with a single reference line:

```
> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules", §"Anti-Hallucination Principles".
```

That's ~30 tokens vs ~2,200 tokens per step doc. Across 4 step docs: **save ~8,700 tokens**.

### 1.2 Consolidate Stop-Slop rules

SKILL.md already has the full Stop-Slop section. Step 02 and 03 re-describe it. Replace with:

```
- Apply Stop-Slop rules per SKILL.md §"Stop-Slop".
```

**Save ~400 tokens.**

---

## Phase 2: Slim Down SKILL.md (Save ~12,000 tokens)

**Effort:** Medium. **Risk:** Low (content preserved, just condensed). **Savings:** ~12,000 base tokens × 30 calls = 360K/run.

### 2.1 Move completion checklist to a separate file

The completion checklist is 30+ items (~2,500 tokens) that the agent only needs at the END of the pipeline, not during every API call.

**Change:** Move to `99_completion_checklist.md`. SKILL.md references it:

```
## Completion Checklist
See `99_completion_checklist.md` — read it only after all 3 steps complete.
```

**Save ~2,500 tokens** from the base context for 25+ API calls (only read at the end).

### 2.2 Condense First Action questions

The 4 questions with full option descriptions take ~3,000 tokens. Condense to a compact table:

```
## First Action: Pipeline Options (ask all 4 in one `ask` call)

| # | Setting | Options |
|---|---------|---------|
| 1 | Render mode | LaTeX (pdflatex, .tex source) / ReportFallback (ReportLab, no pdflatex) |
| 2 | Resume style | US (Skills→Projects→Experience) / German (Experience→Skills, projects in experience) |
| 3 | Application source | Cold Apply / Referral / LinkedIn Connection / Direct |
| 4 | Language | English / German |
```

**Save ~2,000 tokens.**

### 2.3 Condense anti-hallucination principles

The 6 anti-hallucination principles in SKILL.md are ~2,000 tokens with detailed explanations. Condense to bullet points with 1-line summaries (the detailed versions are already re-stated in each step doc's context-specific guardrails):

```
## Anti-Hallucination Principles (Non-Negotiable)
1. **Projects:** Only the 15 in project_catalog.yaml. No inventing/splitting/merging.
2. **Metrics:** From catalog key_metrics or base resume bullets only. No fabrication.
3. **Skills:** From catalog, base resume, or JD required skills. No invented skills (unless user-directed via keyword stuffing).
4. **Company/Role:** Verbatim from JD. No paraphrasing.
5. **Employment:** Dates/titles from base resume are immutable. Independent period (01/2023-04/2025) is self-learning, not production.
6. **Repo URLs:** Verbatim from catalog. No bare profile URLs.
```

**Save ~1,200 tokens.**

### 2.4 Remove verbose pipeline overview diagram

The ASCII pipeline diagram + bullet-point overview (~1,500 tokens) duplicates what the step docs already describe. Replace with a 3-line summary:

```
## Pipeline Overview
Step 1: ATS analysis + JD archival + project ranking → ATS_Report.yaml, Job_Description.pdf, project_info.md
Step 2: Resume rewrite + layout audit + parseability audit → Resume.pdf, Layout_Audit_Report.yaml, Parseability_Report.pdf
Step 3: Cover letter → Cover_Letter.pdf
Post: Obsidian sync + sort
```

**Save ~1,200 tokens.**

### 2.5 Condense font rule, read-only guardrail, and writable files list

The read-only guardrail + writable files list is ~2,500 tokens with extensive file enumeration. Condense:

```
## Read-Only Guardrail (Non-Negotiable)
- **Read-only:** All skill infrastructure — SKILL.md, step docs, renderers/, pipeline scripts, okf/base_files/, okf/project_catalog.yaml, config.py.
- **Writable:** Only generated files inside the application folder (/home/sagar/Applications/[Company] — [Role]/).
- **Font rule:** LaTeX mode uses lmodern (LM Roman 10). Never patch the .tex preamble to change fonts. Keyword misses are fixed by adjusting YAML wording, not fonts.
```

**Save ~1,800 tokens.**

### 2.6 Condense post-pipeline and error handling sections

The post-pipeline Obsidian sync instructions and error handling are ~1,500 tokens. Move sync instructions to Step 03 (where they already exist) and condense error handling to 3 bullets.

**Save ~800 tokens.**

---

## Phase 3: Slim Down Step Docs (Save ~10,000 tokens)

**Effort:** Medium. **Risk:** Low. **Savings:** ~10,000 base tokens × 30 calls = 300K/run.

### 3.1 Slim `02_resume_and_visual_audit.md` (43KB → ~18KB)

This is the biggest file. Key cuts:

- **Remove §4 LaTeX Project Format Polish examples** (~2,500 tokens): The renderer already produces the correct format. The before/after LaTeX examples are illustrative but not needed every run. Keep the 7 refinement rules as bullets, drop the code blocks.
- **Condense §2.5 Space-Fill Directive** (~1,500 tokens → ~500): The 5-step priority order can be 5 bullets instead of paragraphs.
- **Condense §2 Structural & Layout Constraints** (~2,000 tokens → ~800): Convert to a compact constraints table:
  ```
  | Element | English | German |
  |---------|---------|--------|
  | Summary | 2 lines, ≤200 chars | 2 lines, ≤170 chars |
  | Project summary | ≤300 chars, ≤3 lines | ≤280 chars, ≤3 lines |
  | Experience bullets | ≤105 chars, 1 line each | same |
  | IBM bullets | exactly 4 | exactly 4 |
  | Staff 4 bullets | exactly 2 | exactly 2 |
  ```
- **Condense §6 Parseability Audit** (~1,200 tokens → ~400): The script auto-recovers. Just list the command and pass criteria.
- **Condense §7 Anti-Hallucination Validation** (~800 tokens → ~200): The Python validation script is the source of truth. Keep the command, drop the prose explanation.
- **Remove repeated guardrails** (per Phase 1): ~2,200 tokens.
- **Condense compilation commands** (~1,000 tokens → ~400): Group into a single code block instead of scattered Step A/B/C/D sections.

**Target: 43KB → ~18KB (save ~6,200 tokens).**

### 3.2 Slim `01_ats_and_jd_archival.md` (24KB → ~12KB)

- **Condense ATS scoring matrix description** (~1,500 tokens → ~500): The schema YAML already documents the structure. Keep the 4-category names and weights, drop the verbose explanations.
- **Condense improvement blueprint** (~1,500 tokens → ~600): The schema YAML documents the fields. Keep 1-line descriptions per field.
- **Condense placement weighting** (~800 tokens → ~200): The multipliers table is enough.
- **Remove repeated guardrails** (per Phase 1): ~2,200 tokens.
- **Condense compilation commands**: ~300 tokens.

**Target: 24KB → ~12KB (save ~3,000 tokens).**

### 3.3 Slim `03_cover_letter.md` (10KB → ~5KB)

- **Remove repeated guardrails** (per Phase 1): ~1,000 tokens.
- **Condense narrative rules** (~1,000 tokens → ~400): Bullet points instead of paragraphs.
- **Condense schema** (~800 tokens → ~300): The YAML schema is self-documenting.

**Target: 10KB → ~5KB (save ~1,200 tokens).**

### 3.4 Slim `00_jd_fetch.md` (9.5KB → ~4KB)

- **Condense validation heuristic** (~800 tokens → ~200): The 5 checks as bullets.
- **Condense strategy routing** (~600 tokens → ~200): One sentence per strategy.
- **Remove repeated guardrails** (per Phase 1): ~500 tokens.

**Target: 9.5KB → ~4KB (save ~1,400 tokens).**

---

## Phase 4: Slim Project Catalog (Save ~6,000 tokens)

**Effort:** Medium. **Risk:** Medium (must preserve all data needed for ranking). **Savings:** ~6,000 base tokens × 30 calls = 180K/run.

### 4.1 Create `okf/project_catalog_condensed.yaml`

The full catalog is 49KB (12,228 tokens) with 8-10 detailed bullets per project. The agent needs the full bullets only when writing the resume (Step 2). For project ranking (Step 1), it only needs: title, description, business_problem, key_metrics, transferable_skills, technologies, archetypes, repo_url.

**Change:** Create a condensed catalog with NO bullets (~22KB, ~5,500 tokens):

```yaml
projects:
  - title: "Chicago Crime & Divvy Bike-Share Data Engineering Pipeline"
    description: "..."
    technologies: "..."
    archetypes: [Data Engineering, Analytics Engineering, ...]
    business_problem: "..."
    key_metrics: "..."
    transferable_skills: [...]
    repo_url: "..."
    # NO bullets field — full bullets are in project_catalog.yaml
```

Step 1 reads the condensed catalog for ranking. Step 2 reads the full catalog entry for only the 3-6 selected projects (via a Python script that extracts just those entries).

**Save ~6,700 tokens** from the base context during Steps 1-3 (condensed catalog replaces full catalog).

### 4.2 Alternative: Python script extracts selected projects

Add a helper script `extract_projects.py` that takes project titles and outputs a YAML with only those projects' full data:

```bash
python extract_projects.py --titles "Project A,Project B,Project C" --catalog okf/project_catalog.yaml
```

Step 1 ranks using the condensed catalog, then Step 2 calls this script to get full bullets for only the 3-6 selected projects (~3KB instead of 49KB).

---

## Phase 5: Lazy Loading Strategy (Save ~5,000 tokens)

**Effort:** Low. **Risk:** None. **Savings:** ~5,000 tokens × remaining calls.

### 5.1 Don't read all step docs at once

Currently the agent reads SKILL.md (which instructs reading all step docs). Instead:

- SKILL.md instructs: "Read only the step doc for the step you're executing."
- Step 1 doc ends with: "Proceed to Step 2 — read `02_resume_and_visual_audit.md`."
- Step 2 doc ends with: "Proceed to Step 3 — read `03_cover_letter.md`."

This means Step 2's doc (the biggest at 43KB→18KB) is not in context during Step 1's ~10 API calls, and Step 1's doc is not needed during Step 3.

**Savings:** Step 2 doc (18KB after Phase 3) not in context for ~10 calls = ~45K tokens saved per run. Step 1 doc (12KB after Phase 3) not in context for ~10 calls = ~30K tokens saved per run.

**Total: ~75K tokens per run from lazy loading.**

### 5.2 Read Step 0 doc only when URL is provided

Already the case in the current design, but make it explicit in SKILL.md.

---

## Phase 6: Consolidate Compilation Commands (Save ~2,000 tokens)

**Effort:** Low. **Risk:** None. **Savings:** ~2,000 tokens × 30 calls = 60K/run.

### 6.1 Create `compile_commands.md` reference

Compilation commands are scattered across Step 1 (ATS Report + JD), Step 2 (Resume tex-only → pdflatex → stamp photo → parseability), and Step 3 (Cover Letter). Each step doc has its own copy.

**Change:** Create a single `compile_commands.md` with all commands in one place. Step docs reference it:

```
## Compilation
See `compile_commands.md` for all compilation commands. Key commands for this step:
- ATS Report: `yaml_to_pdf.py ATS_Report.yaml ATS_Report.pdf`
- Job Description: `yaml_to_pdf.py Job_Description.yaml Job_Description.pdf`
```

**Save ~2,000 tokens** from step docs (they no longer contain full command blocks with comments).

---

## Summary: Before vs After

### Base context per API call

| Component | Before (tokens) | After (tokens) | Savings |
|---|---|---|---|
| SKILL.md | 8,030 | 3,500 | 4,530 |
| 02_resume_audit.md | 10,698 | 4,500 | 6,198 |
| 01_ats_archival.md | 5,898 | 3,000 | 2,898 |
| 03_cover_letter.md | 2,484 | 1,250 | 1,234 |
| 00_jd_fetch.md | 2,367 | 1,000 | 1,367 |
| project_catalog (condensed) | 12,228 | 5,500 | 6,728 |
| Base resume | 1,125 | 1,125 | 0 |
| Completion checklist (lazy) | 2,500 | 0 (until end) | 2,500 |
| Compile commands (extracted) | 2,000 | 0 (reference file) | 2,000 |
| **Total skill docs** | **~47,330** | **~19,875** | **~27,455** |

### Token consumption per run (30 API calls)

| Metric | Before | After | Savings |
|---|---|---|---|
| Base context | ~53,000 | ~30,000 | ~23,000 |
| Avg context (with growth) | ~82,000 | ~52,000 | ~30,000 |
| Tokens per run (30 calls) | ~2,460,000 | ~1,560,000 | ~900,000 |
| 4 runs | ~9,840,000 | ~6,240,000 | ~3,600,000 |
| With agent overhead (~20%) | ~12,000,000 | ~7,500,000 | ~4,500,000 |

### Projected usage after optimization

```
4 runs:  ~7.5M tokens (down from 12M)   →  38% reduction
Per run: ~1.9M tokens (down from ~3M)    →  37% reduction
```

### Quota impact (nanoGPT 60M subscription — caching does NOT reduce quota)

```
Before:  12M / 60M = 20% per 4 resumes  →  ~20 resumes/month max
After:   7.5M / 60M = 12.5% per 4 resumes →  ~32 resumes/month max
```

**~60% more resumes per month from the same quota.**

---

## Phase 7: Session Splitting per Step (Aggressive — Save ~1.5M tokens/run)

**Effort:** High (requires wrapper script or manual chaining). **Risk:** Low (each step reads previous outputs from disk). **Savings:** ~1.5M tokens per run.

### The Problem

In a single agent session, context accumulates across all 3 steps. Step 3 carries the entire history of Step 1 + Step 2 — all the ATS scoring YAML, project ranking, compile logs, audit results. This is pure overhead: Step 3 only needs `ATS_Report.yaml`, `project_info.md`, and `Job_Description.yaml` (all on disk).

### The Change

Instead of one 30-call session, run 3 separate sessions that chain via disk:

```
Session 1 (Step 1): ~10 calls, base context ~13K → reads SKILL.md + 01_doc + condensed catalog
    ↓ writes ATS_Report.yaml, Job_Description.yaml, project_info.md to disk
    ↓ session ends

Session 2 (Step 2): ~12 calls, base context ~11K → reads SKILL.md + 02_doc + selected project entries
    ↓ reads Step 1 outputs from disk (ATS_Report.yaml, project_info.md)
    ↓ writes Resume.yaml, Resume.pdf, Layout_Audit_Report.yaml, Parseability_Report.pdf
    ↓ session ends

Session 3 (Step 3): ~8 calls, base context ~5K → reads SKILL.md + 03_doc
    ↓ reads Step 1+2 outputs from disk (ATS_Report.yaml, project_info.md)
    ↓ writes Cover_Letter.yaml, Cover_Letter.pdf
    ↓ runs Obsidian sync + sort
```

### Token math

```
Single session (current):  30 calls × ~82K avg context = ~2.5M tokens
Split sessions:            10×13K + 12×20K + 8×15K = 130K + 240K + 120K = ~490K tokens
                            (with context growth per session: ~700K total)
```

**Savings: ~1.8M tokens per run.** Across 4 runs: **~7.2M tokens saved.**

### Implementation

Create a wrapper script `run_pipeline.sh` that:
1. Launches an OMP session for Step 1 with the JD text
2. Waits for Step 1 to complete (check for ATS_Report.yaml on disk)
3. Launches a new OMP session for Step 2 (reads Step 1 outputs from disk)
4. Waits for Step 2 to complete (check for Resume.pdf + Parseability_Report.yaml)
5. Launches a new OMP session for Step 3 (reads Step 1+2 outputs from disk)
6. Waits for completion, runs Obsidian sync

Each session starts with a clean context — no accumulation from previous steps.

### Combined with Phases 1-6

```
Per run with all phases:  ~700K tokens (down from ~3M)  →  77% reduction
4 runs:                   ~2.8M tokens (down from 12M)  →  77% reduction
Quota:                    2.8M / 60M = 4.7% per 4 resumes → ~85 resumes/month
```

### Risk mitigation

- Each step reads previous outputs from disk (YAML files), not from conversation history. The YAML schemas are the contract between steps.
- If a step fails, the wrapper script can re-launch just that step with the same disk inputs.
- The user can still intervene between steps (e.g., the keyword stuffing decision in Step 2).

## Implementation Order

| Phase | Effort | Tokens saved/run | Risk | Priority |
|---|---|---|---|---|
| 1: De-duplicate repeated blocks | Low | 264K | None | **P0 — do first** |
| 2: Slim SKILL.md | Medium | 360K | Low | **P0** |
| 5: Lazy loading | Low | 75K | None | **P0** |
| 3: Slim step docs | Medium | 300K | Low | **P1** |
| 6: Consolidate compile cmds | Low | 60K | None | **P1** |
| 4: Condensed catalog | Medium | 180K | Medium | **P2** |
| 7: Session splitting | High | 1,800K | Low | **P2 — biggest single win** |

### Cumulative savings

| Phases | Per run | 4 runs | Quota used | Resumes/month |
|---|---|---|---|---|
| Current (no changes) | ~3M | ~12M | 20% | ~20 |
| P1+2+5 (quick wins) | ~2M | ~8M | 13.3% | ~30 |
| P1+2+3+5+6 (all doc slimming) | ~1.6M | ~6.4M | 10.7% | ~37 |
| +P4 (condensed catalog) | ~1.4M | ~5.6M | 9.3% | ~43 |
| +P7 (session splitting) | ~0.7M | ~2.8M | 4.7% | ~85 |

### Validation

After each phase, run one test pipeline run and verify:
1. All output files are generated correctly (ATS_Report, Resume, Cover Letter, Parseability Report).
2. Parseability audit passes (100% keyword recovery, all section headers, 5/5 contact fields).
3. No hallucinated projects (all titles match catalog).
4. Resume fills exactly one page.
5. Compare token usage before/after (if the platform shows per-run usage).

### What NOT to change

- **Anti-hallucination guardrails themselves** — only de-duplicate their presentation, never weaken the rules.
- **YAML schemas** — condense the surrounding prose but keep the schema YAML blocks (they're the source of truth for output structure).
- **Python validation scripts** — these run locally and don't consume tokens; keep them as-is.
- **Renderer code** — not part of this optimization (renderers are Python, not LLM context).
- **The pipeline's 3-step architecture** — don't merge steps or change the flow; only slim the instructions.

---

## File Inventory After Optimization

```
SKILL.md                         ~3,500 tokens  (was 8,030)
00_jd_fetch.md                   ~1,000 tokens  (was 2,367)  [read only when URL provided]
01_ats_and_jd_archival.md        ~3,000 tokens  (was 5,898)  [read in Step 1]
02_resume_and_visual_audit.md    ~4,500 tokens  (was 10,698) [read in Step 2]
03_cover_letter.md               ~1,250 tokens  (was 2,484)  [read in Step 3]
99_completion_checklist.md       ~2,500 tokens  (was in SKILL.md) [read only at end]
compile_commands.md              ~1,500 tokens  (new, reference) [read when compiling]
okf/project_catalog_condensed.yaml ~5,500 tokens (was 12,228) [read in Step 1]
okf/project_catalog.yaml         ~12,228 tokens (unchanged, full) [read in Step 2 for selected projects only]
```

**Base context during Step 1:** SKILL.md + 01_doc + condensed catalog + base resume = ~13,125 tokens (was ~27,000)
**Base context during Step 2:** SKILL.md + 02_doc + full catalog (selected only) + base resume = ~10,625 tokens (was ~32,000)
**Base context during Step 3:** SKILL.md + 03_doc = ~4,750 tokens (was ~12,500)

The base context is now **step-dependent** instead of monolithic, so the agent only carries what it needs for the current step.
