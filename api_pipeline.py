#!/usr/bin/env python3
"""
api_pipeline.py — Direct OpenRouter API calls for llm-cv pipeline.

Architecture: Static-First with prompt caching.
  - Large SYSTEM_PROMPT (~15K tokens) loaded once at module import, identical
    across all runs, sent as the system message with cache_control. After the
    first call, OpenRouter caches this prefix at ~10x discount.
  - Variable user message (~2-4K tokens) contains only JD, ATS report, config,
    and task-specific instructions.

Usage:
    python api_pipeline.py step1 --jd-file /tmp/jd.txt --render latex \
        --style german --source "Cold Apply" --language English
    python api_pipeline.py step2 --app-dir /path/to/app --render latex \
        --style german --language English --stuffing none --score-boost true
    python api_pipeline.py step3 --app-dir /path/to/app --render latex \
        --language English
    python api_pipeline.py fix --app-dir /path/to/app --error "parseability failed: ..."
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SKILL_DIR = Path(__file__).parent.resolve()
APPLICATIONS_DIR = Path(os.getenv("LLM_CV_APPLICATIONS_DIR", "/home/sagar/Applications"))
VENV_PYTHON = str(SKILL_DIR / ".venv" / "bin" / "python")

# ─── API Configuration ───────────────────────────────────────────────────────

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("LLM_CV_MODEL", "qwen/qwen3.8-flash")
API_TIMEOUT = int(os.getenv("LLM_CV_API_TIMEOUT", "300"))


def get_api_key() -> str:
    """Get OpenRouter API key from env or OMP config."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if key:
        return key
    try:
        import sqlite3
        db_path = Path.home() / ".omp" / "agent" / "agent.db"
        if db_path.exists():
            db = sqlite3.connect(str(db_path))
            cursor = db.cursor()
            cursor.execute("SELECT data FROM auth_credentials WHERE provider='openrouter'")
            row = cursor.fetchone()
            db.close()
            if row:
                data = json.loads(row[0])
                return data.get("key", "")
    except Exception:
        pass
    print("ERROR: No OpenRouter API key found. Set OPENROUTER_API_KEY env var.", file=sys.stderr)
    sys.exit(1)


# ─── File Reading Helpers ────────────────────────────────────────────────────

def read_file(path: Path) -> str:
    """Read a file, return empty string if not found."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"WARN: Could not read {path}: {e}", file=sys.stderr)
        return ""


def detect_archetype(jd_text: str) -> str:
    """Detect role archetype from JD text."""
    jd_lower = jd_text.lower()
    archetypes = {
        "Data Engineer": ["data engineer", "data pipeline", "etl", "data infrastructure",
                          "data platform", "data warehouse", "data lake"],
        "Data Analyst": ["data analyst", "business analyst", "analytics", "reporting",
                         "dashboard", "kpi", "business intelligence"],
        "Analytics Engineer": ["analytics engineer", "dbt", "transformation",
                               "data modeling", "sql transformation"],
        "AI Data Engineer": ["ai engineer", "ml engineer", "machine learning",
                             "llm", "rag", "ai/ml", "deep learning",
                             "nlp", "computer vision", "genai", "gen ai"],
    }
    best = "Data Engineer"
    best_score = 0
    for archetype, keywords in archetypes.items():
        score = sum(1 for kw in keywords if kw in jd_lower)
        if score > best_score:
            best_score = score
            best = archetype
    return best


def get_base_resume(language: str, archetype: str) -> str:
    """Load the base resume file for the given language and archetype."""
    lang_dir = "english" if language == "English" else "german"
    base_dir = SKILL_DIR / "okf" / "base_files" / lang_dir

    archetype_files = {
        "Data Engineer": "resume_data_engineer.md",
        "Data Analyst": "resume_data_analyst.md",
        "Analytics Engineer": "resume_analytics_engineer.md",
        "AI Data Engineer": "resume_ai_data_engineer.md",
    }

    filename = archetype_files.get(archetype, "resume.md")
    if language == "German":
        filename = filename.replace(".md", "_de.md")
        if not (base_dir / filename).exists():
            filename = "resume_de.md"

    path = base_dir / filename
    content = read_file(path)
    if not content:
        fallback = "resume.md" if language == "English" else "resume_de.md"
        content = read_file(base_dir / fallback)
    return content


def get_nearest_city(job_location: str) -> str:
    """Get nearest candidate city using config.py."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", SKILL_DIR / "config.py")
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        city = config.nearest_candidate_city(job_location)
        return city or "Kiel, Germany"
    except Exception:
        return "Kiel, Germany"


# ─── Static System Prompt (cached across all calls) ──────────────────────────

def _load_system_prompt() -> str:
    """Build the large static system prompt with step docs, schemas, and golden examples.

    This is loaded ONCE at module import and sent as the system message for every
    API call. Identical bytes every time → OpenRouter caches the prefix → ~10x
    input token discount after the first call.
    """
    # Load step docs
    step2_doc = read_file(SKILL_DIR / "02_resume_and_visual_audit.md")
    step3_doc = read_file(SKILL_DIR / "03_cover_letter.md")
    score_boost_doc = read_file(SKILL_DIR / "prompts" / "score_boost.md")

    # Load golden examples (John Deere — interview-winning application)
    golden_resume = read_file(
        Path("/home/sagar/Applications/2026/08/24/"
             "John Deere — Intern Dealer Development - Business Intelligence and Data visualization (m-f-d)"
             "/Resume.yaml"))
    golden_cover = read_file(
        Path("/home/sagar/Applications/2026/08/24/"
             "John Deere — Intern Dealer Development - Business Intelligence and Data visualization (m-f-d)"
             "/Cover_Letter.yaml"))

    return f"""You are an expert ATS resume optimization system for a German job market candidate (Sagar Marthandan).
You output ONLY valid YAML or markdown as instructed. No explanations, no commentary outside the requested output.
Follow schemas exactly. Quote all string values containing colons, dashes, or special characters.
Use block scalars (|) for multi-line content. Never fabricate metrics, projects, or skills.

# GUARDRAILS (NON-NEGOTIABLE)

## Anti-Hallucination
1. Projects: ONLY the 15 in the provided catalog. No inventing/splitting/merging.
2. Metrics: From catalog key_metrics or base resume bullets only. No fabrication.
3. Technologies: Only from catalog, base resume, or JD required skills.
4. Company & Role: Verbatim from JD.
5. Employment History: Dates/titles from base resume are immutable.
6. Repo URLs: Verbatim from catalog repo_url field. If empty, omit.

## YAML Safety
1. Quote all string values containing : - # > | {{ }} [] or quotes.
2. Use block scalars (|) for multi-line content.
3. Never paste raw text into YAML without quoting or block-scaling.

## Stop-Slop Writing Rules
1. Strict active voice — every sentence leads with action.
2. No adverbs ending in -ly (successfully, effectively, genuinely, actually, really).
3. No em-dashes (—) in prose. Use commas or periods. --- separators in project names are OK.
4. No throat-clearing ("at its core", "it is worth noting", "the reality is").
5. No AI fluff ("passionate", "thrilled", "excited", "delighted", "eager").

# RESUME CONSTRAINTS (NON-NEGOTIABLE)

1. Project summaries: Exactly 3 bullets per project, each 60-80 chars. Total 180-240 chars per project.
   EVERY bullet must contain at least one quantitative metric (a number: %, count, latency, size, duration).
   A bullet without a number is a FAIL. If the catalog has no metric for a bullet, use a different bullet.
   For German style project_bullets: 3 bullets per project dict, each 60-80 chars.
   For US style projects: 3 bullets per project, each 60-80 chars.
4. IBM: 4-6 bullets from the base resume. Pick the most JD-relevant. Available bullets include:
   CICS/Db2 maintenance, MQ monitoring, SMF capacity planning, 15% overhead reduction,
   team lead of 5 for 2 years (project management), ITIL V3 Foundation (IBM certified).
   Use 4 by default, add 5th-6th if needed for page fill. Staff 4: exactly 2 bullets.
5. Technical skills: JD-relevant only (anti-stuffing). Prioritize JD-required -> core project tools -> adjacent strengths.
6. Project tools: 3-5 most JD-relevant per project.
7. Project names: SHORTEN to under 50 chars. Drop subtitles after colons.
   BAD: "Ergast Formula 1 Data Engineering Mini Project: Databricks Medallion Architecture"
   GOOD: "F1 Databricks Medallion Pipeline"
8. Section order (US Style): Summary -> Technical Skills -> Projects -> Professional Experience -> Education -> Languages
   (US style: projects are a SEPARATE top-level `projects:` section in the YAML)
9. Section order (German Style): Summary -> Professional Experience -> Education -> Technical Skills -> Languages
   (German style: NO separate `projects:` section. Projects go as `project_bullets` under the
   "Independent Data Engineering & Professional Development" experience entry. Do NOT include
   a top-level `projects:` key in German style YAML.)
10. PAGE FILL (CRITICAL): Content must fill the ENTIRE text area between margins, top to bottom.
    The renderer uses 0.4in margins on A4. If content stops 15-20% short of the bottom margin,
    the resume looks unfinished. Fill the page by adding MORE CONTENT, not longer prose:
    a) Add 5-6 technical_skills categories (not 4) with 5-7 skills each (not 4-5).
    b) Add a 5th project from selected_projects.yaml if 4 projects leave visible empty space.
    c) Add a 5th IBM bullet (max 105 chars) if still short.
    d) NEVER extend bullet prose to fill space. Long bullets are an eyesore for recruiters.
    Keep bullets at 60-80 chars each. Fill via quantity of sections, not length of text.
11. Anti-hallucination: only projects from selected_projects.yaml, metrics from catalog key_metrics.
12. 3-5 projects. Default to 4. Add a 5th ONLY when needed for page fill (see rule 10).

# GERMAN STYLE INDEPENDENT ENTRY FORMAT (CRITICAL)

The Independent entry uses project_bullets (dicts), NOT strings:
- company: "Independent Data Engineering & Professional Development"
- location: "Remote" or closest_candidate_location
- date: "Jan 2023 – April 2025"
- project_bullets: 3-5 JD-aligned projects, each a DICT with:
    - name: "[Short project name — keep under 50 chars, no subtitle after colon]"
    - repo_url: "[from selected_projects.yaml]"
    - bullets: [3 short outcome bullets, each 60-80 chars, one metric per bullet]
- bullets: single "other tools" bullet after project bullets
- Do NOT include a top-level `projects:` section. All projects live inside this entry.

# SCORE-BOOST MEASURES (always active)

{score_boost_doc}

# COVER LETTER RULES

1. Match target JD language exactly.
2. Geschäftsbrief layout: Sender -> Recipient -> Date -> Subject -> Salutation -> Body -> Closing.
3. English: max 4 paragraphs, 250-320 words. German: max 4 paragraphs, 180-240 words.
4. Ground every tech skill in SPECIFIC metrics from project_info. Don't paraphrase the JD — show your work.
   BAD: "I bring experience in data pipelines and cloud platforms."
   GOOD: "I modeled a star schema with 3 fact and 4 dimension tables in Power BI, including DAX time intelligence for 90-day rolling profit."
5. No resume rehash — cover letter carries info the resume does not. Focus on HOW you did things, not WHAT.
6. Paragraph structure:
   - P1: Hook — link a specific JD requirement to a specific project. State what you'd do in first 90 days.
   - P2: Deep dive project 1 — specific metrics, specific tools, specific decisions.
   - P3: Deep dive project 2 — different angle, different metrics.
   - P4: B1 German (planning B2), GitHub portfolio, availability, archetype-conditional (LLMs/RAG only for AI roles).
7. No raw URLs in prose — refer to GitHub in plain language.
8. If Referral/LinkedIn Connection, mention weak_tie_contact in paragraph 1.
9. German conventions: real umlauts (not ae/oe/ue), "Mit freundlichen Grüßen" without comma,
    date "City, DD.MM.YYYY" numeric, sender "city, Deutschland".
10. Subject uses exact job title from Job_Description.yaml.

# STEP 2 DOC (full reference)

{step2_doc}

# STEP 3 DOC (full reference)

{step3_doc}

# GOLDEN EXAMPLE — RESUME (interview-winning application, German style, English language)
# This is what "good" looks like. Match this format: 3 bullets per project, short names,
# specific metrics, no padding. NOTE: This example has 4 projects and 4 skills categories.
# For your run, use 5-6 skills categories and add a 5th project if the page has empty space.

{golden_resume}

# GOLDEN EXAMPLE — COVER LETTER (same application, 4 tight paragraphs, specific metrics)

{golden_cover}
"""


SYSTEM_PROMPT = _load_system_prompt()


# ─── API Call ────────────────────────────────────────────────────────────────

def call_openrouter(prompt: str, system: str = None, model: str = None,
                    max_tokens: int = 16000, temperature: float = 0.3,
                    max_retries: int = 4) -> dict:
    """Make a single API call to OpenRouter with retry on 429.

    The system message is sent with cache_control to enable prompt caching.
    Returns the full response dict.
    """
    api_key = get_api_key()
    model = model or DEFAULT_MODEL
    system = system or SYSTEM_PROMPT

    # System message with cache_control for prompt caching.
    # Content as array of objects to attach cache_control to the static prefix.
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        },
        {"role": "user", "content": prompt}
    ]

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # Disable reasoning for speed — pipeline steps are structured tasks
        "reasoning": {"enabled": False},
        "include_reasoning": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/SagarMarthandan/llm-cv",
        "X-Title": "llm-cv pipeline",
    }

    data = json.dumps(payload).encode("utf-8")

    system_tokens = len(system) // 4
    print(f"[api] Calling {model} (max_tokens={max_tokens}, temp={temperature}, "
          f"system={system_tokens:,} tokens)...", file=sys.stderr)

    start = time.time()
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < max_retries:
                wait = 2 ** attempt + 1
                print(f"[api] HTTP 429 (rate limited). Retrying in {wait}s (attempt {attempt+1}/{max_retries})...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"[api] HTTP {e.code}: {body[:500]}", file=sys.stderr)
            raise
        except Exception as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"[api] Error: {e}. Retrying in {wait}s (attempt {attempt+1}/{max_retries})...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"[api] Error: {e}", file=sys.stderr)
            raise
    else:
        raise RuntimeError(f"API call failed after {max_retries + 1} attempts")

    elapsed = time.time() - start
    usage = result.get("usage", {})
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost = usage.get("cost", 0)
    cache_pct = (cached / prompt_tokens * 100) if prompt_tokens else 0
    print(f"[api] Response in {elapsed:.1f}s — "
          f"prompt={prompt_tokens:,}, "
          f"completion={completion_tokens:,}, "
          f"cached={cached:,} ({cache_pct:.0f}%), "
          f"cost=${cost:.4f}", file=sys.stderr)

    return result


def extract_yaml_from_response(response: dict) -> str:
    """Extract YAML content from the API response."""
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    # Try to extract YAML from code blocks
    yaml_match = re.search(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)
    if yaml_match:
        return yaml_match.group(1).strip()

    # Try to extract from first --- to end
    yaml_match = re.search(r'^---\s*\n(.*)', content, re.DOTALL | re.MULTILINE)
    if yaml_match:
        return yaml_match.group(1).strip()

    # If content looks like YAML already (starts with a key:)
    if re.match(r'^[a-zA-Z_]+:\s', content):
        return content.strip()

    # Fallback: return the whole content
    return content.strip()


def extract_markdown_from_response(response: dict) -> str:
    """Extract markdown content from the API response."""
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    md_match = re.search(r'```(?:markdown|md)?\s*\n(.*?)```', content, re.DOTALL)
    if md_match:
        return md_match.group(1).strip()
    return content.strip()


def validate_yaml(yaml_text: str) -> bool:
    """Validate YAML using the venv python."""
    import subprocess
    try:
        proc = subprocess.run(
            [VENV_PYTHON, "-c", f"import yaml; yaml.safe_load(open('/dev/stdin'))"],
            input=yaml_text, capture_output=True, text=True, timeout=10
        )
        return proc.returncode == 0
    except Exception:
        return False


def write_yaml_file(path: Path, yaml_text: str) -> bool:
    """Write YAML to file and validate it."""
    path.write_text(yaml_text, encoding="utf-8")
    if validate_yaml(yaml_text):
        print(f"[ok] Wrote {path.name} ({len(yaml_text)} bytes, valid YAML)", file=sys.stderr)
        return True
    else:
        print(f"[warn] Wrote {path.name} but YAML validation failed", file=sys.stderr)
        return False


# ─── Prompt Builders (variable suffix only — system prompt is static) ────────

def build_step1_prompt(jd_text: str, render_mode: str, resume_style: str,
                       app_source: str, language: str, weak_tie: str = "") -> str:
    """Build the Step 1 variable suffix: ATS analysis + JD archival + project ranking."""

    catalog = read_file(SKILL_DIR / "okf" / "project_catalog_condensed.yaml")
    archetype = detect_archetype(jd_text)
    base_resume = get_base_resume(language, archetype)

    loc_match = re.search(r'(?:location|ort|standort|city)[:\s]+([^\n,]+)', jd_text, re.IGNORECASE)
    job_location = loc_match.group(1).strip() if loc_match else ""
    nearest_city = get_nearest_city(job_location) if job_location else "Kiel, Germany"

    return f"""# TASK: ATS Analysis, JD Archival & Project Ranking

Execute Step 1 of the llm-cv pipeline. Analyze the JD, score the base resume, rank projects, and output THREE files.

## Configuration
- render_mode: {render_mode}
- resume_style: {resume_style}
- application_source: "{app_source}"
- language: "{language}"
- weak_tie_contact: "{weak_tie}"
- closest_candidate_location: "{nearest_city}"

## Input: Job Description
{jd_text}

## Input: Base Resume (archetype: {archetype})
{base_resume}

## Input: Project Catalog (15 projects, condensed — no bullets)
{catalog}

## Instructions

1. Detect role archetype from JD (Data Engineer, Data Analyst, Analytics Engineer, AI Data Engineer).
2. Score base resume against JD using 4-category ATS matrix (25pts each, 100 total):
   - keywords_and_terminology, experience_relevance, technical_skills, soft_skills_and_language
3. Extract skill_gaps (JD-required skills not in resume or projects).
4. Build improvement_blueprint (bullet density audit, project swap directive, keyword inventory, tech skills tuning, quantified outcomes).
5. Archive JD into clean YAML sections (overview, requirements, responsibilities, stack).
6. Rank top 6 projects from catalog by: technology overlap, transferable skills, business-problem match, archetype fit, complexity, reframing potential.
7. Write project_info.md with all 6 ranked projects.

## Output Format

Output THREE YAML/Markdown blocks, each wrapped in code fences with a clear header:

### FILE 1: ATS_Report.yaml
```yaml
type: ats_report
company: "[Company Name]"
position: "[Job Position Title]"
render_mode: "{render_mode}"
resume_style: "{resume_style}"
language: "{language}"
closest_candidate_location: "{nearest_city}"
ats_vendor: "[Workday/Personio/SAP SuccessFactors/Greenhouse/Lever/Taleo/Unknown]"
application_source: "{app_source}"
weak_tie_contact: {('null' if not weak_tie else f'"{weak_tie}"')}
role_archetype:
  primary: "[Archetype]"
  archetype_rationale: "[One sentence]"
ats_score_matrix:
  keywords_and_terminology: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  experience_relevance: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  technical_skills: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  soft_skills_and_language: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  total_score: 0
formatting_quality:
  verdict: "Excellent"
  notes: ""
  suggestions: []
core_score_detractors: []
skill_gaps: []
placement_breakdown:
  keywords: []
improvement_blueprint:
  target_language_confirmation: "{language}"
  bullet_point_density_audit: []
  project_swap_directive:
    remove_projects: []
    add_projects: []
    volume_constraint_check: "3 projects selected"
  keyword_inventory:
    hard_skills: []
    methodologies: []
    domain_terms: []
  technical_skills_tuning:
    add: []
    remove: []
  quantified_outcomes: []
  ats_threshold_calibration:
    meets_target: false
    score_gate_verdict: "REVIEW"
    remedy_suggestions: []
```

### FILE 2: Job_Description.yaml
```yaml
type: job_description
company: "[Company Name]"
position: "[Job Position Title]"
location: "[Job Location]"
sections:
  - title: "Core Role Overview & Context"
    content: "[Overview paragraph]"
  - title: "Target Profile Requirements"
    bullets: ["[Requirement]"]
  - title: "Primary Responsibilities"
    bullets: ["[Responsibility]"]
  - title: "Tech Stack & Tooling"
    bullets: ["[Tool/Skill]"]
```

### FILE 3: project_info.md
```markdown
# Tailored Project Portfolio

# [Project Title]
[Description from catalog]
Problem: [business_problem]
Metrics: [key_metrics — cite verbatim]
Tech: [technologies]
Archetypes: [archetypes]
Repo: [repo_url]
[First 2 bullets from catalog]
<!-- LLM Rank: [rank], Reason: [one sentence] -->

Repeat for all 6 projects.
```

## OUTPUT NOW
Output all three files. Do NOT ask questions. Do NOT explain. Just output the three code blocks."""


def build_step2_prompt(app_dir: Path, render_mode: str, resume_style: str,
                       language: str, stuffing: str, user_skills: str,
                       score_boost: str, initial_score: int) -> str:
    """Build the Step 2 variable suffix: Resume writer + ATS rescoring."""

    ats_report = read_file(app_dir / "ATS_Report.yaml")
    selected_projects = read_file(app_dir / "selected_projects.yaml")
    job_desc = read_file(app_dir / "Job_Description.yaml")

    archetype = "Data Engineer"
    arch_match = re.search(r'primary:\s*"?([^"\n]+)"?', ats_report)
    if arch_match:
        archetype = arch_match.group(1).strip()

    lang_dir = "english" if language == "English" else "german"
    base_resume = get_base_resume(language, archetype)

    keyword_stuffing = "false"
    if stuffing in ("all", "selective"):
        keyword_stuffing = "true"

    # Build the schema section based on style
    if resume_style == "german":
        schema_section = f"""
## Resume.yaml Schema (German Style — NO top-level projects: section)
type: resume
language: "{language}"
render_mode: "{render_mode}"
resume_style: "{resume_style}"
resume_variation: "Balanced"
keyword_stuffing: {keyword_stuffing}
user_directed_skills: [{('' if not user_skills else f'"{user_skills}"')}]
contact_info:
  name: "SAGAR MARTHANDAN"
  location: "[from ATS_Report closest_candidate_location]"
  phone: "+49 176 74138359"
  email: "sagar.marthandan@yahoo.com"
  linkedin: "linkedin.com/in/sagarmarthandan"
  github: "github.com/SagarMarthandan"
  visa: "Authorized to work in Germany"
  availability: "Immediately available"
summary: "[2 lines, <=200 chars EN / <=170 DE, no tool names]"
technical_skills:
  - category: "[Category 1]"
    skills: ["[5-7 skills]"]
  - category: "[Category 2]"
    skills: ["[5-7 skills]"]
  - category: "[Category 3]"
    skills: ["[5-7 skills]"]
  - category: "[Category 4]"
    skills: ["[5-7 skills]"]
  - category: "[Category 5]"
    skills: ["[5-7 skills]"]
  - category: "[Category 6 — add only if needed for page fill]"
    skills: ["[5-7 skills]"]
professional_experience:
  - company: "Independent Data Engineering & Professional Development"
    location: "Remote"
    date: "Jan 2023 – April 2025"
    title: "Data Engineer"
    project_bullets:
      - name: "[Short name under 50 chars]"
        repo_url: "[from selected_projects.yaml]"
        bullets:
          - "[Bullet 1: outcome + metric, 60-80 chars]"
          - "[Bullet 2: outcome + metric, 60-80 chars]"
          - "[Bullet 3: outcome + metric, 60-80 chars]"
      - name: "[Short name under 50 chars]"
        repo_url: "[from selected_projects.yaml]"
        bullets:
          - "[3 bullets per project]"
          - "[3 bullets per project]"
          - "[3 bullets per project]"
      - name: "[Short name under 50 chars]"
        repo_url: "[from selected_projects.yaml]"
        bullets:
          - "[3 bullets per project]"
          - "[3 bullets per project]"
          - "[3 bullets per project]"
      - name: "[Short name under 50 chars]"
        repo_url: "[from selected_projects.yaml]"
        bullets:
          - "[3 bullets per project]"
          - "[3 bullets per project]"
          - "[3 bullets per project]"
      - name: "[5th project — add ONLY if 4 projects leave empty space at bottom]"
        repo_url: "[from selected_projects.yaml]"
        bullets:
          - "[3 bullets per project]"
          - "[3 bullets per project]"
          - "[3 bullets per project]"
    bullets:
      - "[Other tools: single bullet listing additional technologies]"
  - company: "IBM India Private Ltd"
    location: "[City]"
    date: "[MM/YYYY – MM/YYYY]"
    title: "[Title]"
    bullets: ["[4-6 bullets from base resume, <=105 chars each. Add 5th-6th if needed for page fill]"]
  - company: "Staff 4 Cruise"
    location: "[City]"
    date: "[MM/YYYY – MM/YYYY]"
    title: "[Title]"
    bullets: ["[exactly 2 bullets, <=105 chars each]"]
education:
  - degree: "[Degree]"
    university: "[University]"
    date: "[MM/YYYY or 'present']"
languages: ["[Language (Level)]"]
"""
    else:
        schema_section = f"""
## Resume.yaml Schema (US Style — projects as separate top-level section)
type: resume
language: "{language}"
render_mode: "{render_mode}"
resume_style: "{resume_style}"
resume_variation: "Balanced"
keyword_stuffing: {keyword_stuffing}
user_directed_skills: [{('' if not user_skills else f'"{user_skills}"')}]
contact_info:
  name: "SAGAR MARTHANDAN"
  location: "[from ATS_Report closest_candidate_location]"
  phone: "+49 176 74138359"
  email: "sagar.marthandan@yahoo.com"
  linkedin: "linkedin.com/in/sagarmarthandan"
  github: "github.com/SagarMarthandan"
  visa: "Authorized to work in Germany"
  availability: "Immediately available"
summary: "[2 lines, <=200 chars EN / <=170 DE, no tool names]"
technical_skills:
  - category: "[Category 1]"
    skills: ["[5-7 skills]"]
  - category: "[Category 2]"
    skills: ["[5-7 skills]"]
  - category: "[Category 3]"
    skills: ["[5-7 skills]"]
  - category: "[Category 4]"
    skills: ["[5-7 skills]"]
  - category: "[Category 5]"
    skills: ["[5-7 skills]"]
  - category: "[Category 6 — add only if needed for page fill]"
    skills: ["[5-7 skills]"]
projects:
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[Bullet 1: outcome + metric, 60-80 chars]"
      - "[Bullet 2: outcome + metric, 60-80 chars]"
      - "[Bullet 3: outcome + metric, 60-80 chars]"
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
  - name: "[5th project — add ONLY if 4 projects leave empty space]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
professional_experience:
  - company: "[Company]"
    location: "[City]"
    date: "[MM/YYYY – MM/YYYY]"
    title: "[Title]"
    bullets: ["[4-6 bullets from base resume, <=105 chars each. Add 5th-6th if needed for page fill]"]
languages: ["[Language (Level)]"]
"""

    return f"""# TASK: Resume Rewrite & ATS Rescoring

Write a tailored Resume.yaml for this job application.

## Configuration
- render_mode: {render_mode}
- resume_style: {resume_style}
- language: "{language}"
- keyword_stuffing: {keyword_stuffing}
- user_directed_skills: "{user_skills}"
- score_boost_mode: {score_boost}
- initial_ats_score: {initial_score}

## Input: ATS Report (from Step 1)
{ats_report}

## Input: Selected Projects (6 ranked projects with full bullets)
{selected_projects}

## Input: Job Description (archived)
{job_desc}

## Input: Base Resume (archetype: {archetype})
{base_resume}

{schema_section}

## Post-Rewrite ATS Rescoring (MANDATORY)
After writing Resume.yaml, also output a post_rewrite_ats_score block:
- Re-run 4-category ATS matrix on the final resume
- Calculate score_delta (post - pre)
- Set score_gate_verdict (PROCEED if >=85, HOLD if <85)
- If score_boost is active, use the itemized scoring rubric (Measure 4) from the system prompt

## post_rewrite_ats_score (append to ATS_Report.yaml)
```yaml
post_rewrite_ats_score:
  ats_score_matrix:
    keywords_and_terminology: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    experience_relevance: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    technical_skills: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    soft_skills_and_language: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    total_score: 0
  score_delta: 0
  formatting_quality:
    verdict: "Excellent"
    notes: ""
    suggestions: []
  score_gate_verdict: "PROCEED"
  remaining_gaps: []
```

## OUTPUT NOW

Output TWO code blocks:

### FILE 1: Resume.yaml
```yaml
[full Resume.yaml content]
```

### FILE 2: post_rewrite_ats_score block (to append to ATS_Report.yaml)
```yaml
[post_rewrite_ats_score block only — will be appended to existing ATS_Report.yaml]
```

Do NOT ask questions. Do NOT explain. Just output the two code blocks."""


def build_step3_prompt(app_dir: Path, render_mode: str, language: str) -> str:
    """Build the Step 3 variable suffix: Cover letter writer."""

    ats_report = read_file(app_dir / "ATS_Report.yaml")
    job_desc = read_file(app_dir / "Job_Description.yaml")
    project_info = read_file(app_dir / "project_info.md")

    return f"""# TASK: Cover Letter Generation

Write a formal cover letter (Cover_Letter.yaml) grounded in project metrics.

## Configuration
- render_mode: {render_mode}
- language: "{language}"

## Input: ATS Report
{ats_report}

## Input: Job Description
{job_desc}

## Input: Project Info (ranked projects with metrics)
{project_info}

## Cover_Letter.yaml Schema
```yaml
type: cover_letter
render_mode: "{render_mode}"
language: "{language}"
sender:
  name: "SAGAR MARTHANDAN"
  address: "[closest_candidate_location from ATS_Report]"
  phone: "+49 176 74138359"
  email: "sagar.marthandan@yahoo.com"
recipient:
  company: "[Company Name]"
  department: "Hiring Team"
  address: "[Company Address from JD, or company name + city]"
date: "[Closest City], [Date]"
subject: "Bewerbung als [Title] / Application for [Title]"
salutation: "Sehr geehrte Damen und Herren, / Dear Hiring Team,"
paragraphs:
  - "[P1: Hook linking portfolio to role]"
  - "[P2: Deep dive project 1 with metrics]"
  - "[P3: Deep dive project 2 with metrics]"
  - "[P4: B1 German, LLMs/RAG if archetype, availability]"
closing: "Mit freundlichen Grüßen, / Sincerely,"
signature_image: "okf/SAGAR_MARTHANDAN_signature.png"
```

## OUTPUT NOW

Output ONE code block:

### FILE: Cover_Letter.yaml
```yaml
[full Cover_Letter.yaml content]
```

Do NOT ask questions. Do NOT explain. Just output the code block."""


def build_fix_prompt(app_dir: Path, error_msg: str, language: str) -> str:
    """Build a fix prompt for parseability failures."""

    resume_yaml = read_file(app_dir / "Resume.yaml")

    fix_instructions = ""
    if "summary" in error_msg.lower() and "char" in error_msg.lower():
        cur_match = re.search(r'[Ss]ummary:?\s*(\d+)\s*chars?\s*\(limit:?\s*(\d+)\)', error_msg)
        if cur_match:
            current, limit = int(cur_match.group(1)), int(cur_match.group(2))
            fix_instructions = f"""
## SPECIFIC FIX REQUIRED
The summary is {current} chars but the limit is {limit} chars. You MUST trim it by at least {current - limit + 5} chars.
Rewrite the summary to be under {limit} chars. Remove adjectives, condense phrasing, keep the core message.
Count the characters carefully before outputting. The summary must be <= {limit} characters."""

    if "project" in error_msg.lower() and "char" in error_msg.lower():
        proj_match = re.search(r'(\d+)\s*chars?\s*\(limit:?\s*(\d+)\)', error_msg)
        if proj_match:
            current, limit = int(proj_match.group(1)), int(proj_match.group(2))
            fix_instructions = f"""
## SPECIFIC FIX REQUIRED
A project summary is {current} chars but the limit is {limit} chars. Trim it by at least {current - limit + 5} chars.
Shorten bullet text while keeping metrics and technologies. Count carefully."""

    if "yaml_to_pdf" in error_msg.lower() or "tex-only" in error_msg.lower():
        fix_instructions = """
## SPECIFIC FIX REQUIRED
The YAML-to-LaTeX renderer failed. This usually means a schema mismatch.
Check that:
1. For German style: projects are under professional_experience as project_bullets (NOT a separate projects section)
2. For US style: projects are a separate top-level section
3. All required fields are present (contact_info, summary, technical_skills, professional_experience, education, languages)
4. No unquoted special characters in YAML values"""

    return f"""# TASK: Fix Resume YAML

The resume YAML failed a compilation check. Fix the issue and output the corrected YAML.

## Error
{error_msg}
{fix_instructions}

## Current Resume.yaml
{resume_yaml}

## Rules
- Fix ONLY the reported issue. Do NOT rewrite the entire resume.
- Keep all project names, metrics, and structure the same.
- If the issue is a keyword miss, de-parenthesize skill strings or remove special characters.
- If the issue is char count overflow, trim text to fit the limit. Count characters carefully.
- If the issue is a schema error, fix the YAML structure to match the expected format.
- Never change fonts or LaTeX preamble.

## OUTPUT NOW
Output the corrected Resume.yaml in a single code block:
```yaml
[corrected Resume.yaml]
```"""


# ─── Step Execution ──────────────────────────────────────────────────────────

def run_step1(args):
    """Execute Step 1: ATS analysis + JD archival + project ranking."""
    jd_text = read_file(Path(args.jd_file)) if args.jd_file else args.jd_text
    if not jd_text:
        print("ERROR: No JD text provided", file=sys.stderr)
        sys.exit(1)

    prompt = build_step1_prompt(
        jd_text=jd_text,
        render_mode=args.render,
        resume_style=args.style,
        app_source=args.source,
        language=args.language,
        weak_tie=args.weak_tie or "",
    )

    response = call_openrouter(prompt, max_tokens=16000)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)
    md_blocks = re.findall(r'```(?:markdown|md)?\s*\n(.*?)```', content, re.DOTALL)

    if not yaml_blocks:
        print("ERROR: No YAML blocks found in response", file=sys.stderr)
        print(f"Response preview: {content[:500]}", file=sys.stderr)
        sys.exit(1)

    ats_yaml = yaml_blocks[0].strip()

    company = ""
    position = ""
    company_match = re.search(r'^company:\s*"?([^"\n]+)"?\s*$', ats_yaml, re.MULTILINE)
    position_match = re.search(r'^position:\s*"?([^"\n]+)"?\s*$', ats_yaml, re.MULTILINE)
    if company_match:
        company = company_match.group(1).strip()
    if position_match:
        position = position_match.group(1).strip()

    if not company or not position:
        print("ERROR: Could not extract company/position from ATS_Report.yaml", file=sys.stderr)
        sys.exit(1)

    safe_company = company.replace("/", "")
    safe_position = position.replace("/", "")
    app_dir = APPLICATIONS_DIR / f"{safe_company} — {safe_position}"
    app_dir.mkdir(parents=True, exist_ok=True)

    write_yaml_file(app_dir / "ATS_Report.yaml", ats_yaml)

    if len(yaml_blocks) >= 2:
        write_yaml_file(app_dir / "Job_Description.yaml", yaml_blocks[1].strip())

    project_info_content = ""
    for block in md_blocks:
        if "Tailored Project Portfolio" in block or "LLM Rank" in block:
            project_info_content = block.strip()
            break

    if not project_info_content:
        md_match = re.search(r'# Tailored Project Portfolio.*?(?=```|$)', content, re.DOTALL)
        if md_match:
            project_info_content = md_match.group(0).strip()

    if project_info_content:
        (app_dir / "project_info.md").write_text(project_info_content, encoding="utf-8")
        print(f"[ok] Wrote project_info.md ({len(project_info_content)} bytes)", file=sys.stderr)
    else:
        print("[warn] project_info.md not found in response", file=sys.stderr)

    print(str(app_dir))
    return 0


def run_step2(args):
    """Execute Step 2: Resume writer + ATS rescoring."""
    app_dir = Path(args.app_dir)
    if not app_dir.exists():
        print(f"ERROR: App dir not found: {app_dir}", file=sys.stderr)
        sys.exit(1)

    prompt = build_step2_prompt(
        app_dir=app_dir,
        render_mode=args.render,
        resume_style=args.style,
        language=args.language,
        stuffing=args.stuffing,
        user_skills=args.user_skills or "",
        score_boost=args.score_boost,
        initial_score=int(args.initial_score or 0),
    )

    response = call_openrouter(prompt, max_tokens=16000)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)

    if not yaml_blocks:
        print("ERROR: No YAML blocks found in response", file=sys.stderr)
        print(f"Response preview: {content[:500]}", file=sys.stderr)
        sys.exit(1)

    write_yaml_file(app_dir / "Resume.yaml", yaml_blocks[0].strip())

    if len(yaml_blocks) >= 2:
        post_score_yaml = yaml_blocks[1].strip()
        ats_path = app_dir / "ATS_Report.yaml"
        existing = read_file(ats_path)
        if existing and "post_rewrite_ats_score" not in existing:
            appended = existing.rstrip() + "\n\n" + post_score_yaml + "\n"
            write_yaml_file(ats_path, appended)
        elif existing and "post_rewrite_ats_score" in existing:
            pattern = r'post_rewrite_ats_score:.*$'
            replaced = re.sub(pattern, post_score_yaml, existing, flags=re.DOTALL)
            write_yaml_file(ats_path, replaced)

    print("STEP 2 COMPLETE")
    return 0


def run_step3(args):
    """Execute Step 3: Cover letter writer."""
    app_dir = Path(args.app_dir)
    if not app_dir.exists():
        print(f"ERROR: App dir not found: {app_dir}", file=sys.stderr)
        sys.exit(1)

    prompt = build_step3_prompt(
        app_dir=app_dir,
        render_mode=args.render,
        language=args.language,
    )

    response = call_openrouter(prompt, max_tokens=8000)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)

    if not yaml_blocks:
        print("ERROR: No YAML blocks found in response", file=sys.stderr)
        print(f"Response preview: {content[:500]}", file=sys.stderr)
        sys.exit(1)

    write_yaml_file(app_dir / "Cover_Letter.yaml", yaml_blocks[0].strip())

    print("STEP 3 COMPLETE")
    return 0


def run_fix(args):
    """Execute a fix pass on Resume.yaml."""
    app_dir = Path(args.app_dir)
    prompt = build_fix_prompt(app_dir, args.error, args.language)

    response = call_openrouter(prompt, max_tokens=16000)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)
    if yaml_blocks:
        write_yaml_file(app_dir / "Resume.yaml", yaml_blocks[0].strip())
        print("FIX COMPLETE")
    else:
        print("ERROR: No YAML in fix response", file=sys.stderr)
        sys.exit(1)
    return 0


# ─── URL Fetch ──────────────────────────────────────────────────────────────

def fetch_jd_from_url(url: str) -> str:
    """Fetch JD text from URL using Jina Reader."""
    import hashlib
    cache_dir = SKILL_DIR / "okf" / ".jd_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(url.encode()).hexdigest()
    cache_path = cache_dir / f"{url_hash}.txt"

    if cache_path.exists():
        import time as _time
        age = _time.time() - cache_path.stat().st_mtime
        if age < 7 * 86400:
            cached = cache_path.read_text(encoding="utf-8")
            if len(cached) > 200:
                print(f"[fetch] Cache hit ({len(cached)} bytes, {age/3600:.0f}h old)", file=sys.stderr)
                return cached

    jina_url = f"https://r.jina.ai/{url}"
    print(f"[fetch] Fetching via Jina Reader: {url}", file=sys.stderr)
    try:
        req = urllib.request.Request(jina_url, headers={
            "Authorization": f"Bearer {os.getenv('JINA_API_KEY', '')}",
        } if os.getenv("JINA_API_KEY") else {})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[fetch] Jina Reader failed: {e}", file=sys.stderr)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except Exception as e2:
            print(f"[fetch] Direct fetch also failed: {e2}", file=sys.stderr)
            return ""

    if len(content) < 200:
        print(f"[fetch] Content too short ({len(content)} bytes)", file=sys.stderr)
        return ""

    cache_path.write_text(content, encoding="utf-8")
    print(f"[fetch] Fetched {len(content)} bytes, cached at {cache_path.name}", file=sys.stderr)
    return content


def run_fetch(args):
    """Fetch JD from URL and print to stdout."""
    content = fetch_jd_from_url(args.url)
    if content:
        print(content)
        return 0
    else:
        print("FETCH_FAILED", file=sys.stderr)
        return 1


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="llm-cv direct API pipeline")
    subparsers = parser.add_subparsers(dest="step", required=True)

    # Step 1
    p1 = subparsers.add_parser("step1", help="ATS analysis + JD archival + project ranking")
    p1.add_argument("--jd-file", help="Path to JD text file")
    p1.add_argument("--jd-text", help="JD text directly")
    p1.add_argument("--render", default="latex", choices=["latex", "reportfallback"])
    p1.add_argument("--style", default="us", choices=["us", "german"])
    p1.add_argument("--source", default="Cold Apply")
    p1.add_argument("--language", default="English", choices=["English", "German"])
    p1.add_argument("--weak-tie", default="")
    p1.add_argument("--model", default=DEFAULT_MODEL)

    # Step 2
    p2 = subparsers.add_parser("step2", help="Resume writer + ATS rescoring")
    p2.add_argument("--app-dir", required=True, help="Application folder path")
    p2.add_argument("--render", default="latex", choices=["latex", "reportfallback"])
    p2.add_argument("--style", default="us", choices=["us", "german"])
    p2.add_argument("--language", default="English", choices=["English", "German"])
    p2.add_argument("--stuffing", default="none", choices=["none", "all", "selective"])
    p2.add_argument("--user-skills", default="")
    p2.add_argument("--score-boost", default="false", choices=["true", "false"])
    p2.add_argument("--initial-score", default="0")
    p2.add_argument("--model", default=DEFAULT_MODEL)

    # Step 3
    p3 = subparsers.add_parser("step3", help="Cover letter writer")
    p3.add_argument("--app-dir", required=True, help="Application folder path")
    p3.add_argument("--render", default="latex", choices=["latex", "reportfallback"])
    p3.add_argument("--language", default="English", choices=["English", "German"])
    p3.add_argument("--model", default=DEFAULT_MODEL)

    # Fetch
    pfetch = subparsers.add_parser("fetch", help="Fetch JD from URL via Jina Reader")
    pfetch.add_argument("--url", required=True, help="Job posting URL")
    pfetch.add_argument("--model", default=DEFAULT_MODEL)

    # Fix
    pf = subparsers.add_parser("fix", help="Fix Resume.yaml after parseability failure")
    pf.add_argument("--app-dir", required=True, help="Application folder path")
    pf.add_argument("--error", required=True, help="Error message from parseability audit")
    pf.add_argument("--language", default="English", choices=["English", "German"])
    pf.add_argument("--model", default=DEFAULT_MODEL)

    args = parser.parse_args()

    if args.step == "step1":
        sys.exit(run_step1(args))
    elif args.step == "step2":
        sys.exit(run_step2(args))
    elif args.step == "step3":
        sys.exit(run_step3(args))
    elif args.step == "fetch":
        sys.exit(run_fetch(args))
    elif args.step == "fix":
        sys.exit(run_fix(args))


if __name__ == "__main__":
    main()
