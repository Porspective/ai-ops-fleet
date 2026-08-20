#!/bin/bash
# Fleet state sync — pull + push ~/company. Runs every 15 min on always-on machines.
cd "$HOME/company" || exit 1
git pull --rebase --quiet 2>/dev/null
git add -A >/dev/null 2>&1
git commit -qm "sync $(date +%F-%H%M) [$(hostname -s)]" >/dev/null 2>&1
git push -q 2>/dev/null
exit 0
