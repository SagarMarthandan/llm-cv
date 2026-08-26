#!/bin/bash
###############################################################################
# run_pipeline.sh — llm-cv Session-Splitting Wrapper (Phase 7)
#
# Runs the 3-step llm-cv pipeline as 3 separate OMP sessions, chaining via
# disk files. Each session starts with a clean context — no accumulation
# from previous steps. Saves ~1.8M tokens per run vs single-session mode.
#
# Usage:
#   ./run_pipeline.sh                          # interactive — prompts for JD
#   ./run_pipeline.sh "paste JD text here"     # pass JD text directly
#   ./run_pipeline.sh --url "https://..."      # fetch JD from URL (Step 0)
#   ./run_pipeline.sh --file jd.txt            # read JD from file
#
# The script will:
#   1. Collect First Action answers (render mode, style, source, language)
#   2. Launch Step 1 session (ATS analysis + JD archival + project ranking)
#   3. Read skill_gaps from ATS_Report.yaml, collect keyword stuffing decision
#   4. Launch Step 2 session (resume rewrite + layout audit + parseability)
#   5. Launch Step 3 session (cover letter + Obsidian sync)
#
# Each session is non-interactive (omp -p --auto-approve). The user is
# prompted by this script between sessions for decisions that would
# normally require the ask tool inside the agent.
###############################################################################
set -euo pipefail

SCRIPT_DIR="/home/sagar/Skills/llm-cv"
OMP="${OMP:-/home/sagar/.local/bin/omp}"
APPLICATIONS_DIR="/home/sagar/Applications"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
PROMPTS_DIR="$SCRIPT_DIR/prompts"

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

die() { err "$*"; exit 1; }

###############################################################################
# Parse arguments
###############################################################################
JD_TEXT=""
JD_URL=""
JD_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)   JD_URL="$2"; shift 2;;
        --file)  JD_FILE="$2"; shift 2;;
        -h|--help)
            head -25 "$0" | tail -22
            exit 0
            ;;
        *)
            # Treat as JD text (if it doesn't start with --)
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
    # Pass URL to Step 1 — the agent will read 00_jd_fetch.md and fetch it
    JD_TEXT="__JD_URL__:$JD_URL"
elif [[ -z "$JD_TEXT" ]]; then
    log "Paste the full Job Description text (Ctrl+D to finish):"
    JD_TEXT=$(cat)
fi

[[ -n "$JD_TEXT" ]] || die "No JD text provided."

# Write JD to temp file for passing to omp
JD_TEMP=$(mktemp /tmp/llm-cv-jd-XXXXXX.txt)
echo "$JD_TEXT" > "$JD_TEMP"

###############################################################################
# Collect First Action answers
###############################################################################
echo ""
log "=== First Action: Pipeline Options ==="
echo ""

PS3="Render mode (1-2): "
select render_mode in "latex" "reportfallback"; do break; done

PS3="Resume style (1-2): "
select resume_style in "us" "german"; do break; done

PS3="Application source (1-4): "
select app_source in "Cold Apply" "Referral" "LinkedIn Connection" "Direct"; do break; done

weak_tie_contact=""
if [[ "$app_source" == "Referral" || "$app_source" == "LinkedIn Connection" ]]; then
    echo -n "Contact name/role for $app_source: "
    read weak_tie_contact
fi

PS3="Language (1-2): "
select language in "English" "German"; do break; done

echo ""
log "Selected: render=$render_mode style=$resume_style source=$app_source lang=$language"
echo ""

###############################################################################
# Helper: run an OMP session in print mode
###############################################################################
run_session() {
    local prompt_file="$1"
    local session_name="$2"

    log "Launching session: $session_name"
    "$OMP" -p --auto-approve --cwd "$SCRIPT_DIR" \
        --skills "llm-cv" \
        @"$prompt_file" \
        2>&1 | tee /tmp/llm-cv-${session_name}.log

    local exit_code=${PIPESTATUS[0]}
    if [[ $exit_code -ne 0 ]]; then
        die "Session $session_name failed (exit $exit_code). Log: /tmp/llm-cv-${session_name}.log"
    fi
    ok "Session $session_name completed."
}

###############################################################################
# Step 1: ATS Analysis & JD Archival
###############################################################################
log "=== Step 1: ATS Analysis & JD Archival ==="

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
2. Write ATS_Report.yaml, Job_Description.yaml, project_info.md
3. Compile ATS_Report.pdf and Job_Description.pdf
4. Store all First Action answers in the appropriate YAML files

Do NOT ask any questions — all answers are provided above.
Do NOT proceed to Step 2. This session handles Step 1 only.
EOF

run_session "$STEP1_PROMPT" "step1"
rm -f "$STEP1_PROMPT"

###############################################################################
# Find the application folder (created by Step 1)
###############################################################################
log "Locating Step 1 outputs..."
APP_DIR=""

# Try to find the most recently created ATS_Report.yaml
for f in $(find "$APPLICATIONS_DIR" -name "ATS_Report.yaml" -newer "$JD_TEMP" 2>/dev/null | sort -r); do
    APP_DIR=$(dirname "$f")
    break
done

if [[ -z "$APP_DIR" || ! -f "$APP_DIR/ATS_Report.yaml" ]]; then
    # Fallback: find most recent application folder
    APP_DIR=$(find "$APPLICATIONS_DIR" -name "ATS_Report.yaml" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2 | xargs dirname 2>/dev/null)
fi

[[ -n "$APP_DIR" && -f "$APP_DIR/ATS_Report.yaml" ]] || die "Step 1 did not produce ATS_Report.yaml. Check /tmp/llm-cv-step1.log"

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
            # Find the most recent prior application folder from the check output
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

ok "Application folder: $APP_DIR"

###############################################################################
# Collect Keyword Stuffing Decision (between Step 1 and Step 2)
###############################################################################
log "=== Keyword Stuffing Decision ==="

# Extract skill_gaps from ATS_Report.yaml
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

PS3="How do you want to handle skill gaps? (1-3): "
select stuffing_choice in "Add all" "No stuffing" "Selective"; do break; done

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
    echo "  4. Itemized Scoring Rubric — post-rewrite rescoring against explicit JD term"
    echo "     lists with matched/unmatched items (more rigorous score justification)"
    echo ""
    echo "All measures respect anti-hallucination rules — no fabricating capabilities or metrics."
    echo ""
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
else
    ok "Initial ATS score: $INITIAL_ATS_SCORE (≥ 85) — Score-Boost Mode not needed"
fi

echo ""

###############################################################################
# Step 2: Resume Rewrite & Visual Layout Audit
###############################################################################
log "=== Step 2: Resume Rewrite & Visual Layout Audit ==="

STEP2_PROMPT=$(mktemp /tmp/llm-cv-step2-prompt-XXXXXX.md)
cat > "$STEP2_PROMPT" << EOF
Run the llm-cv pipeline Step 2 ONLY. Do NOT proceed to Step 3.

Read skill://llm-cv (SKILL.md) and 02_resume_and_visual_audit.md for full instructions.

Application folder: $APP_DIR

Read these files from the application folder (do NOT re-paste):
- ATS_Report.yaml (Step 1 output — read render_mode, resume_style, language, improvement_blueprint, role_archetype, skill_gaps, closest_candidate_location from here)
- project_info.md (Step 1 output — tailored project list)

Keyword stuffing decision (already collected — do NOT use the ask tool):
- keyword_stuffing: $keyword_stuffing
- user_directed_skills: "$user_directed_skills"
- score_boost_mode: $score_boost_mode
- initial_ats_score: $INITIAL_ATS_SCORE

Execute Step 2 completely:
If score_boost_mode is true, apply Score-Boost measures from prompts/score_boost.md during the rewrite: Measures 1-3 (student framing, JD phrase weaving, adjacent skills) in §1 Document Rewrite; Measure 4 (itemized scoring rubric) in §5 Post-Rewrite ATS Rescoring.
1. Write Resume.yaml with all projects, skills, experience
2. Compile the resume (LaTeX: tex-only → pdflatex × 2 → stamp photo; ReportFallback: single compile)
3. Run layout audit → Layout_Audit_Report.yaml
4. Post-rewrite ATS rescoring → update post_rewrite_ats_score in ATS_Report.yaml
5. Run parseability audit → Parseability_Report.yaml + .pdf
6. Recompile ATS_Report.pdf with post-rewrite scores

Do NOT ask any questions — all answers are provided above.
Do NOT proceed to Step 3. This session handles Step 2 only.
EOF

run_session "$STEP2_PROMPT" "step2"
rm -f "$STEP2_PROMPT"

# Verify Step 2 outputs
RESUME_PDF=""
if [[ "$language" == "German" ]]; then
    RESUME_PDF="$APP_DIR/SAGAR_MARTHANDAN_Lebenslauf.pdf"
else
    RESUME_PDF="$APP_DIR/SAGAR_MARTHANDAN_Resume.pdf"
fi
[[ -f "$RESUME_PDF" ]] || warn "Resume PDF not found at expected path: $RESUME_PDF"
[[ -f "$APP_DIR/Parseability_Report.yaml" ]] || warn "Parseability report not found."

###############################################################################
# Step 3: Cover Letter Generation & Compilation
###############################################################################
log "=== Step 3: Cover Letter Generation & Compilation ==="

STEP3_PROMPT=$(mktemp /tmp/llm-cv-step3-prompt-XXXXXX.md)
cat > "$STEP3_PROMPT" << EOF
Run the llm-cv pipeline Step 3 ONLY. This is the final step.

Read skill://llm-cv (SKILL.md) and 03_cover_letter.md for full instructions.

Application folder: $APP_DIR

Read these files from the application folder (do NOT re-paste):
- ATS_Report.yaml (Step 1 output — read render_mode, language, closest_candidate_location, application_source, weak_tie_contact, role_archetype from here)
- Job_Description.yaml (Step 1 output — company, position, JD sections)
- project_info.md (Step 1 output — tailored project list with metrics)

Execute Step 3 completely:
1. Write Cover_Letter.yaml
2. Compile the cover letter PDF
3. Run Obsidian sync: sync_to_obsidian.py "$APP_DIR" --sort

Do NOT ask any questions — all answers are provided above.
This is the final step — after completion, the pipeline is done.
EOF

run_session "$STEP3_PROMPT" "step3"
rm -f "$STEP3_PROMPT"

###############################################################################
# Verify completion
###############################################################################
echo ""
log "=== Pipeline Complete ==="
ok "Application folder: $APP_DIR"
echo ""
echo "Outputs:"
ls -la "$APP_DIR"/*.pdf "$APP_DIR"/*.yaml "$APP_DIR"/*.md 2>/dev/null | awk '{print "  " $NF}'

# Cleanup
rm -f "$JD_TEMP"

echo ""
ok "Done. Read 99_completion_checklist.md to verify all outputs."
