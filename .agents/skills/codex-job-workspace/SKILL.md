---
name: codex-job-workspace
description: Run the configured job-search workspace in Codex using connected Google Docs, Drive and an existing Google Sheets tracker. Use for finding or approving jobs, tailoring applications, interviews, outcomes, email sync, reports, or maintaining this workspace.
---
# Codex job workspace
Read the workspace-root AGENTS.md and external private/config.json first. When invoked inside the framework checkout, look in its parent. Missing config: follow docs/CODEX.md setup; never personalize tracked templates.
Read docs/codex-workflows.md for the requested operation, and its referenced upstream methodology only as needed.
This adapter overrides upstream storage/runtime instructions: candidate facts come from configured Google Docs and external snapshots; application truth comes from the connected Sheet. Do not execute upstream CSV mutation helpers, populate CLAUDE.md, or create job_search_tracker.csv in Codex mode.
Use connected tools for native Google files. Local .gdoc/.gsheet files are shortcuts. Authenticated connector tools are not available to shell scripts: orchestrate them in Codex, passing their read results as external JSON snapshots to tools/codex_workspace.py.
Use the configured Python/Bun/TeX executable paths. All artifacts, snapshots, build output and logs go to configured external paths, never into the public checkout.
Entry approval adds Not Applied rows and drafts both documents; it never authorizes sending or submitting. A proposed row file is not proof of consent. Check actual user messages, fresh live rows and validation before executing any proposal.
Use a separate reviewer for application drafts, with cleaned posting text and source-backed claims. The reviewer does not write to external services.
