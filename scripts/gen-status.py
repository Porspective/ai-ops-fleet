#!/usr/bin/env python3
"""Generate docs/status.html — a public, static status page for the fleet.

Reads real evidence from the private ~/company state repo (git commit
history, matched by workflow-specific commit-message patterns) and renders
a dark dashboard: per-workflow last-run time, a derived "today's output"
count, and a 7-day/6-week run streak.

No prospect data, no application data, no recipient data, no local paths in
the output — only counts and dates pulled from commit metadata.

ponytail: streak/last-run signal is git commit history, not launchd/log
files (none were found on this machine — logs/ was empty, launchctl list
showed no loaded fleet jobs). If real log files ever exist, prefer those;
commit history is the honest fallback, not a workaround.
"""
import os
import re
import subprocess
from datetime import date, datetime, timedelta

COMPANY = os.path.expanduser("~/company")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "status.html")
TODAY = date.today()


def git_log(grep_pattern):
    """Return [(date, subject), ...] newest first for commits whose subject matches grep_pattern (regex, case-insensitive)."""
    try:
        raw = subprocess.run(
            ["git", "-C", COMPANY, "log", "--format=%ad\t%s", "--date=short",
             "--all", "-i", "-E", f"--grep={grep_pattern}"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except Exception:
        return []
    out = []
    for line in raw.splitlines():
        if "\t" not in line:
            continue
        d, subj = line.split("\t", 1)
        try:
            out.append((datetime.strptime(d, "%Y-%m-%d").date(), subj))
        except ValueError:
            continue
    return out


def first_number(text):
    m = re.search(r"\d[\d,]*", text)
    return m.group(0) if m else None


def daily_streak(commits, days=7):
    """Dot per calendar day, most recent `days` days, filled if a commit landed that day."""
    have = {d for d, _ in commits}
    dots = []
    for i in range(days - 1, -1, -1):
        d = TODAY - timedelta(days=i)
        dots.append(d in have)
    return dots


def weekly_streak(commits, weeks=6):
    have = {d.isocalendar()[:2] for d, _ in commits}
    dots = []
    for i in range(weeks - 1, -1, -1):
        d = TODAY - timedelta(weeks=i)
        dots.append(d.isocalendar()[:2] in have)
    return dots


def render_dots(dots):
    return "".join(f'<span class="dot {"on" if v else "off"}"></span>' for v in dots)


def relative(d):
    if d is None:
        return "—"
    delta = (TODAY - d).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "yesterday"
    return f"{delta}d ago ({d.isoformat()})"


WORKFLOWS = [
    dict(
        name="Daily Briefing",
        purpose="One-line status per active workflow, texted to the owner every morning.",
        cadence="daily",
        grep=r"job: daily-briefing|briefing sent",
        output_re=None,
        output_label="sent",
    ),
    dict(
        name="Morning Intel",
        purpose="AI/frontier news digest, filtered and summarized before the day starts.",
        cadence="daily",
        grep=r"job: morning-intel",
        output_re=None,
        output_label="digest",
    ),
    dict(
        name="Email Pipeline",
        purpose="Drafts, re-verifies, and stages the outbound email queue; suppression and volume gates enforced on every send.",
        cadence="daily",
        grep=r"job: email-pipeline|email autopilot|email: stage and push",
        output_re=r"\((\d[\d,]*)\)|(\d[\d,]*)\s+(new (?:replies|bounces)|(?:new\s+)?(?:emails|drafts|queued))",
        output_label="drafted",
    ),
    dict(
        name="Lead Harvest",
        purpose="Nightly local-business lead pipeline: public registries + map search, deduped and scored into lanes.",
        cadence="daily",
        grep=r"nightly harvest|lawn grid harvest",
        output_re=r"(\d[\d,]*)\s+(?:gmaps rows|businesses)",
        output_label="leads found",
    ),
    dict(
        name="Weekly Retro",
        purpose="Self-audit pass over the week's logs and commits; rewrites the status board's focus.",
        cadence="weekly",
        grep=r"weekly-retro",
        output_re=None,
        output_label="run",
    ),
    dict(
        name="Sync",
        purpose="Git pull/push backstop every 15 minutes so no machine's output goes untracked.",
        cadence="daily",
        grep=r"^sync ",
        output_re=None,
        output_label="syncs",
    ),
]


def build_card(wf):
    commits = git_log(wf["grep"])
    last_date = commits[0][0] if commits else None
    last_subj = commits[0][1] if commits else ""

    output = "—"
    if last_date == TODAY:
        if wf["output_re"]:
            m = re.search(wf["output_re"], last_subj, re.I)
            if m:
                groups = [g for g in m.groups() if g]
                num = groups[0] if groups else None
                label = groups[1] if len(groups) > 1 else wf["output_label"]
                if num:
                    output = f'{num} {label}'.strip()
        else:
            output = f'1 {wf["output_label"]}'

    if wf["cadence"] == "weekly":
        dots = weekly_streak(commits)
        streak_label = "6-week streak"
    else:
        dots = daily_streak(commits)
        streak_label = "7-day streak"

    return f"""
    <div class="card">
      <div class="card-head">
        <h2>{wf['name']}</h2>
        <span class="badge {'live' if last_date else 'dark'}">{'live' if last_date else 'no evidence'}</span>
      </div>
      <p class="purpose">{wf['purpose']}</p>
      <div class="stats">
        <div class="stat"><span class="label">Last run</span><span class="value">{relative(last_date)}</span></div>
        <div class="stat"><span class="label">Today</span><span class="value">{output}</span></div>
      </div>
      <div class="streak">
        <span class="label">{streak_label}</span>
        <div class="dots">{render_dots(dots)}</div>
      </div>
    </div>"""


def main():
    cards = "\n".join(build_card(wf) for wf in WORKFLOWS)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ai-ops-fleet — live status</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #0b0d12; --card: #12151c; --border: #232733; --text: #e6e9f0;
    --muted: #8890a3; --accent: #5ee6c2; --dot-on: #5ee6c2; --dot-off: #262b38;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 48px 24px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  header {{ margin-bottom: 36px; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 6px; }}
  .sub {{ color: var(--muted); font-size: 0.95rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .card-head h2 {{ font-size: 1.05rem; margin: 0; }}
  .badge {{ font-size: 0.7rem; padding: 3px 8px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.04em; }}
  .badge.live {{ background: rgba(94,230,194,0.15); color: var(--accent); }}
  .badge.dark {{ background: rgba(136,144,163,0.15); color: var(--muted); }}
  .purpose {{ color: var(--muted); font-size: 0.85rem; line-height: 1.4; min-height: 2.6em; margin: 0 0 16px; }}
  .stats {{ display: flex; gap: 24px; margin-bottom: 14px; }}
  .stat {{ display: flex; flex-direction: column; gap: 2px; }}
  .stat .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
  .stat .value {{ font-size: 0.95rem; }}
  .streak .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; display: block; margin-bottom: 6px; }}
  .dots {{ display: flex; gap: 5px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .dot.on {{ background: var(--dot-on); }}
  .dot.off {{ background: var(--dot-off); }}
  footer {{ margin-top: 36px; color: var(--muted); font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>ai-ops-fleet — live status</h1>
    <div class="sub">Scheduled workflows running unattended since July 2026. Generated {generated}.</div>
  </header>
  <div class="grid">
    {cards}
  </div>
  <footer>Counts and dates are derived from real run evidence, not projected. A dash means the metric couldn't be derived from that evidence.</footer>
</div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
