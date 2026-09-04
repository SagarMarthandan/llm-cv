#!/bin/bash
###############################################################################
# run_pipeline.sh — llm-cv Direct API Architecture (v4)
#
# Replaces OMP agent sessions with direct OpenRouter API calls via
# api_pipeline.py. 3 API calls total (step1, step2, step3) + optional fix
# calls. Bash handles all parallelism, compilation, and coordination.
#
# Architecture:
#   Step 1: ATS analysis + JD archival + project ranking (direct API call)
#   [bash]  Compile Step 1 PDFs + extract selected projects
#   [user]  Duplicate check + keyword stuffing + score-boost prompts
#   Step 2: Resume writer + ATS rescoring (direct API call, parallel with Step 3)
#   Step 3: Cover letter writer (direct API call, parallel with Step 2)
#   [bash]  Compile all PDFs + fix loop + obsidian sync
#
# Usage:
#   ./run_pipeline.sh                          # interactive — prompts for all
#   ./run_pipeline.sh "paste JD text here"     # pass JD text directly
#   ./run_pipeline.sh --url "https://..."      # fetch JD from URL (Jina Reader)
#   ./run_pipeline.sh --file jd.txt            # read JD from file
#
# Non-interactive (agent mode — all options via CLI flags):
#   ./run_pipeline.sh --url "https://..." --render latex --style german \
#       --source "Cold Apply" --language English --stuffing none --score-boost auto
###############################################################################
set -euo pipefail

SCRIPT_DIR="/home/sagar/Skills/llm-cv"
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
OPT_FORCE=""
OPT_STAGE=""
OPT_APP_DIR=""
OPT_USER_SKILLS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)        JD_URL="$2"; shift 2;;
        --file)       JD_FILE="$2"; shift 2;;
        --render)     OPT_RENDER="$2"; shift 2;;
        --style)      OPT_STYLE="$2"; shift 2;;
        --source)     OPT_SOURCE="$2"; shift 2;;
        --language)   OPT_LANGUAGE="$2"; shift 2;;
        --stuffing)   OPT_STUFFING="$2"; shift 2;;
        --score-boost) OPT_SCORE_BOOST="$2"; shift 2;;
        --stage)      OPT_STAGE="$2"; shift 2;;
        --app-dir)    OPT_APP_DIR="$2"; shift 2;;
        --user-skills) OPT_USER_SKILLS="$2"; shift 2;;
        --force)      OPT_FORCE="1"; shift;;
        --weak-tie)   OPT_WEAK_TIE="$2"; shift 2;;
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
# Collect JD text (skip in stage 2 — no JD needed)
###############################################################################
if [[ "$OPT_STAGE" != "2" ]]; then

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

fi # end JD + First Action block (skipped in stage 2)

###############################################################################
# Stage 2: use CLI flags for render/style/language (no interactive prompts)
###############################################################################
if [[ "$OPT_STAGE" == "2" ]]; then
    [[ -n "$OPT_APP_DIR" && -f "$OPT_APP_DIR/ATS_Report.yaml" ]] || die "Stage 2 requires --app-dir with valid ATS_Report.yaml"
    APP_DIR="$OPT_APP_DIR"
    render_mode="${OPT_RENDER:-latex}"
    resume_style="${OPT_STYLE:-german}"
    language="${OPT_LANGUAGE:-English}"
    app_source="${OPT_SOURCE:-Cold Apply}"
    weak_tie_contact="$OPT_WEAK_TIE"
    ok "Stage 2: resuming from $APP_DIR"
fi


###############################################################################
# api_pipeline.py — direct OpenRouter API calls (replaces OMP sessions)
###############################################################################
API_PY="$VENV_PYTHON $SCRIPT_DIR/api_pipeline.py"

###############################################################################
# Source compilation functions from lib/compile.sh
###############################################################################
source "$SCRIPT_DIR/lib/compile.sh"

###############################################################################
# Step 1: ATS Analysis + JD Archival + Project Ranking (direct API call)
# Skipped in stage 2 (app-dir already exists from stage 1)
###############################################################################
if [[ "$OPT_STAGE" != "2" ]]; then

###############################################################################
log "=== Step 1: ATS Analysis & JD Archival + Project Ranking (direct API) ==="

# Handle URL fetch first (replaces Step 0 agent session)
if [[ "$JD_TEXT" == __JD_URL__:* ]]; then
    URL="${JD_TEXT#__JD_URL__:}"
    log "Fetching JD from URL: $URL"
    JD_FETCHED=$($API_PY fetch --url "$URL" 2>/tmp/llm-cv-fetch.log)
    if [[ $? -ne 0 || -z "$JD_FETCHED" ]]; then
        die "Failed to fetch JD from URL. See /tmp/llm-cv-fetch.log. Please paste JD text manually."
    fi
    JD_TEXT="$JD_FETCHED"
    echo "$JD_TEXT" > "$JD_TEMP"
    log "JD fetched (${#JD_TEXT} chars)"
fi

# Run Step 1 via direct API call
STEP1_OUTPUT=$($API_PY step1 \
    --jd-file "$JD_TEMP" \
    --render "$render_mode" \
    --style "$resume_style" \
    --source "$app_source" \
    --language "$language" \
    ${weak_tie_contact:+--weak-tie "$weak_tie_contact"} \
    2>/tmp/llm-cv-step1.log)

STEP1_EXIT=$?
if [[ $STEP1_EXIT -ne 0 ]]; then
    warn "Step 1 API call failed (exit $STEP1_EXIT). Log: /tmp/llm-cv-step1.log"
    tail -30 /tmp/llm-cv-step1.log 2>/dev/null
    die "Step 1 failed."
fi

# The last line of output is the app dir
APP_DIR=$(echo "$STEP1_OUTPUT" | tail -1)

###############################################################################
# Verify Step 1 outputs
###############################################################################
log "Verifying Step 1 outputs..."

# If APP_DIR wasn't captured from step1 output, try to find it
if [[ -z "$APP_DIR" || ! -f "$APP_DIR/ATS_Report.yaml" ]]; then
    # Fallback: find most recent ATS_Report.yaml in Applications
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

fi # end Step 1 block (skipped in stage 2)


###############################################################################
# Stage 1 exit: print app dir + skill gaps for agent to ask user about stuffing
###############################################################################
if [[ "$OPT_STAGE" == "1" ]]; then
    SKILL_GAPS=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    data = yaml.safe_load(f)
gaps = data.get('skill_gaps', [])
print(', '.join(gaps) if gaps else '(none)')
" 2>/dev/null || echo "(unable to read)")

    INITIAL_ATS_SCORE=$("$VENV_PYTHON" -c "
import yaml
with open('$APP_DIR/ATS_Report.yaml') as f:
    data = yaml.safe_load(f)
score = data.get('ats_score_matrix', {}).get('total_score', 0)
print(score)
" 2>/dev/null || echo "0")

    echo "APP_DIR:$APP_DIR"
    echo "SKILL_GAPS:$SKILL_GAPS"
    echo "ATS_SCORE:$INITIAL_ATS_SCORE"
    ok "Stage 1 complete. Agent should ask user about keyword stuffing, then run --stage 2."
    exit 0
fi

###############################################################################
# Duplicate Application Check (before resume rewrite)
###############################################################################
log "=== Duplicate Application Check ==="
set +e
DUP_OUTPUT=$("$VENV_PYTHON" "$SCRIPT_DIR/check_duplicate_application.py" "$APP_DIR" 2>&1)
DUP_EXIT=$?
set -e

if [[ "$DUP_EXIT" -ne 0 && -z "$OPT_FORCE" ]]; then
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
elif [[ "$DUP_EXIT" -ne 0 && -n "$OPT_FORCE" ]]; then
    warn "Duplicate application detected but --force set, proceeding anyway."
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
user_directed_skills="$OPT_USER_SKILLS"

case "$stuffing_choice" in
    "Add all"|"all")
        keyword_stuffing="true"
        ;;
    "Selective"|"selective")
        keyword_stuffing="true"
        if [[ -z "$user_directed_skills" ]]; then
            echo -n "Which skills to add (comma-separated): "
            read user_directed_skills
        fi
        ;;
    "No stuffing"|"none")
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

score_boost_mode="true"

if [[ -n "$OPT_SCORE_BOOST" ]]; then
    case "$OPT_SCORE_BOOST" in
        no|false)
            score_boost_mode="false"
            ok "Score-Boost Mode skipped (from --score-boost no)"
            ;;
        *)
            ok "Score-Boost Mode ACTIVATED (from --score-boost $OPT_SCORE_BOOST)"
            ;;
    esac
else
    ok "Score-Boost Mode ACTIVATED (always on by default)"
fi

###############################################################################
# Step 2 + Step 3: Resume Writer + Cover Letter (parallel direct API calls)
###############################################################################
log "=== Step 2: Resume Writer + ATS Rescoring (direct API) ==="
log "=== Step 3: Cover Letter Writer (parallel with Step 2) ==="

# Map stuffing choice to api_pipeline.py format
stuffing_arg="none"
case "$stuffing_choice" in
    "Add all")    stuffing_arg="all" ;;
    "Selective")  stuffing_arg="selective" ;;
    *)            stuffing_arg="none" ;;
esac

# Launch Step 2 and Step 3 in parallel via bash backgrounding
$API_PY step2 \
    --app-dir "$APP_DIR" \
    --render "$render_mode" \
    --style "$resume_style" \
    --language "$language" \
    --stuffing "$stuffing_arg" \
    --user-skills "$user_directed_skills" \
    --score-boost "$score_boost_mode" \
    --initial-score "$INITIAL_ATS_SCORE" \
    > /tmp/llm-cv-step2.log 2>&1 &
RESUME_PID=$!

$API_PY step3 \
    --app-dir "$APP_DIR" \
    --render "$render_mode" \
    --language "$language" \
    > /tmp/llm-cv-step3.log 2>&1 &
CL_PID=$!

log "Waiting for Step 2 (PID $RESUME_PID) and Step 3 (PID $CL_PID) API calls..."

# Wait for both — use set +e so one failure doesn't kill the other
set +e
wait "$RESUME_PID"
RESUME_EXIT=$?
wait "$CL_PID"
CL_EXIT=$?
set -e

if [[ $RESUME_EXIT -ne 0 ]]; then
    warn "Step 2 API call failed (exit $RESUME_EXIT). Log: /tmp/llm-cv-step2.log"
    tail -20 /tmp/llm-cv-step2.log 2>/dev/null
fi

if [[ $CL_EXIT -ne 0 ]]; then
    warn "Step 3 API call failed (exit $CL_EXIT). Log: /tmp/llm-cv-step3.log"
    tail -20 /tmp/llm-cv-step3.log 2>/dev/null
fi

# Check outputs
if [[ ! -f "$APP_DIR/Resume.yaml" ]]; then
    die "Resume.yaml not found. Step 2 failed. Check /tmp/llm-cv-step2.log"
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

    log "Resume compilation failed: $COMPILE_ERROR. Running fix pass $fix_attempt via API..."

    FIX_ERROR_MSG="$COMPILE_ERROR: $(echo "$COMPILE_LOG" | head -20)"
    $API_PY fix \
        --app-dir "$APP_DIR" \
        --error "$FIX_ERROR_MSG" \
        --language "$language" \
        > /tmp/llm-cv-fix-$fix_attempt.log 2>&1 || true
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

    # Update APP_DIR if the folder was moved by --sort
    if [[ ! -d "$APP_DIR" ]]; then
        NEW_DIR=$(find "$APPLICATIONS_DIR" -name "$(basename "$APP_DIR")" -type d 2>/dev/null | head -1)
        if [[ -n "$NEW_DIR" && -d "$NEW_DIR" ]]; then
            APP_DIR="$NEW_DIR"
            ok "Application folder moved to: $APP_DIR"
        fi
    fi
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
rm -f "${JD_TEMP:-/tmp/llm-cv-jd-NONE.txt}" /tmp/llm-cv-compile.log /tmp/llm-cv-parse.log /tmp/llm-cv-watermark.log /tmp/llm-cv-cl-compile.log /tmp/llm-cv-cl-watermark.log

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
