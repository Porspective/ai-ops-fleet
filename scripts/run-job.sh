#!/bin/bash
# Fleet job runner. Usage: run-job.sh <job-name>
# Runs prompts/<job-name>.md through headless Claude, with cross-machine dedup:
# every machine in the fleet fires the same launchd timers; the first one to start
# a given day's job claims a stamp in the shared git repo, and the others skip.
JOB="$1"
export PATH="$HOME/node/bin:$HOME/bin:$HOME/.local/bin:$PATH"
[ -f "$HOME/.claude-token" ] && export CLAUDE_CODE_OAUTH_TOKEN="$(cat "$HOME/.claude-token")"
OWNER_IMESSAGE="${OWNER_IMESSAGE:-owner@example.com}"   # iMessage handle for failure alerts
cd "$HOME/company" || exit 1
git pull --rebase --quiet 2>/dev/null   # best-effort; refuses on a dirty tree
STAMP=".stamps/$JOB-$(date +%F)"
[ "$JOB" = "weekly-retro" ] && STAMP=".stamps/$JOB-$(date +%G-W%V)"
[ -f "$STAMP" ] && exit 0
# The pull above is unreliable (any modified file makes rebase refuse), which left the
# race guard inert and let a job run twice on two machines. Check the OTHER machine's
# claim straight off the remote instead — fetch touches no working tree.
git fetch -q origin main 2>/dev/null
git cat-file -e "origin/main:$STAMP" 2>/dev/null && exit 0
CLAUDE=$(command -v claude || echo "$HOME/.local/bin/claude")
[ -x "$CLAUDE" ] || exit 0
[ -f "prompts/$JOB.md" ] || exit 0
mkdir -p .stamps logs
LOG="logs/$JOB-$(date +%F).log"
# claim the stamp BEFORE running, and push it, so the other machine skips rather than
# duplicating the run (two copies of the weekly retro once raced and both wrote a full
# report). Released on failure.
touch "$STAMP"
git add -A >/dev/null 2>&1; git commit -qm "claim: $JOB [$(hostname -s)]" >/dev/null 2>&1; git push -q 2>/dev/null
if ! "$CLAUDE" -p --dangerously-skip-permissions "$(cat "prompts/$JOB.md")" > "$LOG" 2>&1; then
  rm -f "$STAMP"
  # job failure is otherwise 100% silent — text the owner the last log line
  osascript <<'APPLESCRIPT' "$OWNER_IMESSAGE" "job $JOB failed on $(hostname -s): $(tail -1 "$LOG" | cut -c1-200)" >/dev/null 2>&1
on run argv
    tell application "Messages"
        send (item 2 of argv) to buddy (item 1 of argv) of service id (id of 1st service whose service type = iMessage)
    end tell
end run
APPLESCRIPT
fi
git add -A >/dev/null 2>&1; git commit -qm "job: $JOB $(date +%F) [$(hostname -s)]" >/dev/null 2>&1; git push -q 2>/dev/null
exit 0
