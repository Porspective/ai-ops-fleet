# ai-ops-fleet

A small fleet of Macs that runs a one-person company's back office on a schedule: morning intelligence digests, a daily owner briefing, a weekly self-audit, cold-email queue building, and job-search scraping — with a human approval gate in front of anything that leaves the machine.

Designed and operated by Porter Robertson; implementation written with Claude Code under his direction. This repo is a sanitized copy of the live system: real scripts and prompts, with names, handles, keys, and business data replaced by `{{PLACEHOLDERS}}`. It is a working reference, not a one-click install.

## Architecture

```
                        ┌────────────────────────────────┐
                        │   private git repo ("state")   │
                        │  STATE.md · DECISIONS.md ·     │
                        │  prompts/ · .stamps/ · queues  │
                        └──────▲──────────────▲──────────┘
                         pull/push        pull/push
                  ┌────────────┴───┐  ┌───┴────────────────┐
                  │  HQ (laptop)   │  │  Node (headless,   │
                  │  travels with  │  │  24/7, broken      │
                  │  the owner;    │  │  screen; launchd   │
                  │  rich MCP:     │  │  timers, local     │
                  │  iMessage,     │  │  Ollama for cheap  │
                  │  browser, etc. │  │  scoring)          │
                  └───────┬────────┘  └────────┬───────────┘
                          │    same job list,  │
                          │    both fire —     │
                          │    stamps dedup    │
                          ▼                    ▼
              scripts/run-job.sh  →  claude -p "$(cat prompts/<job>.md)"
                          │
                          ▼
        outputs: digest files, briefing texts, email queue, job leads
                          │
                          ▼
              ┌───────────────────────────┐
              │  OWNER APPROVAL (human)   │  ← nothing external sends without it
              └───────────┬───────────────┘
                          ▼
              scripts/send-approved.sh (fail-closed gates, see below)
```

### The pieces

**Two machines, one job list.** Both machines load the same launchd plists and fire the same jobs. Availability comes from redundancy, not from either machine being reliable: the laptop sleeps and travels; the headless node is a $0 salvaged M1 with a broken screen.

**Git-synced state.** `~/company` is a private repo holding the live status board (`STATE.md`), decision log, prompts, queues, and job stamps. Every machine pulls before work and pushes after; `scripts/sync.sh` runs every 15 minutes as a backstop. Uncommitted work is invisible work — the weekly audit once wrongly downgraded a whole department because its output sat untracked for an hour.

**Claim-before-run dedup.** `scripts/run-job.sh` claims a per-day stamp file *in the shared repo, before running*, and checks the other machine's claim against `origin/main` with `git fetch` + `git cat-file` — deliberately not `git pull`, because a rebase refuses on a dirty tree and a guard that can be blocked by dirt is no guard. The comments in that script record the four distinct ways the race was lost before this version.

**Fail-closed verification gates.** `scripts/send-approved.sh` is the only path from email queue to outbox, and it aborts unless everything checks out: a verification baseline must exist; `scripts/verify-sites.py` must confirm no prospect site drifted since drafting (every email asserts something observed on the site — if the site changed, the claim is false); the compliance footer placeholder must be filled; suppressed addresses are skipped and the suppression list is pushed to the platform's account-level blocklist first (`scripts/sync-blocklist.py`) so opt-outs are enforced even for sequences already in flight.

**Human approval gate.** Scheduled jobs draft; they never send. The email pipeline writes a queue and texts the owner; the job pipeline tailors applications and stops. Sending and submitting are manual, every time.

**Self-audit loop.** Sunday's `weekly-retro` job runs an auditor persona (Vera) over the repo, the stamps, the logs, and the session transcripts — including the CEO session's own claims. Its findings rewrite the status board's focus for the week. Several fixes in these scripts started as retro findings, including the discovery that four consecutive "successful" morning runs had died on an expired token and nobody noticed.

**Cheap local scoring.** `scripts/job-intern.py` polls free job-board APIs every 2 hours and has a local 8B model (Ollama) score each posting against a candidate profile — zero marginal cost per run, so it can be always-on.

## Repo layout

```
scripts/    the runner, sync, gates, and scrapers (bash + stdlib-only python)
prompts/    one markdown prompt per scheduled job, fed to `claude -p`
launchd/    plist patterns: interval-fired and calendar-fired examples
agents/     persona files for the "staff" — spawned as subagents for
            audits, revenue takes, finding tools, accountability
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
