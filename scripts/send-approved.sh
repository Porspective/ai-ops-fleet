#!/bin/bash
# Push an APPROVED email queue day to the sending platform.
# Usage: send-approved.sh YYYY-MM-DD [daily_cap]
# Only run AFTER the owner approves the batch. Requires SENDER_API_KEY in ~/company/.env.
#
# This script is the ONLY path from queue to outbox, and it fails closed:
#   1. no verification baseline        -> abort
#   2. any prospect site drifted       -> abort
#   3. unfilled footer placeholder     -> abort (CAN-SPAM postal address gate)
#   4. address on suppression list     -> skip
set -e
DAY="$1"; CAP="${2:-15}"  # day-1 staging rule: 10-15 max, inspect results, then ramp
[ -n "$DAY" ] || { echo "usage: send-approved.sh YYYY-MM-DD [cap]"; exit 1; }
QDIR="$HOME/company/email/queue/$DAY"
[ -d "$QDIR" ] || { echo "no queue at $QDIR"; exit 1; }
source "$HOME/company/.env"
[ -n "$SENDER_API_KEY" ] || { echo "no SENDER_API_KEY"; exit 1; }
SENDER_API_BASE="${SENDER_API_BASE:-https://api.example-sender.com/api/v2}"

# Send-day reverification. Every email asserts something observed on the prospect's site;
# if the site changed since drafting, the claim is false. Fail closed.
BASE="$(/bin/ls -1 "$HOME/company/email/verification/"*.json 2>/dev/null | tail -1)"
[ -n "$BASE" ] || { echo "no verification baseline — run: scripts/verify-sites.py snapshot $QDIR"; exit 1; }
if ! python3 "$HOME/company/scripts/verify-sites.py" check "$QDIR" "$BASE"; then
  echo "ABORT: sites drifted since $BASE. Re-check those emails, then re-snapshot."; exit 1
fi

# Push the suppression list to the platform's blocklist so opt-outs are enforced
# platform-side, not just by this script's local check.
python3 "$HOME/company/scripts/sync-blocklist.py" || echo "WARN: blocklist sync failed, local suppression still applies"

python3 - "$QDIR" "$CAP" <<'PY'
import json, os, re, sys, urllib.request

qdir, cap = sys.argv[1], int(sys.argv[2])
API = os.environ.get("SENDER_API_BASE", "https://api.example-sender.com/api/v2")
KEY = os.environ["SENDER_API_KEY"]

def req(method, path, body=None):
    r = urllib.request.Request(API + path, method=method,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.load(resp)

# find-or-create campaign with variable-driven sequence
name = os.environ.get("CAMPAIGN_NAME", "Launch Campaign")
camps = req("GET", "/campaigns?limit=100").get("items", [])
camp = next((c for c in camps if c.get("name") == name), None)
if not camp:
    camp = req("POST", "/campaigns", {
        "name": name,
        "campaign_schedule": {"schedules": [{"name": "workday", "timing": {"from": "08:30", "to": "16:30"},
            "days": {"1": True, "2": True, "3": True, "4": True, "5": True}, "timezone": "America/Chicago"}]},
        "sequences": [{"steps": [
            {"type": "email", "delay": 0, "variants": [{"subject": "{{subjectLine}}", "body": "{{emailBody}}"}]},
            {"type": "email", "delay": 3, "variants": [{"subject": "re: {{subjectLine}}", "body": "{{bumpBody}}"}]},
            {"type": "email", "delay": 5, "variants": [{"subject": "re: {{subjectLine}}", "body": "{{breakupBody}}"}]},
        ]}],
        "daily_limit": cap,
        "stop_on_reply": True, "link_tracking": False, "open_tracking": False,
    })
    print("campaign created:", camp["id"])
else:
    print("campaign exists:", camp["id"])

def field(txt, key):
    m = re.search(rf"^{key}:\s*(.+?)(?=\n[A-Z]+:|\Z)", txt, re.S | re.M)
    return m.group(1).strip() if m else ""

supp_path = os.path.expanduser("~/company/email/suppression.txt")
suppressed = set()
if os.path.exists(supp_path):
    suppressed = {l.strip().lower() for l in open(supp_path) if l.strip()}

sent = 0
for fn in sorted(os.listdir(qdir)):
    if not fn.endswith(".md") or fn.startswith("_"): continue
    if sent >= cap: print(f"cap {cap} reached"); break
    txt = open(os.path.join(qdir, fn)).read()
    to = field(txt, "TO")
    if not to or "@" not in to: continue
    if to.lower() in suppressed: print(f"SUPPRESSED {to}"); continue
    if "[POSTAL ADDRESS" in txt: print(f"BLOCKED {fn}: footer address placeholder unfilled"); break
    try:
        req("POST", "/leads", {
            "campaign": camp["id"], "email": to, "skip_if_in_campaign": True,
            "custom_variables": {
                "subjectLine": field(txt, "SUBJECT"), "emailBody": field(txt, "BODY"),
                "bumpBody": field(txt, "BUMP"), "breakupBody": field(txt, "BREAKUP"),
                "segment": field(txt, "SERVICE-FIT") or "default",  # segment attribution for reply analysis
            }})
        sent += 1
    except Exception as e:
        print(f"FAIL {to}: {e}")
print(f"uploaded {sent} leads")

# activate
try:
    req("POST", f"/campaigns/{camp['id']}/activate")
    print("campaign ACTIVE — platform sends per schedule/cap")
except Exception as e:
    print("activate manually in the platform UI:", e)
PY
