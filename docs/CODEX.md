# Codex workspace
This is an agent-orchestrated application workflow, not an unattended service. Open the external workspace root in Codex with the Google Drive and Gmail plugins connected. No Anthropic dependency is used by this adapter.

## Setup
Keep the checkout in a child directory of a private workspace. Copy config/codex.example.json to private/config.json outside the checkout; fill in absolute paths and source IDs. Install Python 3.10+, Bun, LuaLaTeX, XeLaTeX, pypdf and PyMuPDF. Configure MiKTeX automatic missing-package installation or preinstall template packages.
Place a project skill pointer under the workspace root .agents/skills that loads this checkout's codex-job-workspace skill. Retain personal preferences in the root AGENTS.md.

## Commands
Run from the checkout, using the external Python environment:
```
python tools/codex_workspace.py --config ../private/config.json preflight
python tools/codex_workspace.py --config ../private/config.json report --snapshot ../private/state/tracker.json --output ../reports/report-YYYYMMDD-HHMM.html
python tools/codex_workspace.py --config ../private/config.json propose --snapshot ../private/state/tracker.json --jobs ../private/state/shortlist.json --approved job-1 --approval "User message approving job-1" --output ../private/state/proposal-unique.json
```
Helpers never write to Google. Read-only snapshots are disposable and refreshed by the agent. Every output path must be outside this checkout; existing output files are never overwritten. Local preflight does not establish connector authentication or cloud sync.

## Everyday requests
- Find new jobs and rank them.
- Approve entries 1 and 3; add them and prepare their applications.
- Prepare me for the technical interview at COMPANY.
- I submitted ROLE at COMPANY today.
- Check Gmail for application updates; show proposed changes.
- Generate a report / expand my profile / build a learning plan.
- Add a template / add a portal / preview upstream changes.

See codex-workflows.md for all execution contracts. Keep only reusable code, synthetic tests and example config in public Git. Review staged diffs before publishing. Do not run two writers against the same synced checkout/state simultaneously.
