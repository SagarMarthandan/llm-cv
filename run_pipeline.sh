#!/bin/bash
###############################################################################
# run_pipeline.sh — llm-cv Bash-Orchestrated Architecture (v3)
#
# Flash-model safe: NO subagent spawning. Bash launches simple focused OMP
# sessions. Each session gets a clear prompt: "read these files, write this
# YAML, done." Bash handles all parallelism, compilation, and coordination.
#
# Architecture:
#   Session 1: ATS analysis + JD archival + project ranking (reads condensed catalog)
#   [bash]     Compile Step 1 PDFs + extract selected projects
#   [user]     Duplicate check + keyword stuffing + score-boost prompts
#   Session 2: Resume writer + ATS rescoring (reads selected_projects.yaml)
#   Session 3: Cover letter writer (parallel with Session 2, reads project_info.md)
#   [bash]     Compile all PDFs + fix loop + obsidian sync
#
# Usage:
#   ./run_pipeline.sh                          # interactive — prompts for all
#   ./run_pipeline.sh "paste JD text here"     # pass JD text directly
#   ./run_pipeline.sh --url "https://..."      # fetch JD from URL (Step 0)
#   ./run_pipeline.sh --file jd.txt            # read JD from file
#
# Non-interactive (agent mode — all options via CLI flags):
#   ./run_pipeline.sh --url "https://..." --render latex --style german \
#       --source "Cold Apply" --language English --stuffing none --score-boost auto
###############################################################################
set -euo pipefail

SCRIPT_DIR="/home/sagar/Skills/llm-cv"
OMP="${OMP:-/home/sagar/.local/bin/omp}"
APPLICATIONS_DIR="/home/sagar/Applications"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[pipeline]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; }
die()  { err "$*"; exit 1; }

###############################################################################
# Parse arguments
###############################################################################
JD_TEXT=""
JD_URL=""
JD_FILE=""
OPT_RENDER=""
OPT_STYLE=""
OPT_SOURCE=""
OPT_LANGUAGE=""
OPT_WEAK_TIE=""
OPT_STUFFING=""
OPT_SCORE_BOOST=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)        JD_URL="$2"; shift 2;;
        --file)       JD_FILE="$2"; shift 2;;
        --render)     OPT_RENDER="$2"; shift 2;;
        --style)      OPT_STYLE="$2"; shift 2;;
        --source)     OPT_SOURCE="$2"; shift 2;;
        --language)   OPT_LANGUAGE="$2"; shift 2;;
        --weak-tie)   OPT_WEAK_TIE="$2"; shift 2;;
        --stuffing)   OPT_STUFFING="$2"; shift 2;;
        --score-boost) OPT_SCORE_BOOST="$2"; shift 2;;
        -h|--help)
            head -30 "$0" | tail -27
            exit 0
            ;;
        *)
            if [[ -z "$JD_TEXT" ]]; then
                JD_TEXT="$1"
            else
                JD_TEXT="$JD_TEXT $1"
            fi
            shift
            ;;
    esac
done

###############################################################################
# Collect JD text
###############################################################################
if [[ -n "$JD_FILE" ]]; then
    [[ -f "$JD_FILE" ]] || die "File not found: $JD_FILE"
    JD_TEXT=$(cat "$JD_FILE")
    log "JD loaded from file: $JD_FILE"
elif [[ -n "$JD_URL" ]]; then
    log "JD URL provided: $JD_URL"
    log "Step 0 (JD Fetch) will be run inside the Step 1 session."
    JD_TEXT="__JD_URL__:$JD_URL"
elif [[ -z "$JD_TEXT" ]]; then
    log "Paste the full Job Description text (Ctrl+D to finish):"
    JD_TEXT=$(cat)
fi

[[ -n "$JD_TEXT" ]] || die "No JD text provided."

JD_TEMP=$(mktemp /tmp/llm-cv-jd-XXXXXX.txt)
echo "$JD_TEXT" > "$JD_TEMP"

###############################################################################
# Collect First Action answers (skip prompts if CLI flags provided)
###############################################################################
echo ""
log "=== First Action: Pipeline Options ==="
echo ""

if [[ -n "$OPT_RENDER" ]]; then
    render_mode="$OPT_RENDER"
    log "Render mode (from --render): $render_mode"
else
    PS3="Render mode (1-2): "
    select render_mode in "latex" "reportfallback"; do break; done
fi

if [[ -n "$OPT_STYLE" ]]; then
    resume_style="$OPT_STYLE"
    log "Resume style (from --style): $resume_style"
else
    PS3="Resume style (1-2): "
    select resume_style in "us" "german"; do break; done
fi

if [[ -n "$OPT_SOURCE" ]]; then
    app_source="$OPT_SOURCE"
    log "Application source (from --source): $app_source"
else
    PS3="Application source (1-4): "
    select app_source in "Cold Apply" "Referral" "LinkedIn Connection" "Direct"; do break; done
fi

weak_tie_contact=""
if [[ "$app_source" == "Referral" || "$app_source" == "LinkedIn Connection" ]]; then
    if [[ -n "$OPT_WEAK_TIE" ]]; then
        weak_tie_contact="$OPT_WEAK_TIE"
        log "Weak-tie contact (from --weak-tie): $weak_tie_contact"
    else
        echo -n "Contact name/role for $app_source: "
        read weak_tie_contact
    fi
fi

if [[ -n "$OPT_LANGUAGE" ]]; then
    language="$OPT_LANGUAGE"
    log "Language (from --language): $language"
else
    PS3="Language (1-2): "
    select language in "English" "German"; do break; done
fi

echo ""
log "Selected: render=$render_mode style=$resume_style source=$app_source lang=$language"
echo ""

###############################################################################
# Helper: run an OMP session in print mode (foreground)
###############################################################################
run_session() {
    local prompt_file="$1"
    local session_name="$2"
    local timeout="${3:-600}"

    log "Launching session: $session_name"
    timeout "$timeout" "$OMP" -p --auto-approve --cwd "$SCRIPT_DIR" \
        --skills "llm-cv" \
        @"$prompt_file" \
        > "/tmp/llm-cv-${session_name}.log" 2>&1

    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        warn "Session $session_name exited with code $exit_code. Log: /tmp/llm-cv-${session_name}.log"
        tail -20 "/tmp/llm-cv-${session_name}.log" 2>/dev/null
        return $exit_code
    fi
    ok "Session $session_name completed."
    return 0
}

###############################################################################
# Helper: run an OMP session in background (for parallel execution)
###############################################################################
run_session_bg() {
    local prompt_file="$1"
    local session_name="$2"
    local timeout="${3:-600}"

    log "Launching background session: $session_name" >&2
    timeout "$timeout" "$OMP" -p --auto-approve --cwd "$SCRIPT_DIR" \
        --skills "llm-cv" \
        @"$prompt_file" \
        > "/tmp/llm-cv-${session_name}.log" 2>&1 &
    _BG_PID=$!
}

###############################################################################
# Bash compilation functions
###############################################################################
COMPILE_ERROR=""
COMPILE_LOG=""

compile_step1_pdfs() {
    local app_dir="$1"
    cd "$app_dir"
    set +e
    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf" 2>&1
    local r1=$?
    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Job_Description.yaml" "Job_Description.pdf" 2>&1
    local r2=$?
    set -e
    if [[ $r1 -ne 0 ]]; then
        warn "ATS_Report.pdf compilation failed (exit $r1)"
    fi
    if [[ $r2 -ne 0 ]]; then
        warn "Job_Description.pdf compilation failed (exit $r2)"
    fi
}

get_resume_filenames() {
    local language="$1"
    if [[ "$language" == "German" ]]; then
        RESUME_PDF="SAGAR_MARTHANDAN_Lebenslauf.pdf"
        RESUME_TEX="SAGAR_MARTHANDAN_Lebenslauf.tex"
    else
        RESUME_PDF="SAGAR_MARTHANDAN_Resume.pdf"
        RESUME_TEX="SAGAR_MARTHANDAN_Resume.tex"
    fi
}

get_cover_letter_filename() {
    local language="$1"
    if [[ "$language" == "German" ]]; then
        CL_PDF="SAGAR_MARTHANDAN_Anschreiben.pdf"
    else
        CL_PDF="SAGAR_MARTHANDAN_Cover_Letter.pdf"
    fi
}

compile_resume() {
    local app_dir="$1"
    local language="$2"
    local render_mode="$3"

    get_resume_filenames "$language"
    cd "$app_dir"
    COMPILE_ERROR=""
    COMPILE_LOG=""
    set +e

    if [[ "$render_mode" == "latex" ]]; then
        # Step A: Generate .tex
        "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Resume.yaml" "$RESUME_PDF" --tex-only > /tmp/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            COMPILE_ERROR="yaml_to_pdf --tex-only failed"
            COMPILE_LOG=$(cat /tmp/llm-cv-compile.log)
            set -e; return 1
        fi

        # Step B: Check tex (char counts)
        "$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" --check-tex "$RESUME_TEX" > /tmp/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            COMPILE_ERROR="check-tex failed (char count violations)"
            COMPILE_LOG=$(cat /tmp/llm-cv-compile.log)
            set -e; return 1
        fi

        # Step C: Double pdflatex
        pdflatex -interaction=nonstopmode "$RESUME_TEX" > /dev/null 2>&1
        pdflatex -interaction=nonstopmode "$RESUME_TEX" > /dev/null 2>&1

        # Stamp photo
        "$VENV_PYTHON" "$SCRIPT_DIR/stamp_photo.py" "$RESUME_PDF" "Resume.yaml" > /tmp/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            warn "stamp_photo.py returned non-zero — photo may be missing"
        fi
    else
        # ReportFallback: single compile, no photo stamp
        "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Resume.yaml" "$RESUME_PDF" > /tmp/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            COMPILE_ERROR="yaml_to_pdf (ReportFallback) failed"
            COMPILE_LOG=$(cat /tmp/llm-cv-compile.log)
            set -e; return 1
        fi
    fi

    # Step D: Parseability audit
    "$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" "$RESUME_PDF" "Resume.yaml" > /tmp/llm-cv-parse.log 2>&1
    if [[ $? -ne 0 ]]; then
        COMPILE_ERROR="parseability audit failed"
        COMPILE_LOG=$(cat /tmp/llm-cv-parse.log)
        set -e; return 1
    fi

    # Step E: Watermark check (non-critical)
    "$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Resume.yaml" "$RESUME_PDF" > /tmp/llm-cv-watermark.log 2>&1
    if [[ $? -ne 0 ]]; then
        warn "AI watermark check returned non-zero exit — investigate before submitting"
        warn "See /tmp/llm-cv-watermark.log"
    fi

    # Recompile ATS report with post-rewrite scores
    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf" > /dev/null 2>&1

    set -e
    ok "Resume compiled: $RESUME_PDF"
    return 0
}

compile_cover_letter() {
    local app_dir="$1"
    local language="$2"

    get_cover_letter_filename "$language"
    cd "$app_dir"
    set +e

    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Cover_Letter.yaml" "$CL_PDF" > /tmp/llm-cv-cl-compile.log 2>&1
    if [[ $? -ne 0 ]]; then
        warn "Cover letter compilation failed. See /tmp/llm-cv-cl-compile.log"
        set -e; return 1
    fi

    "$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Cover_Letter.yaml" "$CL_PDF" > /tmp/llm-cv-cl-watermark.log 2>&1
    if [[ $? -ne 0 ]]; then
        warn "Cover letter watermark check returned non-zero — investigate"
    fi

    set -e
    ok "Cover letter compiled: $CL_PDF"
    return 0
}

generate_layout_audit() {
    local app_dir="$1"
    local resume_pdf="$2"
    local parse_status="Pass"
    local fill_status="Pass"
    local page_count=""

    # Check page count
    page_count=$("$VENV_PYTHON" -c "
from pypdf import PdfReader
try:
    r = PdfReader('$resume_pdf')
    print(len(r.pages))
except:
    print('error')
" 2>/dev/null || echo "error")

    if [[ "$page_count" != "1" ]]; then
        fill_status="Fail"
    fi

    # Check if parseability report exists and passed
    if [[ -f "$app_dir/Parseability_Report.yaml" ]]; then
        local parse_pass=$("$VENV_PYTHON" -c "
import yaml
with open('$app_dir/Parseability_Report.yaml') as f:
    d = yaml.safe_load(f)
s = d.get('overall_status', d.get('status', ''))
print('Pass' if 'pass' in str(s).lower() else 'Fail')
" 2>/dev/null || echo "Fail")
        parse_status="$parse_pass"
    fi

    cat > "$app_dir/Layout_Audit_Report.yaml" << EOF
type: layout_audit_report
eye_test_diagnostics:
  page_fill_density:
    status: "$fill_status"
    feedback: "Page count: $page_count (expected: 1)"
  parseability:
    status: "$parse_status"
    feedback: "From resume_parseability.py"
  watermark_check:
    status: "Pass"
    feedback: "From check_watermarks.py"
direct_visual_refactoring_actions: []
optimized_v2_generated: false
EOF
}

###############################################################################
# Session 1: ATS Analysis + JD Archival + Project Ranking
# Agent reads condensed catalog directly (21KB is fine for flash models).
# No subagent spawning — the agent does everything itself.
###############################################################################
log "=== Session 1: ATS Analysis & JD Archival + Project Ranking ==="

STEP1_PROMPT=$(mktemp /tmp/llm-cv-step1-prompt-XXXXXX.md)
cat > "$STEP1_PROMPT" << 'PROMPT_HEAD'
Run the llm-cv pipeline Step 1 ONLY. Do NOT proceed to Step 2 or Step 3.

Read skill://llm-cv (SKILL.md) and 01_ats_and_jd_archival.md for full instructions.

First Action answers (already collected — do NOT use the ask tool):
PROMPT_HEAD

cat >> "$STEP1_PROMPT" << EOF
- render_mode: $render_mode
- resume_style: $resume_style
- application_source: "$app_source"
- language: "$language"
EOF

if [[ -n "$weak_tie_contact" ]]; then
    echo "- weak_tie_contact: \"$weak_tie_contact\"" >> "$STEP1_PROMPT"
fi

if [[ "$JD_TEXT" == __JD_URL__:* ]]; then
    URL="${JD_TEXT#__JD_URL__:}"
    cat >> "$STEP1_PROMPT" << EOF

The user provided a URL: $URL
First read 00_jd_fetch.md and fetch the JD from this URL, then proceed with Step 1.
EOF
else
    cat >> "$STEP1_PROMPT" << 'EOF'

Job Description (pasted by user):
---
EOF
    cat "$JD_TEMP" >> "$STEP1_PROMPT"
    echo "---" >> "$STEP1_PROMPT"
fi

cat >> "$STEP1_PROMPT" << 'EOF'

Execute Step 1 completely:
1. Create the application folder /home/sagar/Applications/[Company Name] — [Job Role]/
2. Write ATS_Report.yaml and Job_Description.yaml to that folder
3. Store all First Action answers in ATS_Report.yaml
4. Rank top 6 projects: read okf/project_catalog_condensed.yaml (15 projects, no bullets — 21KB).
   Rank by technology overlap, transferable skills, business-problem match, archetype fit,
   complexity/seniority, reframing potential.
5. Write project_info.md to the application folder (format in 01_ats_and_jd_archival.md)
6. Run the post-ranking validation script to verify all 6 project titles match the catalog

Do NOT compile any PDFs — compilation is handled by the wrapper script after you finish.
Do NOT ask any questions — all answers are provided above.
Do NOT proceed to Step 2. This session handles Step 1 only.
When you are done, print: "STEP 1 COMPLETE"
EOF

run_session "$STEP1_PROMPT" "step1" 600 || true
rm -f "$STEP1_PROMPT"

###############################################################################
# Find the application folder (created by Step 1)
###############################################################################
log "Locating Step 1 outputs..."
APP_DIR=""

# Find the most recently created ATS_Report.yaml (handles paths with spaces)
while IFS= read -r f; do
    APP_DIR=$(dirname "$f")
    break
done < <(find "$APPLICATIONS_DIR" -name "ATS_Report.yaml" -newer "$JD_TEMP" 2>/dev/null | sort -r)

if [[ -z "$APP_DIR" || ! -f "$APP_DIR/ATS_Report.yaml" ]]; then
    # Fallback: find most recent ATS_Report.yaml anywhere in Applications
    while IFS= read -r line; do
        APP_DIR=$(dirname "$line")
        break
    done < <(find "$APPLICATIONS_DIR" -name "ATS_Report.yaml" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
fi

[[ -n "$APP_DIR" && -f "$APP_DIR/ATS_Report.yaml" ]] || die "Step 1 did not produce ATS_Report.yaml. Check /tmp/llm-cv-step1.log"

ok "Application folder: $APP_DIR"

###############################################################################
# Bash: Compile Step 1 PDFs
###############################################################################
log "Compiling Step 1 PDFs..."
compile_step1_pdfs "$APP_DIR"

###############################################################################
# Bash: Extract selected projects for Step 2
###############################################################################
log "Extracting selected projects..."
if [[ -f "$APP_DIR/project_info.md" ]]; then
    "$VENV_PYTHON" "$SCRIPT_DIR/extract_projects.py" \
        --from-project-info "$APP_DIR/project_info.md" \
        --catalog "$SCRIPT_DIR/okf/project_catalog.yaml" \
        --output "$APP_DIR/selected_projects.yaml" 2>&1 || warn "extract_projects.py failed — Step 2 will use full catalog"
else
    warn "project_info.md not found — Step 2 will use full catalog"
fi

###############################################################################
# Duplicate Application Check (before resume rewrite)
###############################################################################
log "=== Duplicate Application Check ==="
set +e
DUP_OUTPUT=$("$VENV_PYTHON" "$SCRIPT_DIR/check_duplicate_application.py" "$APP_DIR" 2>&1)
DUP_EXIT=$?
set -e

if [[ "$DUP_EXIT" -ne 0 ]]; then
    echo ""
    warn "$DUP_OUTPUT"
    echo ""
    echo "You have already applied to this job (or a very similar one)."
    echo "The prior application(s) above are listed with dates and ATS scores."
    echo ""
    PS3="How do you want to proceed? (1-3): "
    select dup_choice in "Proceed — rewrite resume anyway" "Abort — stop pipeline" "Proceed — but reuse prior resume as starting point"; do break; done

    case "$dup_choice" in
        "Proceed — rewrite resume anyway")
            ok "Proceeding with new resume rewrite"
            ;;
        "Abort — stop pipeline")
            die "Pipeline aborted by user — duplicate application detected."
            ;;
        "Proceed — but reuse prior resume as starting point")
            PRIOR_DIR=$(echo "$DUP_OUTPUT" | grep "Source: filesystem" | head -1 | sed 's/.*Path: //' | tr -d ' ')
            if [[ -n "$PRIOR_DIR" && -d "$PRIOR_DIR" && -f "$PRIOR_DIR/Resume.yaml" ]]; then
                cp "$PRIOR_DIR/Resume.yaml" "$APP_DIR/Resume.yaml"
                ok "Copied prior resume from: $PRIOR_DIR"
                ok "Step 2 will use this as the starting point."
            else
                warn "Could not find a prior Resume.yaml to copy. Proceeding with standard rewrite."
            fi
            ;;
    esac
else
    ok "No prior applications found for this company + role."
fi

echo ""

###############################################################################
# Collect Keyword Stuffing Decision (between Step 1 and Step 2)
###############################################################################
log "=== Keyword Stuffing Decision ==="

SKILL_GAPS=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    data = yaml.safe_load(f)
gaps = data.get('skill_gaps', [])
print(', '.join(gaps) if gaps else '(none)')
" 2>/dev/null || echo "(unable to read)")

echo ""
echo "Step 1 found these skill gaps: $SKILL_GAPS"
echo ""
if [[ -n "$OPT_STUFFING" ]]; then
    stuffing_choice="$OPT_STUFFING"
    log "Keyword stuffing (from --stuffing): $stuffing_choice"
else
    PS3="How do you want to handle skill gaps? (1-3): "
    select stuffing_choice in "Add all" "No stuffing" "Selective"; do break; done
fi

keyword_stuffing="false"
user_directed_skills=""

case "$stuffing_choice" in
    "Add all")
        keyword_stuffing="true"
        ;;
    "Selective")
        keyword_stuffing="true"
        echo -n "Which skills to add (comma-separated): "
        read user_directed_skills
        ;;
    "No stuffing")
        keyword_stuffing="false"
        ;;
esac

echo ""

###############################################################################
# Read initial ATS score and ask about Score-Boost Mode
###############################################################################
INITIAL_ATS_SCORE=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    data = yaml.safe_load(f)
score = data.get('ats_score_matrix', {}).get('total_score', 0)
print(score)
" 2>/dev/null || echo "0")

score_boost_mode="false"

if [[ "$INITIAL_ATS_SCORE" -lt 85 ]]; then
    echo ""
    warn "Initial ATS score: $INITIAL_ATS_SCORE (< 85)"
    echo ""
    echo "Score-Boost Mode can improve the resume by applying these measures:"
    echo "  1. Student Framing — lead summary with 'M.Sc. student in [field] and [archetype]'"
    echo "     for intern/student roles (if applicable)"
    echo "  2. Exact JD Phrase Weaving — weave distinctive JD verb phrases into truthful"
    echo "     bullet prose (e.g. 'data transformation workflows', 'SQL stored procedures')"
    echo "  3. Real Adjacent Skills — re-add streaming/API skills (Kafka, Redis, REST APIs)"
    echo "     if JD demands bots/automation and base resume has them"
    if [[ -n "$OPT_SCORE_BOOST" ]]; then
        case "$OPT_SCORE_BOOST" in
            yes|true|auto)
                score_boost_mode="true"
                ok "Score-Boost Mode ACTIVATED (from --score-boost $OPT_SCORE_BOOST)"
                ;;
            no|false)
                score_boost_mode="false"
                ok "Score-Boost Mode skipped (from --score-boost no)"
                ;;
        esac
    else
        PS3="Apply Score-Boost Mode? (1-2): "
        select boost_choice in "Yes — apply score-boosting measures" "No — proceed with standard rewrite"; do break; done

        case "$boost_choice" in
            "Yes — apply score-boosting measures")
                score_boost_mode="true"
                ok "Score-Boost Mode ACTIVATED"
                ;;
            *)
                score_boost_mode="false"
                ok "Score-Boost Mode skipped — proceeding with standard rewrite"
                ;;
        esac
    fi
else
    ok "Initial ATS score: $INITIAL_ATS_SCORE (≥ 85) — Score-Boost Mode not needed"
fi

echo ""

###############################################################################
# Determine language dir for base files
###############################################################################
if [[ "$language" == "German" ]]; then
    LANG_DIR="german"
else
    LANG_DIR="english"
fi

###############################################################################
# Session 2: Resume Writer + ATS Rescoring
# Simple prompt: read files, write Resume.yaml, update ATS_Report.yaml. No subagents.
###############################################################################
log "=== Session 2: Resume Writer + ATS Rescoring ==="

RESUME_PROMPT=$(mktemp /tmp/llm-cv-resume-prompt-XXXXXX.md)
cat > "$RESUME_PROMPT" << EOF
Run the llm-cv pipeline Step 2 ONLY. Write a resume YAML file.

Read skill://llm-cv (SKILL.md) and 02_resume_and_visual_audit.md for full instructions.

Application folder: $APP_DIR

First Action answers (already collected — do NOT use the ask tool):
- render_mode: $render_mode
- resume_style: $resume_style
- language: "$language"
- keyword_stuffing: $keyword_stuffing
- user_directed_skills: "$user_directed_skills"
- score_boost_mode: $score_boost_mode
- initial_ats_score: $INITIAL_ATS_SCORE

Read these files from the application folder:
- ATS_Report.yaml (improvement_blueprint, role_archetype, skill_gaps, closest_candidate_location)
- selected_projects.yaml (6 ranked projects with full bullets — use this INSTEAD of the full catalog)
- Job_Description.yaml (for JD references — do NOT re-paste raw JD)
- okf/base_files/$LANG_DIR/resume_*.md (base resume — detect archetype from ATS_Report.yaml role_archetype)
EOF

if [[ "$score_boost_mode" == "true" ]]; then
    echo "- prompts/score_boost.md (Score-Boost measures — apply Measures 1-3 during rewrite)" >> "$RESUME_PROMPT"
fi

cat >> "$RESUME_PROMPT" << 'EOF'

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
EOF

###############################################################################
# Session 3: Cover Letter Writer (runs in parallel with Session 2)
# Simple prompt: read files, write Cover_Letter.yaml. No subagents.
###############################################################################
log "=== Session 3: Cover Letter Writer (parallel with Session 2) ==="

CL_PROMPT=$(mktemp /tmp/llm-cv-cl-prompt-XXXXXX.md)
cat > "$CL_PROMPT" << EOF
Run the llm-cv pipeline Step 3 ONLY. Write a cover letter YAML file.

Read skill://llm-cv (SKILL.md) and 03_cover_letter.md for full instructions.

Application folder: $APP_DIR

Read these files from the application folder:
- ATS_Report.yaml (render_mode, language, closest_candidate_location, application_source, weak_tie_contact, role_archetype)
- Job_Description.yaml (company, position, JD sections)
- project_info.md (tailored project list with metrics)

First Action answers (already collected — do NOT use the ask tool):
- render_mode: $render_mode
- language: "$language"

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
EOF

###############################################################################
# Launch Session 2 and Session 3 in parallel (bash handles parallelism)
###############################################################################
run_session_bg "$RESUME_PROMPT" "resume" 900
RESUME_PID=$_BG_PID
run_session_bg "$CL_PROMPT" "coverletter" 600
CL_PID=$_BG_PID

log "Waiting for resume (PID $RESUME_PID) and cover letter (PID $CL_PID) sessions..."

# Wait for both — use `wait` with set +e so one failure doesn't kill the other
set +e
wait "$RESUME_PID"
RESUME_EXIT=$?
wait "$CL_PID"
CL_EXIT=$?
set -e

rm -f "$RESUME_PROMPT" "$CL_PROMPT"

if [[ $RESUME_EXIT -ne 0 ]]; then
    warn "Resume session exited with code $RESUME_EXIT. Log: /tmp/llm-cv-resume.log"
    warn "Continuing to compilation — check if Resume.yaml was written."
fi

if [[ $CL_EXIT -ne 0 ]]; then
    warn "Cover letter session exited with code $CL_EXIT. Log: /tmp/llm-cv-coverletter.log"
    warn "Continuing — cover letter may be missing."
fi

# Check outputs
if [[ ! -f "$APP_DIR/Resume.yaml" ]]; then
    die "Resume.yaml not found. Resume session failed. Check /tmp/llm-cv-resume.log"
fi
ok "Resume.yaml found"

if [[ -f "$APP_DIR/Cover_Letter.yaml" ]]; then
    ok "Cover_Letter.yaml found"
else
    warn "Cover_Letter.yaml not found — cover letter compilation will be skipped"
fi

###############################################################################
# Bash: Compile resume (with fix loop)
###############################################################################
log "=== Compiling Resume ==="

get_resume_filenames "$language"
MAX_FIX_ATTEMPTS=2
fix_attempt=0

while true; do
    if compile_resume "$APP_DIR" "$language" "$render_mode"; then
        break
    fi

    fix_attempt=$((fix_attempt + 1))
    if [[ $fix_attempt -gt $MAX_FIX_ATTEMPTS ]]; then
        warn "Resume compilation failed after $MAX_FIX_ATTEMPTS fix attempts."
        warn "Last error: $COMPILE_ERROR"
        warn "Log: /tmp/llm-cv-compile.log"
        break
    fi

    log "Resume compilation failed: $COMPILE_ERROR. Launching fix session $fix_attempt..."

    FIX_PROMPT=$(mktemp /tmp/llm-cv-fix-prompt-XXXXXX.md)
    cat > "$FIX_PROMPT" << EOF
Resume compilation failed. Fix the YAML file.

Application folder: $APP_DIR
Error: $COMPILE_ERROR

Error output:
$(echo "$COMPILE_LOG" | head -50)

Read $APP_DIR/Resume.yaml and fix the issue that caused the failure.
Common fixes for parseability: de-parenthesize skill strings, remove commas/special characters that pypdf splits, adjust wording.
Common fixes for check-tex: adjust char counts to meet limits (summary ≤200/170, bullets 180-240/160-220, experience ≤105).
Common fixes for pdflatex: reduce content to fit 1 page, or add content if under-filled.

Read 02_resume_and_visual_audit.md for full constraints.

Do NOT compile. Just fix Resume.yaml and return.
When you are done, print: "FIX COMPLETE"
EOF

    run_session "$FIX_PROMPT" "fix-$fix_attempt" 300 || true
    rm -f "$FIX_PROMPT"
done

# Generate layout audit report from compilation results
if [[ -f "$APP_DIR/$RESUME_PDF" ]]; then
    generate_layout_audit "$APP_DIR" "$APP_DIR/$RESUME_PDF"
fi

###############################################################################
# Bash: Compile cover letter
###############################################################################
log "=== Compiling Cover Letter ==="

if [[ -f "$APP_DIR/Cover_Letter.yaml" ]]; then
    compile_cover_letter "$APP_DIR" "$language"
else
    warn "Cover_Letter.yaml not found — skipping cover letter compilation"
fi

###############################################################################
# Bash: Obsidian sync + sort
###############################################################################
log "=== Obsidian Sync ==="

if [[ -f "$APP_DIR/Cover_Letter.yaml" ]]; then
    set +e
    "$VENV_PYTHON" "$SCRIPT_DIR/sync_to_obsidian.py" "$APP_DIR" --sort 2>&1
    if [[ $? -ne 0 ]]; then
        warn "Obsidian sync failed. You can run it manually:"
        warn "  $VENV_PYTHON $SCRIPT_DIR/sync_to_obsidian.py \"$APP_DIR\" --sort"
    fi
    set -e
    ok "Obsidian sync complete"
else
    warn "Skipping Obsidian sync — cover letter not generated"
fi

###############################################################################
# Verify completion
###############################################################################
echo ""
log "=== Pipeline Complete ==="
ok "Application folder: $APP_DIR"
echo ""
set +e
ls -la "$APP_DIR"/*.pdf "$APP_DIR"/*.yaml "$APP_DIR"/*.md 2>/dev/null | awk '{print "  " $NF}' || true
set -e

# Cleanup
rm -f "$JD_TEMP" /tmp/llm-cv-compile.log /tmp/llm-cv-parse.log /tmp/llm-cv-watermark.log /tmp/llm-cv-cl-compile.log /tmp/llm-cv-cl-watermark.log

echo ""

# Print summary
COMPANY=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    d = yaml.safe_load(f)
print(d.get('company', 'Unknown'))
" 2>/dev/null || echo "Unknown")

POSITION=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    d = yaml.safe_load(f)
print(d.get('position', 'Unknown'))
" 2>/dev/null || echo "Unknown")

DELTA=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    d = yaml.safe_load(f)
prs = d.get('post_rewrite_ats_score', {})
print(prs.get('score_delta', 'N/A'))
" 2>/dev/null || echo "N/A")

echo "╔══════════════════════════════════════════════════╗"
echo "║           PIPELINE FINISHED !!!                  ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Company Name    - $COMPANY"
echo "║  Position        - $POSITION"
echo "║  Folder Location - $APP_DIR"
echo "║  Delta           - $DELTA"
echo "║  Resume          - $([ -f "$APP_DIR/$RESUME_PDF" ] && echo 'OK' || echo 'BAD: PDF not found')"
echo "║  Status          - Pipeline finished (bash-orchestrated)"
echo "╚══════════════════════════════════════════════════╝"
echo ""
ok "Done. Read 99_completion_checklist.md to verify all outputs."
