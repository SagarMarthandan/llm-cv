# Pipeline Step 0: JD Fetch (URL → Job Description Text)

> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules". Only write to `okf/.jd_cache/` in this step.

## Objective
Fetch a job posting URL, extract clean JD text, validate it, and hand to Step 1. Fall back to manual paste if scraping fails.

## When to Run
**Only** when user provides a URL. If user pastes raw JD text, skip Step 0 entirely → go to Step 1.

## Inputs
- Job posting URL (any public job-board or careers page)
- Optional: `JINA_API_KEY` env var for higher Jina rate limits

## Outputs
- Clean JD text → handed to Step 1 as "pasted JD text" (Step 1 behavior unchanged)
- `source_url` → Step 1 stores in `Job_Description.yaml`
- Cache at `okf/.jd_cache/<sha1(url)>.txt` (7-day TTL)

## ATS Vendor Inference (URL → vendor)
`myworkdayjobs.com`→Workday, `personio.de`→Personio, `successfactors.eu`→SAP SuccessFactors, `greenhouse.io`→Greenhouse, `lever.co`→Lever, `taleo.net`→Taleo, `linkedin.com/jobs/*`→LinkedIn, none→`Unknown`. Vendor decides scrape strategy.

## Strategy Routing
- **JS-SPA vendors** (LinkedIn, Workday, Greenhouse, Lever, SuccessFactors, Personio): Skip `webfetch` (returns empty shell). Go straight to Jina Reader. If Jina fails → manual paste.
- **Unknown vendors** (company careers page, static HTML): Try `webfetch` first. If fails validation → Jina fallback. If Jina fails → manual paste.

## Execution

### 1. Cache Lookup
`hash = sha1(url)`. Check `okf/.jd_cache/<hash>.txt`: if exists, <7 days old, passes validation → use directly. Otherwise → scrape.

### 2. Scrape

**Strategy A — Jina Reader** (JS-SPA vendors, or fallback from failed webfetch):
```bash
# Keyless (rate-limited)
/home/sagar/Skills/llm-cv/.venv/bin/python -c "import urllib.request; req=urllib.request.Request('https://r.jina.ai/<URL>'); print(urllib.request.urlopen(req, timeout=30).read().decode('utf-8','ignore'))" > "$TEMP/jd_scrape.txt"

# With API key
/home/sagar/Skills/llm-cv/.venv/bin/python -c "import urllib.request, os; req=urllib.request.Request('https://r.jina.ai/<URL>', headers={'Authorization':'Bearer ' + os.environ.get('JINA_API_KEY', '')}); print(urllib.request.urlopen(req, timeout=30).read().decode('utf-8','ignore'))" > "$TEMP/jd_scrape.txt"
```
Jina returns clean markdown of fully rendered page. **Hard failures (no retry):** HTTP 429, 401/403, 5xx, auth wall text ("Sign in to view"), timeout → next strategy.

**Strategy B — webfetch** (static/Unknown vendors only):
Use agent's built-in `webfetch` tool. Plain HTTP GET with HTML-to-text. **Skip entirely** for JS-SPA vendors. **Hard failures:** HTTP 4xx/5xx, body <200 chars, timeout → next strategy.

### 3. Validation (JD-shape heuristic)
Text must pass ALL:
1. **Length:** >200 chars after stripping whitespace
2. **Role title:** Contains 1-6 word token sequence with ≥1 of: engineer, developer, analyst, scientist, manager, lead, architect, consultant, specialist, designer, administrator, head, director, officer, intern, working student, werkstudent, praktikant (case-insensitive)
3. **Company signal:** Company name token near top OR `company:`/`Unternehmen:`/`Firma:`/`about us`/`Über uns`
4. **JD section markers:** ≥2 of: requirements, qualifications, responsibilities, experience, skills, we are looking for, about the role, your profile, your tasks, anforderungen, profil, aufgaben, wir suchen, über die rolle, ihr profil
5. **Not login/error page:** `<form>`/`<input>`/`Sign in`/`Log in`/`404`/`403`/`Access Denied`/`Not Found` tokens <30% of word count

Pass → write to cache, hand to Step 1. Fail → next strategy or manual paste.

### 4. Final Fallback: Manual Paste
If all strategies fail/skip:
> Could not extract a JD from `<url>` (reason: `<short reason>`). Please paste the full job description text below.

Do NOT store manually-pasted text in URL cache. Only `source_url` is recorded.

## Handoff to Step 1
Proceed to Step 1 with: JD text (treated as pasted), `source_url`, detected ATS vendor. Step 1 runs unchanged.

---
**Next:** Proceed to Step 1 — read `01_ats_and_jd_archival.md`.
