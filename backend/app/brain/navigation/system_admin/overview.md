---
topic: "System Administrator Navigation and Route Directory"
category: "navigation"
roles:
  - "system_admin"
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
  - "system_admin"
  - "users"
  - "audit"
  - "technical settings"
---

# System Administrator Navigation Directory

The following routes are available to users logged in with the `system_admin` role:

| Route Path | Page Title / Purpose | Core Capabilities |
| :--- | :--- | :--- |
| `/dashboard/system-admin` | System Admin Overview | Server health, background worker status, active sessions, and environment status. |
| `/dashboard/system-admin/technical-settings` | Technical Settings | System parameters, cache controls, email dispatch, and API configurations. |
| `/dashboard/users` | User Management | Create, edit, activate/deactivate, and manage permissions for all users. |
| `/dashboard/users/new` | Create User | Provision a new user account and assign roles (`admin`, `staff`, `field_officer`, `system_admin`). |
| `/dashboard/users/:id` | User Detail | Edit account details, reset credentials, and review user activity history. |
| `/dashboard/audit` | Audit Log Page | Inspect immutable audit trails of all system transactions, mutations, and authentication events. |
| `/dashboard/account` | Account Settings | Personal administrator credentials and security options. |
| `/dashboard/notifications` | Notifications Center | System-level maintenance and security alerts. |

*Restricted routes:* System Administrators do not participate in operational engineering review, and therefore do not have operational access to project requirement approvals or provincial notice issuance.
