---
topic: "Provincial Admin Navigation and Route Directory"
category: "navigation"
roles:
  - "admin"
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
  - "admin"
  - "pages"
  - "clusters"
  - "escalation"
  - "sla tracker"
  - "handoff"
---

# Provincial Admin Navigation Directory

The following routes are available to users logged in with the `admin` (Provincial Administrator) role:

| Route Path | Page Title / Purpose | Core Capabilities |
| :--- | :--- | :--- |
| `/dashboard` | Operational Dashboard | High-level portfolio metrics, overdue deadlines, and recent submissions. |
| `/dashboard/projects` | Project List Page | Comprehensive listing of all municipal infrastructure projects. |
| `/dashboard/projects/:id` | Project Detail Page | Project overview, timeline, documents, requirements, and compliance actions. |
| `/dashboard/intake` | Intake Triage | Triage incoming submissions, review documents, and assign workflows. |
| `/dashboard/monitoring` | Implementation Monitoring | Track ongoing project implementation milestones and field progress. |
| `/dashboard/sla` | Compliance Deadline Tracker | Monitor working-day deadlines, view overdue documents, and inspect escalations. |
| `/dashboard/escalation` | Escalation Management | Authorize and sign off on formal deficiency and non-compliance notices (NNC1, NNC2). |
| `/dashboard/handoff` | Regional Handoff | Inspect and transmit fully validated project packages to the Regional Office repository. |
| `/dashboard/reports` | Reports & Analytics | Macro-level provincial compliance analytics and program statistics. |
| `/dashboard/reports/checker-accuracy` | Checker Accuracy Report | Evaluation accuracy metrics and review audit statistics. |
| `/dashboard/clusters` | Clusters Management | Configure LGU municipal clusters and administrative groupings *(Admin only)*. |
| `/dashboard/programs` | Programs List | Browse grant programs (FALGU, SGLG-IF, SBDP) and cycles. |
| `/dashboard/programs/:id` | Program Detail | Deep-dive into specific program allocations and participating LGUs. |
| `/dashboard/programs/:programId/cycles/:cycleId/import` | Workbook Import | Import official program cycles and allocation workbooks *(Admin only)*. |
| `/dashboard/programs/:programId/cycles/:cycleId/workbook` | Workbook Workspace | Interactive review of program workbook data. |
| `/dashboard/lgus` | LGUs Directory | Overview of all Laguna LGUs, project counts, and compliance statuses. |
| `/dashboard/lgus/:id` | LGU Detail Page | Municipality-specific portfolio, contacts, and active projects. |
| `/dashboard/completion` | Project Completion & Vault | Closeout documentation, final completion certificates, and archives. |
| `/dashboard/archive` | Archive Communications | Historical correspondence, transmittal records, and legacy logs. |
| `/dashboard/guidelines` | Reference Library | Official DILG guidelines, operations manuals, and standard templates. |
| `/dashboard/settings` | Operational Settings | Provincial office settings and threshold configurations *(Admin only)*. |
| `/dashboard/users` | User Management | Create, edit, and assign roles for PDMU personnel and field officers. |
| `/dashboard/audit` | Audit Log Page | Review system-wide audit trail and security events. |
| `/dashboard/ai` | Smart Assistant Full Page | Dedicated AI Assistant conversational interface. |
| `/dashboard/account` | Account Settings | Personal profile and credential management. |
| `/dashboard/notifications` | Notifications Center | System notifications and deadline alerts. |
