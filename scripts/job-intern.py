#!/usr/bin/env python3
"""Job-listing intern — runs on the headless node every 2h via launchd.
Polls free job APIs for new postings, has a local LLM (Ollama) score fit,
appends matches to jobsearch/intern-feed.md, commits, and texts on hot hits.
Zero paid APIs. State: ~/.job-intern-seen.json
"""
import json, os, re, subprocess, urllib.request, time

HOME = os.path.expanduser("~")
SEEN_PATH = os.path.join(HOME, ".job-intern-seen.json")
FEED = os.path.join(HOME, "company/jobsearch/intern-feed.md")
OLLAMA = "http://localhost:11434/api/generate"
OWNER_IMESSAGE = os.environ.get("OWNER_IMESSAGE", "owner@example.com")

# tune to the roles you want surfaced
KEYWORDS = re.compile(
    r"ai operations|ai enablement|automation specialist|workflow automation|"
    r"ai implementation|claude|prompt|llm ops|ai ops|business operations analyst|"
    r"revenue operations|marketing operations|implementation specialist", re.I)

# one paragraph the scorer judges every posting against: skills/stack, education,
# location constraint, salary floor, explicit disqualifiers
PROFILE = ("Candidate: builds and operates AI workflow systems (Claude Code, MCP, "
           "launchd, Git, APIs); {{EDUCATION}}; {{LOCATION_CONSTRAINT}}; targets "
           "{{SALARY_FLOOR}}+; NOT senior eng roles needing 5+ yrs; "
           "NOT offshore-rate roles under {{HOURLY_FLOOR}}/hr.")

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (job-intern)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def get_jobs():
    jobs = []
    # Remotive API
    try:
        d = json.loads(fetch("https://remotive.com/api/remote-jobs?limit=100"))
        for j in d.get("jobs", []):
            jobs.append({"id": f"remotive-{j['id']}", "title": j["title"], "company": j["company_name"],
                         "url": j["url"], "loc": j.get("candidate_required_location", ""),
                         "salary": j.get("salary", ""), "desc": re.sub(r"<[^>]+>", " ", j.get("description", ""))[:1500]})
    except Exception as e:
        print("remotive fail:", e)
    # RemoteOK API
    try:
        d = json.loads(fetch("https://remoteok.com/api"))
        for j in d[1:]:
            if not isinstance(j, dict) or not j.get("id"): continue
            jobs.append({"id": f"remoteok-{j['id']}", "title": j.get("position", ""), "company": j.get("company", ""),
                         "url": j.get("url", ""), "loc": j.get("location", ""),
                         "salary": f"{j.get('salary_min','')}-{j.get('salary_max','')}",
                         "desc": re.sub(r"<[^>]+>", " ", j.get("description", ""))[:1500]})
    except Exception as e:
        print("remoteok fail:", e)
    return jobs

def qwen_score(job):
    prompt = (f"{PROFILE}\n\nJob: {job['title']} at {job['company']}. Location req: {job['loc']}. "
              f"Salary: {job['salary']}. Description: {job['desc'][:1200]}\n\n"
              "Score 0-10 how strong a fit this job is for the candidate (10=apply today). "
              "Location-eligibility required; ineligible roles score 0. "
              "Reply with ONLY the number.")
    try:
        body = json.dumps({"model": "qwen3:8b", "prompt": prompt, "stream": False,
                           "think": False,  # qwen3 thinking otherwise eats the num_predict budget -> empty response, score 0
                           "options": {"num_predict": 10}}).encode()
        r = json.loads(fetch_post(OLLAMA, body))
        m = re.search(r"\d+", r.get("response", "0"))
        return min(10, int(m.group())) if m else 0
    except Exception as e:
        print("qwen fail:", e); return -1  # -1 = unscored, still logged if keyword-hot

def fetch_post(url, body):
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode()

def main():
    seen = set()
    if os.path.exists(SEEN_PATH):
        seen = set(json.load(open(SEEN_PATH)))
    fresh = [j for j in get_jobs() if j["id"] not in seen and KEYWORDS.search(j["title"] + " " + j["desc"])]
    hot, logged = [], 0
    lines = []
    for j in fresh:
        score = qwen_score(j)
        seen.add(j["id"])
        if score >= 6 or score == -1:
            logged += 1
            stamp = time.strftime("%Y-%m-%d %H:%M")
            lines.append(f"- [{stamp}] **{j['title']}** — {j['company']} · {j['loc'] or 'remote?'} · "
                         f"{j['salary'] or 'salary unlisted'} · qwen:{score} · {j['url']}")
            if score >= 8:
                hot.append(j)
    if lines:
        os.makedirs(os.path.dirname(FEED), exist_ok=True)
        with open(FEED, "a") as f:
            f.write("\n".join(lines) + "\n")
    json.dump(sorted(seen)[-5000:], open(SEEN_PATH, "w"))
    # commit + push via company repo
    if lines:
        subprocess.run(["git", "-C", os.path.join(HOME, "company"), "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", os.path.join(HOME, "company"), "commit", "-qm",
                        f"job-intern: +{logged} listings"], capture_output=True)
        subprocess.run(["git", "-C", os.path.join(HOME, "company"), "push", "-q"], capture_output=True)
    # text the owner only for hot hits (osascript may fail on a headless node; best-effort)
    if hot:
        msg = "HOT JOB: " + "; ".join(f"{j['title']} @ {j['company']} ({j['salary'] or 'salary ?'})" for j in hot[:2])
        subprocess.run(["osascript", "-e",
                        f'tell application "Messages" to send "{msg[:180]}" to participant '
                        f'"{OWNER_IMESSAGE}" of (1st account whose service type is iMessage)'],
                       capture_output=True)
    print(f"fresh:{len(fresh)} logged:{logged} hot:{len(hot)}")

if __name__ == "__main__":
    main()
