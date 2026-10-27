---
topic: "PDMU Staff Navigation and Route Directory"
category: "navigation"
roles:
  - "staff"
source_type:
  - "system_implementation"
sources:
  - "frontend/src/App.jsx"
  - "frontend/src/config/routes.js"
authority: "Level 3 - Current System Implementation"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "navigation"
  - "routes"
  - "staff"
  - "engineer"
  - "intake"
  - "projects"
  - "sla tracker"
  - "handoff"
---

# PDMU Technical Staff Navigation Directory

The following routes are available to users logged in with the `staff` role:

| Route Path | Page Title / Purpose | Core Capabilities |
| :--- | :--- | :--- |
| `/dashboard` | Operational Dashboard | Overview of pending reviews, upcoming deadlines, and recent submissions. |
| `/dashboard/intake` | Intake Triage | Triage incoming documents from LGUs, encode metadata, and initiate reviews. |
| `/dashboard/projects` | Project List Page | Browse all projects, filter by status, LGU, or program. |
| `/dashboard/projects/:id` | Project Detail Page | Detailed requirement review, checklist evaluation, and returning documents for revision. |
| `/dashboard/monitoring` | Implementation Monitoring | Track ongoing project implementation milestones and field progress. |
| `/dashboard/sla` | Compliance Deadline Tracker | Monitor working-day deadlines and identify approaching or overdue requirements. |
| `/dashboard/escalation` | Escalation Page | View escalation status and draft deficiency notices. |
| `/dashboard/handoff` | Regional Handoff | Prepare and assemble validated document sets for regional transmittal. |
| `/dashboard/reports` | Reports & Analytics | View operational reports and evaluation metrics. |
| `/dashboard/reports/checker-accuracy` | Checker Accuracy Report | View evaluation accuracy statistics and consistency logs. |
| `/dashboard/programs` | Programs List | Browse grant programs (FALGU, SGLG-IF, SBDP) and cycles. |
| `/dashboard/programs/:id` | Program Detail | Deep-dive into program allocations and participating LGUs. |
| `/dashboard/programs/:programId/cycles/:cycleId/workbook` | Workbook Workspace | View and analyze program workbook cycles. |
| `/dashboard/lgus` | LGUs Directory | Overview of all Laguna LGUs and their project portfolios. |
| `/dashboard/lgus/:id` | LGU Detail Page | View municipality-specific portfolio and compliance records. |
| `/dashboard/completion` | Project Completion & Vault | Access closeout documents and final project submissions. |
| `/dashboard/archive` | Archive Communications | Browse historical communications and document archives. |
| `/dashboard/guidelines` | Reference Library | Access official DILG manuals, guidelines, and forms. |
| `/dashboard/ai` | Smart Assistant Full Page | Dedicated conversational interface for data lookups and guidance. |
| `/dashboard/account` | Account Settings | Personal profile and password management. |
| `/dashboard/notifications` | Notifications Center | System notifications and deadline alerts. |

*Restricted routes:* Staff cannot access `/dashboard/clusters`, `/dashboard/settings`, `/dashboard/users`, `/dashboard/audit`, or `/dashboard/system-admin`.
