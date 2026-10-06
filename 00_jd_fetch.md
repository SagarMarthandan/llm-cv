# Pipeline Step 0: JD Fetch (URL → Job Description Text)

## Objective
Extract the exact posting's JD with one primary scraper. Use backups only after failure; never load multiple scraping skills for a normal URL run.

## When to Run
Only when the user provides a URL. Pasted text and existing JD files bypass URL fetching.

## Primary: TinyFish inside the pipeline
Pass the original URL to `run_pipeline.sh --url "<URL>"` with the user's configuration flags. The pipeline invokes:

```bash
.venv/bin/python api_pipeline.py fetch --url "<URL>"
```

This runs `tinyfish fetch content get --format markdown` once. Do not pre-scrape with another tool, search for alternate postings, or route by ATS vendor. TinyFish CLI and its authentication must be available.

## Cache
Successful text is cached at `okf/.jd_cache/tinyfish-<sha1(url)>.txt` for seven days. Jina uses `jina-<sha1(url)>.txt`; legacy unprefixed cache entries are not reused. Text shorter than 200 stripped characters is rejected and not cached.

## Failure-only backup order
The launcher handles backups; the shell pipeline does not have direct access to the mounted Firecrawl MCP tool.

1. **Firecrawl:** If TinyFish fails or the returned text is not the requested JD, call the mounted `firecrawl_scrape` MCP tool once for the same URL with `formats: ["markdown"]`, `onlyMainContent: true`, and `maxAge: 0`. Do not load a separate scraping skill.
2. **Jina:** Only if Firecrawl also fails or returns unusable content, run:

   ```bash
   .venv/bin/python api_pipeline.py fetch --url "<URL>" --scraper jina
   ```

   Jina uses its Reader endpoint; `JINA_API_KEY` is optional. There is no direct-HTML fallback.
3. **Manual paste:** If all three fail, report the extraction failure and ask the user to paste the full JD.

## Backup handoff
Save successful backup text to a unique `/tmp/llm-cv-jd-<slug>.txt` file. Rerun Stage 1 with `--file` and the same configuration answers. Keep the original source URL with the archived JD. Do not cache manually pasted text under the URL.

## Content check
Verify the returned content identifies the requested company and role and includes the posting's responsibilities/requirements. Reject login pages, access-denied pages, listing pages, empty shells, and unrelated postings. Do not invent missing JD content or silently select another job.

## Handoff to Step 1
The pipeline passes the extracted text to Step 1 for ATS analysis and JD archival. Normal URL runs use TinyFish only; Firecrawl and Jina remain sequential failure-only backups.
