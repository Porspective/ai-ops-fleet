# ai-ops-fleet

A two-machine fleet that runs a one-person company's back office on a schedule: intelligence digests, a daily owner briefing, cold-email prospecting with send-day re-verification, lead-generation scraping pipelines, and a weekly self-audit — with verification gates, suppression compliance, and an owner kill switch on every outbound lane. Designed and operated by Porter Robertson; implementation written with Claude Code under his direction, running daily since July 2026. This repo is a sanitized copy of the live system: real scripts and prompts, with names, handles, keys, and business data replaced by `{{PLACEHOLDERS}}`. It is a working reference, not a one-click install.

## Architecture

```mermaid
flowchart TB
    subgraph state["private git repo — \"state\""]
        STATE["STATE.md · DECISIONS.md<br/>prompts/ · .stamps/ · queues"]
    end

    subgraph hq["HQ (laptop)"]
        HQNOTE["travels with the owner<br/>rich MCP: iMessage, browser, artifacts"]
    end

    subgraph mule["Mule (headless M1, 24/7)"]
        MULENOTE["broken screen, sleep disabled<br/>launchd timers, local Ollama for cheap scoring"]
    end

    hq <-- "pull / push" --> state
    mule <-- "pull / push" --> state

    hq --> RUN["scripts/run-job.sh<br/>claim-before-run dedup"]
    mule --> RUN
    RUN --> CLAUDE["claude -p \"$(cat prompts/&lt;job&gt;.md)\""]
    CLAUDE --> OUT["outputs: digests, briefing text,<br/>email queue, prospect leads, filled tabs"]
    OUT --> GATE{{"OWNER APPROVAL (human)<br/>nothing external sends without it"}}
    GATE --> SEND["scripts/send-approved.sh<br/>fail-closed verification gates"]
```

### The pieces

**Two machines, one job list.** Both machines load the same launchd plists and fire the same jobs. Availability comes from redundancy, not from either machine being reliable: the laptop sleeps and travels; the headless node is a salvaged M1 with a broken screen.

**Git-synced state.** `~/company` is a private repo holding the live status board (`STATE.md`), decision log, prompts, queues, and job stamps. Every machine pulls before work and pushes after; `scripts/sync.sh` runs every 15 minutes as a backstop. Uncommitted work is invisible work — the weekly audit once wrongly downgraded a whole department because its output sat untracked for an hour.

**Claim-before-run dedup.** `scripts/run-job.sh` claims a per-day stamp file *in the shared repo, before running*, and checks the other machine's claim against `origin/main` with `git fetch` + `git cat-file` — deliberately not `git pull`, because a rebase refuses on a dirty tree and a guard that can be blocked by dirt is no guard. The comments in that script record the four distinct ways the race was lost before this version.

**Fail-closed verification gates.** `scripts/send-approved.sh` is the only path from email queue to outbox, and it aborts unless everything checks out: a verification baseline must exist; `scripts/verify-sites.py` must confirm no prospect site drifted since drafting (every email asserts something observed on the site — if the site changed, the claim is false); the compliance footer placeholder must be filled; suppressed addresses are skipped and the suppression list is pushed to the sending platform's account-level blocklist first (`scripts/sync-blocklist.py`) so opt-outs are enforced even for sequences already in flight.

**Outbound gates.** Every outbound email passes send-day re-verification and a suppression-list check before it can load; volume is capped per day, replies pause a lane automatically, and the owner can halt any lane with one word. Money and anything irreversible stay manual.

**Self-audit loop.** Sunday's `weekly-retro` job runs an auditor persona (Vera) over the repo, the stamps, the logs, and the session transcripts — including the CEO session's own claims. Its findings rewrite the status board's focus for the week. Several fixes in these scripts started as retro findings, including the discovery that four consecutive "successful" morning runs had died on an expired token and nobody noticed.

**Cheap local scoring.** `scripts/job-intern.py` polls free job-board APIs every 2 hours and has a local 8B model (Ollama) score each posting against a candidate profile — zero marginal cost per run, so it can be always-on.

## Workflows

| Workflow | Schedule | What it does | Failure handling |
|---|---|---|---|
| **morning-intel** | ~6:05 daily, both machines | AI/frontier news, world-news filter, a chat-transcript audit for wasted tool calls, a YouTube learning sweep | Skips sweeps it lacks data for (e.g. no transcripts on this machine) instead of failing the whole job |
| **daily-briefing** | ~10:57 daily | One-line status per active department, ≤3 concrete owner tasks with deadlines, blockers, one intel highlight — under ~120 words, texted | Delivery falls back iMessage MCP → osascript → push notification → skip, in that order |
| **email-pipeline** | weekdays, HQ | Prospects, drafts, and verifies a send queue; never sends | `send-approved.sh` re-checks the queue at send time — drafting-time truth can go stale |
| **send-approved.sh (gate)** | on demand, owner-triggered | The only path from queue to outbox: verification baseline required, site-drift re-check, suppression list pushed to the platform first | Aborts closed on any missing check — a partial pass is a fail |
| **nightly lead harvest** | ~2am, mule | Local-lawn-service lead pipeline: a state pesticide-applicator registry (public API, ~4,200 licensed companies), a Google Maps scrape (~500-query city×service grid), a Craigslist services pull, and a nightly jobs-board pull used as a hiring-signal sharpener — enriched, deduped, scored into email/call/social lanes | Each stage writes only new/changed rows to SQLite; a stage failing doesn't corrupt prior nights' data |
| **weekly-retro (self-audit)** | Sun ~16:17 | Audits every department and the CEO session itself against evidence — files, stamps, logs, transcripts — rewrites the status board's weekly focus | Bias toward deleting stale status over adding new narrative; explicitly checks whether earlier "fixed" claims actually landed |
| **sync** | every 15 min, both machines | Git pull/push backstop so no machine's output goes untracked | Runs regardless of whether any job fired that cycle |

That's 9 distinct scheduled workflows plus the always-on `sync` backstop and the on-demand send gate.

## Numbers

These are real counts from the live system, not projections.

- **9 scheduled workflows** running across 2 machines since July 2026.
- **~4,200 licensed companies** in a state pesticide-applicator registry, cross-referenced against a ~500-query Google Maps grid, for the nightly lead-harvest pipeline.
- **A self-audit that caught a silently failing job**: four consecutive "successful" morning runs had actually died on an expired token before anyone noticed — found by the weekly retro reading logs, not by a person watching a dashboard.

## Design principles

- **Verification before send.** Nothing goes out on a claim made at draft time. If an email asserts something about a prospect's website, the site gets re-checked the day it sends.
- **Fail-closed gates.** A verification step that can't complete blocks the send. A gate you can bypass by having it fail isn't a gate.
- **Logs as source of truth.** Status is derived from what actually ran — stamps, git history, session transcripts — not from what a job claimed it did. The weekly audit exists specifically to catch the gap between the two.
- **Model-cost routing.** Cheap, fast models (a local 8B Ollama model, Haiku-tier agents) handle high-volume mechanical work — scoring postings, single-field form fills. Higher-capability models are reserved for the parts that need judgment — cover text, gate-screening ambiguous postings, coordinating the rest.
- **Human owns anything irreversible.** Scheduled jobs draft, tailor, and fill. They never send an email or spend money. That line does not move regardless of how far the automation gets.

## Built with Claude Code

This fleet was designed and is operated day to day by one person using Claude Code — the scheduling, the scripts, the prompts, and the persona-based subagents that stand in as "staff" (an auditor, a revenue lead, a finder) are all AI-assisted implementation under direct human direction. It's been running unattended, on a schedule, since July 2026, and its own failures (a stale token, a race condition, a subject-line leak) get found by another automated pass — the weekly self-audit — rather than staying invisible. For AI-ops and automation roles, that's the pitch: not a demo, a system that has been operating a real (if small) business continuously and has the scar tissue to show for it.

## Repo layout

```
scripts/    the runner, sync, gates, and scrapers (bash + stdlib-only python)
prompts/    one markdown prompt per scheduled job, fed to `claude -p`
launchd/    plist patterns: interval-fired and calendar-fired examples
agents/     persona files for the "staff" — spawned as subagents for
            audits, revenue takes, finding tools, accountability
docs/       case studies from the live system
```

## Setup notes

1. Create a **private** state repo at `~/company` with `prompts/`, `email/`, `jobsearch/`, a `STATE.md`, and a `.env` (chmod 600, gitignored) for keys.
2. Install the Claude Code CLI on each machine; on headless nodes store a long-lived token at `~/.claude-token` (`run-job.sh` exports it).
3. Fill the `{{PLACEHOLDERS}}` in `prompts/` and `agents/`, and set `OWNER_IMESSAGE`, `SENDER_API_BASE`, `SENDER_API_KEY` where used.
4. Copy `launchd/*.plist` to `~/Library/LaunchAgents/` (edit paths/times), `launchctl load` each.
5. Disable sleep on the always-on node. Timers do not fire on a sleeping Mac, and half this repo's comment history is the scar tissue from learning which failures that causes.
6. iMessage sending needs macOS Automation permission (System Settings → Privacy & Security → Automation → allow control of Messages).

## What this is not

No dashboard, no queue service, no containers, no framework. The coordination layer is a git repo and stamp files, because that was the smallest thing that survived contact with two unreliable machines. Where a mechanism looks over-careful — the fetch-based race check, the send-day re-verification, the claim-before-run ordering — the comment next to it names the specific incident that made it that careful.
