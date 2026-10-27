---
topic: "Field Officer Role and Boundaries"
category: "role"
roles:
  - "field_officer"
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
  - "field_officer"
  - "inspector"
  - "roles"
  - "permissions"
  - "site visits"
  - "geotagged monitoring"
  - "field dashboard"
---

# Field Officer (`field_officer`)

## 1. Role Scope & Responsibility
The **Field Officer** operates at the municipal and field level. They are responsible for conducting on-site physical inspections of infrastructure projects, taking geotagged photos, verifying actual civil progress against reported SWA (Statement of Work Accomplished), and alerting PDMU engineers of on-site issues.

---

## 2. Permitted Capabilities (What Field Officer Can Do)
* **Field Officer Dashboard:** Access the dedicated field monitoring dashboard (`/dashboard/field` and root `/dashboard`).
* **Field Inspection Logging:** Record site visit findings, progress observations, and upload geotagged photographic evidence.
* **Project Directory View:** Browse assigned projects and general project status (`/dashboard/projects`, `/dashboard/projects/:id`).
* **Monitoring & Guidelines:** View monitoring records and reference library documents (`/dashboard/monitoring`, `/dashboard/guidelines`).

---

## 3. Role Restrictions (What Field Officer Cannot Do)
* Cannot approve or return documentary requirements (restricted to Staff and Admin).
* Cannot access administrative reports or checker accuracy analytics (`/dashboard/reports` is restricted to `admin` and `staff`).
* Cannot access regional handoff workflows (`/dashboard/handoff` is restricted to `admin` and `staff`).
* Cannot manage escalations or generate non-compliance notices (`/dashboard/escalation` is restricted to `admin` and `staff`).
* Cannot manage user accounts, clusters, or system settings (`/dashboard/users`, `/dashboard/clusters`, `/dashboard/settings`).

---

## 4. Primary Navigation Routes
* Field Officer Dashboard: `/dashboard/field`
* Projects Directory: `/dashboard/projects`
* Monitoring: `/dashboard/monitoring`
* Reference Library / Guidelines: `/dashboard/guidelines`
