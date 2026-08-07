# Pipeline Step 0: JD Fetch (URL → Job Description Text)

> **READ-ONLY SKILL FILES — HARD GUARDRAIL:** This step does NOT modify any skill infrastructure files. The only files written by this step are entries inside the URL-hash cache directory `okf/.jd_cache/` (a cache of scraped JD text, keyed by URL hash, 7-day TTL). The model MUST NOT edit, patch, or modify any renderer, pipeline script, base file, or step doc. The clean JD text produced by this step is handed to Step 1 as the same "pasted JD text" input Step 1 already expects — Step 0 changes nothing about Step 1's contract.

> **AGENT EXECUTION RULES:** Follow the Tool-Call Execution Protocol in `SKILL.md` §"Agent Execution & Anti-Spinning Rules". Do not emit multi-paragraph planning prose or un-called YAML drafts before tool calls. Keep commentary to 1 sentence per action. Batch independent tool calls.

## Objective
Accept a **job posting URL** from the user, fetch the rendered page, extract the clean job description text, validate that it actually looks like a JD, and hand it to Step 1. If automated scraping fails the JD-shape validation heuristic (or hits a hard error / rate limit / login wall), fall back to asking the user to paste the JD manually.

## When to run this step
Run Step 0 **only** when the user provides a URL (or explicitly asks to "scrape this posting" / "fetch this job link"). If the user pastes raw JD text directly, **skip Step 0 entirely** and go straight to Step 1 — Step 0 is an optional pre-step, not a mandatory one.

## Inputs
- **Job posting URL** — provided by the user (any public job-board or company careers page).
- **Optional:** `JINA_API_KEY` env var for higher Jina Reader rate limits (keyless public endpoint works but is rate-limited).

## Outputs
- **Clean JD text** (string) — handed to Step 1 as the "pasted JD text" input. Step 1 does not change behavior.
- **`source_url`** (string) — stored in `Job_Description.yaml` by Step 1 for traceability (see Step 1 §"Job_Description.yaml Schema").
- **Cache entry** at `okf/.jd_cache/<sha1(url)>.txt` — the raw scraped text, with a 7-day TTL so re-runs of the same URL skip re-scraping.

## ATS Vendor Inference (URL → vendor)
Reuse the existing fingerprint map from Step 1 §"0c. ATS Vendor Inference". The vendor is detected from the URL host:
- `myworkdayjobs.com` → `Workday`
- `personio.de` / `personio.com` → `Personio`
- `successfactors.eu` / `successfactors.com` → `SAP SuccessFactors`
- `greenhouse.io` → `Greenhouse`
- `lever.co` → `Lever`
- `taleo.net` → `Taleo`
- `linkedin.com/jobs/*` → `LinkedIn`
- none matched → `Unknown`

The vendor decides which scrape strategy is viable (see "Strategy routing" below).

## Strategy routing
Known **JS-SPA vendors** (LinkedIn, Workday, Greenhouse, Lever, SuccessFactors, Personio) render their content client-side — a plain HTTP GET returns an empty shell. For these, **skip the local `webfetch` attempt entirely** and go straight to Jina Reader; if Jina fails, go straight to manual paste (the doomed `webfetch` call is skipped to avoid wasting a round-trip on a site we already know won't render server-side).

For `Unknown` vendors (a company's own careers page, a blog post, a static HTML posting), try `webfetch` first (cheap, local, no external dependency); fall back to Jina only if `webfetch` returns something that fails validation.

## Execution

### 1. Cache lookup
Compute `hash = sha1(url)` and check `okf/.jd_cache/<hash>.txt`:
- If it exists AND its mtime is less than 7 days old AND it passes the validation heuristic (see §"Validation" below) → use the cached text directly. Skip scraping. Print `JD cache hit (age: Nd)`.
- Otherwise → proceed to scrape.

### 2. Scrape (vendor-routed)

#### Strategy A — Jina Reader (JS-SPA vendors, or fallback from a failed `webfetch`)
Fetch `https://r.jina.ai/<url>` (prepend the user-supplied URL after the path prefix). If `JINA_API_KEY` is set in the environment, send it as `Authorization: Bearer $JINA_API_KEY` for higher rate limits; otherwise use the keyless public endpoint.

```bash
# Keyless (rate-limited)
/home/sagar/Skills/llm-cv/.venv/bin/python -c "import urllib.request; req=urllib.request.Request('https://r.jina.ai/<URL>'); print(urllib.request.urlopen(req, timeout=30).read().decode('utf-8','ignore'))" > "$TEMP/jd_scrape.txt"

# With API key (higher limits)
/home/sagar/Skills/llm-cv/.venv/bin/python -c "import urllib.request, os; req=urllib.request.Request('https://r.jina.ai/<URL>', headers={'Authorization':'Bearer ' + os.environ.get('JINA_API_KEY', '')}); print(urllib.request.urlopen(req, timeout=30).read().decode('utf-8','ignore'))" > "$TEMP/jd_scrape.txt"
```

Jina returns clean markdown of the fully rendered page (handles JS SPAs, cookie/consent walls, and most login walls for public postings).

**Hard-failure detection (Jina):**
- HTTP 429 (rate-limited) → Jina is blocked. Do NOT retry. Proceed to next strategy.
- HTTP 401/403 → likely a login wall. Do NOT retry. Proceed to next strategy.
- HTTP 5xx → Jina is down. Proceed to next strategy.
- Body contains `Sign in to view` / `Log in to view` / `Join now to see` / `Sign Up to view` → LinkedIn-style auth wall. Do NOT retry. Proceed to next strategy.
- Timeout (>30s) → proceed to next strategy.

#### Strategy B — local `webfetch` (static / Unknown vendors only)
Use the agent's built-in `webfetch` tool against the raw URL. This is a plain HTTP GET with HTML-to-text extraction — works for server-rendered pages, fails on JS SPAs.

**Skip Strategy B entirely** if the vendor is a known JS-SPA vendor (LinkedIn, Workday, Greenhouse, Lever, SuccessFactors, Personio) — go straight from a failed Jina attempt to manual paste. This avoids a doomed round-trip on a site we already know won't render server-side.

**Hard-failure detection (webfetch):**
- HTTP 4xx/5xx → proceed to next strategy.
- Body <200 chars after stripping → proceed to next strategy.
- Timeout → proceed to next strategy.

### 3. Validation (JD-shape heuristic)
Apply this gate to whatever text comes back from a successful scrape (Jina or webfetch). The text must pass ALL of:

1. **Length:** >200 characters after stripping whitespace.
2. **Role title:** contains a plausible job title — heuristic: a token sequence of 1-6 words containing at least one of `{engineer, developer, analyst, scientist, manager, lead, architect, consultant, specialist, designer, administrator, head, director, officer, intern, working student, werkstudent, praktikant}` (case-insensitive). If not found, FAIL.
3. **Company signal:** contains either (a) a company name token near the top of the text, OR (b) the word `company:` / `Unternehmen:` / `Firma:` / `about us` / `Über uns`. If neither, FAIL.
4. **JD section markers:** contains ≥2 of (case-insensitive):
   - `requirements`, `qualifications`, `responsibilities`, `experience`, `skills`, `we are looking for`, `about the role`, `your profile`, `your tasks`, `anforderungen`, `profil`, `aufgaben`, `wir suchen`, `über die rolle`, `ihr profil`
5. **Not a login/error page:** body must NOT be dominated by `<form>`/`<input>`/`Sign in`/`Log in`/`404`/`403`/`Access Denied`/`Not Found` tokens (i.e. these tokens must be <30% of the body's word count).

If validation PASSES → write the cleaned text to `okf/.jd_cache/<hash>.txt` (overwrite if stale), print `JD fetched via <strategy>`, and hand the text to Step 1.

If validation FAILS → print `Scrape returned non-JD content (failed validation: <which checks failed>)` and proceed to the next strategy. If no strategies remain → proceed to §"Final fallback: manual paste".

### 4. Final fallback: manual paste
If both scrape strategies fail (or were skipped for JS-SPA vendors where Jina failed), prompt the user:

> Could not automatically extract a job description from `<url>` (reason: `<short reason — e.g. "Jina rate-limited", "login wall detected", "scraped text failed JD-shape validation">`).
>
> Please paste the full job description text below and I'll continue with Step 1.

The user pastes the JD text. Hand that text to Step 1. **Do NOT store manually-pasted text in the URL cache** (it's not the scraped content) — only `source_url` is recorded in `Job_Description.yaml`.

## Handoff to Step 1
Once Step 0 has produced clean JD text (from cache, Jina, webfetch, or manual paste), proceed to Step 1 with:
- The JD text treated exactly as if the user had pasted it (Step 1's "Paste target JD text at the bottom" input).
- The `source_url` value passed forward so Step 1 can write it into `Job_Description.yaml` (see Step 1 §"Job_Description.yaml Schema" — `source_url` is an optional top-level field).
- The detected ATS vendor (from §"ATS Vendor Inference" above) passed forward so Step 1's own §"0c. ATS Vendor Inference" can reuse it without re-inferring.

Step 1 then runs unchanged.

## What this step does NOT do
- Does not modify Step 1 / Step 2 / Step 3 docs, renderers, pipeline scripts, base files, or `okf/project_catalog.yaml`.
- Does not call any ATS scoring, project ranking, or compilation — those are Step 1's job.
- Does not retry failed scrapes indefinitely — each strategy gets exactly one attempt before falling back.
- Does not silently accept noisy scraped text — the validation gate is mandatory; if it fails, we fall back rather than feeding garbage to Step 1.
- Does not store manually-pasted JD text in the URL cache.
