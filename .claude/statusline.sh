#!/usr/bin/env bash
# statusline.sh — Claude Code statusLine script
#
# Reads JSON from stdin, prints a single status line on stdout.
# Designed to be fast (no network calls, minimal subprocesses).
#
# Shows:
#   <model>  <cwd-basename>  [git-branch*]  [venv]  <HH:MM>
#
# Install: in .claude/settings.local.json
#   {
#     "statusLine": {
#       "type": "command",
#       "command": "/absolute/path/to/statusline.sh"
#     }
#   }
#
# Don't forget to: chmod +x statusline.sh

set -u

input="$(cat)"

get_field() {
    local path="$1"
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$input" | jq -r "$path // empty" 2>/dev/null
    else
        local key="${path##*.}"
        printf '%s' "$input" | sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" | head -n1
    fi
}

if [ -t 1 ]; then
    DIM=$'\033[2m'
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
    BLUE=$'\033[34m'
    GREEN=$'\033[32m'
    YELLOW=$'\033[33m'
    MAGENTA=$'\033[35m'
    CYAN=$'\033[36m'
    GREY=$'\033[90m'
else
    DIM=""; BOLD=""; RESET=""; BLUE=""; GREEN=""; YELLOW=""; MAGENTA=""; CYAN=""; GREY=""
fi

model="$(get_field '.model.display_name')"
[ -z "$model" ] && model="$(get_field '.model.id')"
[ -z "$model" ] && model="claude"

cwd="$(get_field '.workspace.current_dir')"
[ -z "$cwd" ] && cwd="$(get_field '.cwd')"
[ -z "$cwd" ] && cwd="$PWD"
cwd_short="$(basename "$cwd")"

git_part=""
if command -v git >/dev/null 2>&1; then
    branch="$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
              || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)"
    if [ -n "$branch" ]; then
        dirty=""
        if [ -n "$(git -C "$cwd" status --porcelain 2>/dev/null | head -n1)" ]; then
            dirty="${YELLOW}*${RESET}"
        fi
        git_part="${MAGENTA}${branch}${RESET}${dirty}"
    fi
fi

venv_part=""
if [ -n "${VIRTUAL_ENV:-}" ]; then
    venv_part="${GREEN}($(basename "$VIRTUAL_ENV"))${RESET}"
fi

time_part="${GREY}$(date +%H:%M)${RESET}"

parts=("${BOLD}${CYAN}⏵${RESET} ${BOLD}${model}${RESET}" "${BLUE}${cwd_short}${RESET}")
[ -n "$git_part" ] && parts+=("${git_part}")
[ -n "$venv_part" ] && parts+=("${venv_part}")
parts+=("${time_part}")

output=""
for p in "${parts[@]}"; do
    [ -n "$output" ] && output+="  "
    output+="$p"
done

printf '%s' "$output"