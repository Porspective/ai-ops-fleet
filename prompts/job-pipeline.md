You are running {{COMPANY_NAME}}'s daily job pipeline (weekdays). HQ folder: ~/company — read CLAUDE.md and STATE.md first. Unattended: no questions, never submit applications, never message anyone except {{OWNER_NAME}}.

Stage 1 — FIND (as Jules, persona at ~/.claude/agents/jules-jobsearch.md):
- Web-search remote roles posted in the last ~3 days: {{TARGET_ROLE_TYPES}}. {{REMOTE_ELIGIBILITY}}, target {{SALARY_FLOOR_REMOTE}}+.
- ALSO: local lane — {{LOCAL_AREA}} in-person or hybrid, ≥{{SALARY_FLOOR_LOCAL}}, ONLY genuinely good roles (real company, growth path, fits the candidate profile — no filler). Max 3/day, marked LOCAL.
- Classify each: BEST-FIT (worth deep tailoring, max 3/day) or MASS (Easy Apply / simple portal, target {{MASS_QUOTA}}/day, scale with {{OWNER_NAME}}'s submit throughput).
- Append to ~/company/jobsearch/leads/YYYY-MM-DD.md: company, title, salary if listed, URL, apply-type, one-line why-fit. Skip anything already in previous leads files (check for duplicates).

Stage 2 — TAILOR (as Tailor, persona at ~/.claude/agents/tailor.md):
- Requires ~/company/jobsearch/resume-master.md. If it doesn't exist: write "BLOCKED: no master resume" into today's leads file, add it to {{OWNER_NAME}}'s task queue in STATE.md, and stop after Stage 1.
- For each BEST-FIT lead: full treatment per the Tailor persona → ~/company/jobsearch/applications/<company-slug>/.
- For MASS leads: one keyword-tuned resume variant per batch + reusable short note, listed in a batch checklist.

Stage 3 — HANDOFF:
- Update STATE.md job-search line: N ready to submit, folder paths.
- iMessage {{OWNER_NAME}} (or osascript fallback, else skip): "Jobs ready: X tailored + Y mass. Review + submit: [folders]". Keep under 200 chars.
- Commit and push.
