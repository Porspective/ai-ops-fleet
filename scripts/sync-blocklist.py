#!/usr/bin/env python3
"""Push email/suppression.txt into the sending platform's account-level blocklist.

Local suppression only protects sends made by send-approved.sh. Anything added
in the platform UI, or a sequence already in flight, ignores it. The blocklist
is enforced by the platform, so opt-outs stick.

Endpoint paths follow the commercial cold-email platform this fleet uses (v2 API
with campaigns, leads, and account blocklist); set SENDER_API_BASE/SENDER_API_KEY
for yours and adjust paths if they differ.
"""
import json, os, sys, urllib.error, urllib.request

API = os.environ.get("SENDER_API_BASE", "https://api.example-sender.com/api/v2")
KEY = os.environ.get("SENDER_API_KEY")
SUPP = os.path.expanduser("~/company/email/suppression.txt")

def req(method, path, body=None):
    r = urllib.request.Request(API + path, method=method,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.load(resp)

def main():
    if not KEY:
        print("no SENDER_API_KEY"); return 1
    if not os.path.exists(SUPP):
        print("no suppression list; nothing to sync"); return 0
    local = {l.strip().lower() for l in open(SUPP) if l.strip() and not l.startswith("#")}
    if not local:
        print("suppression list empty"); return 0
    try:
        existing = {e.get("bl_value", "").lower()
                    for e in req("GET", "/block-lists-entries?limit=1000").get("items", [])}
    except urllib.error.HTTPError as e:
        print(f"could not read blocklist: {e}"); return 1
    added = 0
    for addr in sorted(local - existing):
        try:
            req("POST", "/block-lists-entries", {"bl_value": addr})
            added += 1
        except Exception as e:
            print(f"FAIL {addr}: {e}")
    print(f"blocklist synced: {added} added, {len(local & existing)} already present")
    return 0

if __name__ == "__main__":
    sys.exit(main())
