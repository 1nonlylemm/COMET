---
topic: "System Administrator Role and Boundaries"
category: "role"
roles:
  - "system_admin"
source_type:
  - "system_implementation"
sources:
  - "frontend/src/App.jsx"
  - "backend/app/models/user.py"
  - "backend/app/services/ai_tool_registry.py"
authority: "Level 3 - Current System Implementation"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "system_admin"
  - "roles"
  - "permissions"
  - "technical administration"
  - "user management"
  - "audit logs"
---

# System Administrator (`system_admin`)

## 1. Role Scope & Responsibility
The **System Administrator** is responsible for platform infrastructure, technical maintenance, security governance, user account administration, and audit oversight. This role does not participate in day-to-day engineering reviews or provincial notice approvals.

---

## 2. Permitted Capabilities (What System Admin Can Do)
* **User Governance:** Create, view, update, deactivate, and reset passwords for user accounts (`/dashboard/users`, `/dashboard/users/new`, `/dashboard/users/:id`).
* **Audit Oversight:** Review system-wide audit logs and administrative traces (`/dashboard/audit`).
* **Technical Settings:** Manage technical configuration, background jobs, and system parameters (`/dashboard/system-admin`, `/dashboard/system-admin/technical-settings`).
* **Profile Management:** Update personal account security credentials (`/dashboard/account`).

---

## 3. Role Restrictions (What System Admin Cannot Do)
* Cannot approve or return engineering requirements (restricted to PDMU Staff and Provincial Admin).
* Cannot issue or sign formal non-compliance notices (restricted to Provincial Admin / Regional Director).
* Cannot upload field inspection photos as a field officer.
* Default dashboard redirects directly to `/dashboard/system-admin`.

---

## 4. Primary Navigation Routes
* System Overview: `/dashboard/system-admin`
* Technical Settings: `/dashboard/system-admin/technical-settings`
* User Management: `/dashboard/users`
* Audit Logs: `/dashboard/audit`
