---
topic: "Field Officer Navigation and Route Directory"
category: "navigation"
roles:
  - "field_officer"
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
  - "field_officer"
  - "inspector"
  - "field dashboard"
  - "monitoring"
---

# Field Officer Navigation Directory

The following routes are available to users logged in with the `field_officer` role:

| Route Path | Page Title / Purpose | Core Capabilities |
| :--- | :--- | :--- |
| `/dashboard` (or `/dashboard/field`) | Field Officer Dashboard | Tailored mobile-friendly overview of assigned field projects, inspection schedules, and recent logs. |
| `/dashboard/projects` | Projects Directory | Browse assigned projects within the field jurisdiction. |
| `/dashboard/projects/:id` | Project Detail Page | View project specifications, location details, and physical status. |
| `/dashboard/monitoring` | Implementation Monitoring | Review field implementation milestones and monitoring logs. |
| `/dashboard/completion` | Project Completion & Vault | View completed project records. |
| `/dashboard/archive` | Archive Communications | Browse archived project communications. |
| `/dashboard/guidelines` | Reference Library | Access official monitoring manuals, field checklists, and guides. |
| `/dashboard/ai` | Smart Assistant Full Page | Ask domain questions, verify guidelines, and look up project facts. |
| `/dashboard/account` | Account Settings | Personal profile and credential updates. |
| `/dashboard/notifications` | Notifications Center | System alerts and assignment notifications. |

*Restricted routes:* Field Officers cannot access `/dashboard/intake`, `/dashboard/reports`, `/dashboard/handoff`, `/dashboard/escalation`, `/dashboard/users`, `/dashboard/clusters`, `/dashboard/settings`, or `/dashboard/system-admin`.
