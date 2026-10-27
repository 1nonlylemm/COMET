---
topic: "PDMU Technical Staff Role and Boundaries"
category: "role"
roles:
  - "staff"
source_type:
  - "system_implementation"
  - "operations_manual"
  - "staff_interview"
sources:
  - "frontend/src/App.jsx"
  - "backend/app/services/ai_tool_registry.py"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
authority: "Level 1, Level 2, and Level 3 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "staff"
  - "engineer"
  - "technical reviewer"
  - "roles"
  - "permissions"
  - "document intake"
  - "return for revision"
  - "checklist evaluation"
---

# PDMU Technical Staff (`staff`)

## 1. Role Scope & Responsibility
**PDMU Technical Staff** (project evaluation officers, civil engineers, and technical personnel) serve as the primary operational filter for DILG Laguna. They review submitted engineering plans, detailed estimates, bidding documents, and compliance checklists.

---

## 2. Permitted Capabilities (What Staff Can Do)
* **Documentary Intake & Triage:** Process incoming document submissions and encode metadata (`/dashboard/intake`).
* **Technical Evaluation:** Review engineering documents (POW, DED, NTP, PhilGEPS postings) against Annex B and Annex C standards.
* **Return for Revision:** Record specific deficiencies and return documents to LGUs for correction (`workflow_status = "returned_for_revision"`).
* **Document Approval:** Approve compliant documents that satisfy technical standards (`workflow_status = "approved"`).
* **Regional Handoff Packaging:** Assemble verified, compliant document sets for upload to the Regional Office repository (`/dashboard/handoff`).
* **Compliance Tracking:** Monitor working-day deadlines and flag overdue items (`/dashboard/sla`).
* **Reports & Escalation Views:** View reports and escalation dashboards (`/dashboard/reports`, `/dashboard/escalation`).

---

## 3. Role Restrictions (What Staff Cannot Do)
* Cannot modify LGU cluster assignments (`/dashboard/clusters` is restricted to `admin`).
* Cannot modify system-level operational settings (`/dashboard/settings` is restricted to `admin`).
* Cannot manage user accounts or view user governance (`/dashboard/users`, `/dashboard/audit`).
* Cannot officially sign and promulgate formal notices of non-compliance (formal signature requires Provincial Director / Regional Director).

---

## 4. Primary Navigation Routes
* Operational Dashboard: `/dashboard`
* Intake Triage: `/dashboard/intake`
* Project Directory: `/dashboard/projects`
* Implementation Monitoring: `/dashboard/monitoring`
* SLA Tracker: `/dashboard/sla`
* Regional Handoff: `/dashboard/handoff`
