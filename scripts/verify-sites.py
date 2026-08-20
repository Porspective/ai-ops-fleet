#!/usr/bin/env python3
"""Send-day reverification: every email in the queue asserts something the operator
observed on the prospect's site. If the site changed between drafting and sending, the
claim is false and the email must not go. This snapshots the observable signals, then diffs.

  verify-sites.py snapshot <queue-dir>            -> email/verification/<date>.json
  verify-sites.py check <queue-dir> <baseline>    -> exits 1 if any site drifted

Signals are deliberately coarse (status, title, copyright years, viewport meta, body
hash). They catch the failure that matters: a prospect relaunched or fixed the exact
thing the email calls out.
"""
import concurrent.futures as cf, csv, datetime, hashlib, json, os, re, ssl, sys, urllib.request

ROOT = os.path.expanduser("~/company")
import glob as _glob
CSVS = sorted(_glob.glob(f"{ROOT}/email/prospects/*.csv"))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def sites_by_email():
    m = {}
    for path in CSVS:
        if not os.path.exists(path): continue
        for row in csv.DictReader(open(path)):
            e, w = (row.get("email") or "").strip().lower(), (row.get("website") or "").strip()
            if e: m.setdefault(e, {"website": w, "name": row.get("name", "")})
    return m

def queued(qdir):
    out = []
    for fn in sorted(os.listdir(qdir)):
        if not fn.endswith(".md") or fn.startswith("_"): continue
        txt = open(os.path.join(qdir, fn)).read()
        m = re.search(r"^TO:\s*(\S+)", txt, re.M)
        if m: out.append((fn[:-3], m.group(1).strip().lower()))
    return out

def fetch(url):
    if not url: return {"state": "no-site"}
    if not url.startswith("http"): url = "https://" + url
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            body = r.read(400_000).decode("utf-8", "replace")
            status, final = r.status, r.geturl()
    except Exception as e:
        return {"state": "error", "error": str(e)[:120]}
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    return {
        "state": "ok", "status": status, "final_url": final,
        "title": " ".join(title.group(1).split())[:120] if title else "",
        # the two signals most emails lean on:
        "years": sorted(set(re.findall(r"(?:©|&copy;|copyright)\s*\D{0,12}(19\d{2}|20\d{2})", body, re.I))),
        "viewport": bool(re.search(r'<meta[^>]+name=["\']?viewport', body, re.I)),
        "hash": hashlib.sha256(re.sub(r"\s+", " ", body).encode()).hexdigest()[:16],
    }

def collect(qdir):
    sites, rows = sites_by_email(), queued(qdir)
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch, sites.get(em, {}).get("website", "")): (slug, em) for slug, em in rows}
        return {slug: dict(email=em, website=sites.get(em, {}).get("website", ""), **f.result())
                for f, (slug, em) in ((f, futs[f]) for f in cf.as_completed(futs))}

def main():
    mode, qdir = sys.argv[1], sys.argv[2]
    if mode == "snapshot":
        snap = collect(qdir)
        out = f"{ROOT}/email/verification/{datetime.date.today()}.json"
        json.dump(snap, open(out, "w"), indent=1, sort_keys=True)
        print(f"snapshot {len(snap)} sites -> {out}")
        return 0
    base = json.load(open(sys.argv[3]))
    now, drift = collect(qdir), []
    for slug, cur in sorted(now.items()):
        old = base.get(slug)
        if not old:
            drift.append((slug, "new in queue, no baseline")); continue
        # hash is stored for forensics but NOT gated on: dynamic pages (nonces, timestamps)
        # re-hash differently seconds apart — 5 of 61 false-positived on an immediate re-run.
        for k in ("state", "status", "years", "viewport", "title"):
            if old.get(k) != cur.get(k):
                drift.append((slug, f"{k}: {old.get(k)!r} -> {cur.get(k)!r}")); break
    for slug, why in drift: print(f"DRIFT {slug}: {why}")
    print(f"{len(drift)} of {len(now)} drifted")
    return 1 if drift else 0

if __name__ == "__main__":
    sys.exit(main())
