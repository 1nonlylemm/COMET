---
topic: "Provincial Administrator Role and Boundaries"
category: "role"
roles:
  - "admin"
source_type:
  - "system_implementation"
  - "operations_manual"
sources:
  - "frontend/src/App.jsx"
  - "backend/app/services/ai_tool_registry.py"
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
authority: "Level 1 and Level 3 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "admin"
  - "provincial_admin"
  - "roles"
  - "permissions"
  - "notice approval"
  - "clusters"
  - "executive oversight"
---

# Provincial Administrator (`admin`)

## 1. Role Scope & Responsibility
The **Provincial Administrator** represents the leadership and executive authority of the DILG Laguna Provincial Office and PDMU. The role oversees project portfolios across all LGUs, authorizes statutory escalations, configures LGU clusters, and reviews macro analytics.

---

## 2. Permitted Capabilities (What Provincial Admin Can Do)
* **Full Operational Oversight:** View all LGU projects, monitoring feeds, and compliance trackers (`/dashboard/projects`, `/dashboard/monitoring`, `/dashboard/sla`).
* **Requirement Evaluation:** Review, approve, or return project documentary requirements (`/dashboard/projects/:id`).
* **Statutory Escalation & Notices:** Authorize, generate, and sign off on formal deficiency and non-compliance notices (NNC1, NNC2) (`/dashboard/escalation`).
* **LGU Clustering & Operational Settings:** Configure LGU cluster assignments and operational settings (`/dashboard/clusters`, `/dashboard/settings`).
* **Program Cycle Imports:** Import official program workbooks and cycle allocations (`/dashboard/programs/:programId/cycles/:cycleId/import`).
* **Reports & Handoff:** Access executive reports, checker accuracy analytics, and regional handoff consoles (`/dashboard/reports`, `/dashboard/handoff`).
* **User Governance:** Create and manage staff and field officer accounts alongside System Admin (`/dashboard/users`).

---

## 3. Role Restrictions (What Provincial Admin Cannot Do)
* Cannot issue Notice of Non-Compliance No. 3 (NNC3) under official policy (NNC3 requires the signature of the **Regional Director**).
* Cannot modify low-level infrastructure and system-level daemon parameters (restricted to `system_admin`).

---

## 4. Primary Navigation Routes
* Operational Dashboard: `/dashboard`
* Escalation Management: `/dashboard/escalation`
* Cluster Configuration: `/dashboard/clusters`
* Operational Settings: `/dashboard/settings`
* Regional Handoff: `/dashboard/handoff`
* Reports & Analytics: `/dashboard/reports`
