# devin-workflows

Event-driven vulnerability remediation for [Apache Superset](https://github.com/DavidBanda314/superset), with **Devin as the core primitive**: Devin detects the issues, Devin fixes them. The code here is thin orchestration around the [Devin API v3](https://docs.devin.ai/api-reference/overview).

## Architecture

```
 Trigger A (cron / manual)                Trigger B (GitHub issue event)
┌──────────────────────────┐            ┌──────────────────────────────┐
│ audit.yml /              │            │ devin-dispatch.yml           │
│ docker compose run audit │            │ (in the superset fork)       │
└────────────┬─────────────┘            │ on: issues [opened, labeled] │
             │                          └──────────────┬───────────────┘
             ▼                                         ▼
   scan_dispatch.py                              dispatch.py
   POST /v3/.../sessions                         POST /v3/.../sessions
             │                                         │
             ▼                                         ▼
 ╔═══════════════════════╗   files issues   ╔═══════════════════════╗
 ║ Devin AUDIT session   ║ ───────────────► ║ Devin FIX session     ║
 ║ scans fork, triages,  ║  labeled         ║ (one per issue)       ║
 ║ files GitHub Issues   ║  `devin-fix`     ║ validates → fixes →   ║
 ╚═══════════════════════╝  (= the event)   ║ opens PR "Fixes #n"   ║
                                            ╚═══════════╦═══════════╝
                                                        ▼
                            report.py  ◄──  PRs close issues on merge
                            (funnel: detected → issue → session → PR)
```

- **Detection**: a scheduled Devin *audit session* scans the fork (running pip-audit/ruff itself, applying judgment to filter false positives) and files one GitHub Issue per confirmed finding, labeled `devin-fix`.
- **Event**: each labeled issue fires the fork's `devin-dispatch.yml` workflow — one independent Devin *fix session* per issue, in parallel.
- **Remediation**: the fix session validates the finding, applies a minimal fix, opens a PR with `Fixes #n`, and comments the session URL on the issue.
- **Observability**: `report.py` joins Devin API sessions with GitHub issues/PRs into a funnel report with success rate, latency, and ACU cost per fix.

## Quick start (Docker)

```bash
cp .env.example .env   # fill in DEVIN_SERVICE_API_KEY, DEVIN_ORG_ID

# Trigger A: start a Devin audit session (detects + files issues)
docker compose run audit

# Trigger B happens automatically via GitHub Actions when issues get the
# `devin-fix` label. To simulate it locally for one issue:
docker compose run -e ISSUE_NUMBER=123 -e ISSUE_TITLE="[security] ..." \
  -e ISSUE_BODY="$(gh issue view 123 -R DavidBanda314/superset --json body -q .body)" dispatch

# Observability: the remediation funnel report (also writes REPORT.md)
docker compose run report
```

## GitHub Actions setup

Secrets required (`Settings → Secrets and variables → Actions`):

| Secret | Where | Purpose |
|---|---|---|
| `DEVIN_SERVICE_API_KEY` | this repo **and** the fork | v3 API auth (service user) |
| `DEVIN_ORG_ID` | this repo **and** the fork | v3 API org scoping |

Workflows:

| Workflow | Repo | Trigger | Runs |
|---|---|---|---|
| `audit.yml` | this repo | daily cron + manual | `scan_dispatch.py` — Devin audit session |
| `devin-dispatch.yml` | superset fork ([template](fork-workflows/devin-dispatch.yml)) | `issues: [opened, labeled]` | `dispatch.py` — Devin fix session per issue |
| `report.yml` | this repo | daily cron + manual | `report.py` — funnel report as job summary + artifact |

## Repository structure

```
├── Dockerfile
├── docker-compose.yml           # services: audit, dispatch, report
├── .env.example
├── scripts/
│   ├── devin_client.py          # Devin API v3 client (create/get/list sessions)
│   ├── scan_dispatch.py         # Trigger A → Devin audit session
│   ├── dispatch.py              # Trigger B → Devin fix session per issue
│   └── report.py                # Observability funnel report
├── .github/workflows/
│   ├── audit.yml                # scheduled audit trigger
│   └── report.yml               # scheduled report
└── fork-workflows/
    └── devin-dispatch.yml       # issue-event trigger (copy into the fork)
```

## Why Devin here?

A scripted pipeline can *detect* a pinned CVE, but it cannot judge whether a finding is a false positive, choose the minimal safe fix, verify it, and open a reviewable PR that explains the vulnerability. Each `devin-fix` issue becomes an autonomous engineer working in parallel — the scripts above are only event plumbing.
