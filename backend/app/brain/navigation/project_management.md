---
topic: "Project Management, Navigation, and Record Updates Guide"
category: "navigation"
roles:
  - "admin"
  - "staff"
  - "field_officer"
source_type:
  - "system_implementation"
sources:
  - "frontend/src/features/projects/pages/ProjectListPage.jsx"
  - "frontend/src/features/projects/pages/ProjectDetailPage.jsx"
  - "backend/app/services/project_service.py"
  - "backend/app/services/ai_tool_registry.py"
authority: "Level 3 - Current System Implementation"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "project management"
  - "projects list"
  - "project detail"
  - "edit details"
  - "update project"
  - "budget amount"
  - "project status"
  - "navigation"
  - "confirmation"
---

# Project Management, Navigation, and Record Updates Guide

## 1. Navigating to the Projects Area
Users can access project records in {app_name} through the primary application navigation:

* **Primary Route:** `/dashboard/projects` (Project List Page)
* **Sidebar Item:** Click **Projects** in the main navigation sidebar.
* **Role Availability:** `admin` (Provincial Admin), `staff` (PDMU Technical Staff), and `field_officer` (Field Officers assigned to specific LGUs).
* **Browsing and Filtering Controls:**
  * **Search Input:** Filter projects dynamically by project name or identifier.
  * **Implementation Phase:** Filter by `pre_implementation`, `implementation`, or `completed`.
  * **Overall Status:** Filter by `not_yet_started`, `ongoing`, `completed`, `delayed`, or `suspended`.
  * **Municipality / LGU:** Filter records by assigned local government unit (`lgu_id`).
  * **Grant Program:** Filter by funding program (`program_id`), such as FALGU, SGLG-IF, or SBDP.

---

## 2. Locating and Opening a Project Record
To inspect or update an individual project:
1. Locate the project on `/dashboard/projects` using table pagination or the filter bar.
2. Click any project card or table row to navigate to the **Project Detail Page** at `/dashboard/projects/:id`.
3. The Project Detail Page contains four dedicated tabs:
   * **Overview (`tab=overview`):** Displays summary metrics, project classification, overall status, allocated budget, target schedule, workbook lock indicators, and lifecycle phase transition controls.
   * **Requirements (`tab=requirements`):** Displays documentary compliance checklists (Annex B/C), document upload zones, intake scanner evaluations, and return-for-revision workflows.
   * **History (`tab=history`):** Chronological log of past status changes and milestone updates.
   * **Activity (`tab=activity`):** Audit trail of user and system events associated with the project.

---

## 3. Editing Project Details in the User Interface
* **Role Permissions:** The **Edit Details** button is strictly visible and actionable for users with the `admin` or `staff` role (`isAdmin() || isStaff()`). Users logged in as `field_officer` have read-only view privileges and cannot open the edit modal.
* **Editing Workflow:**
  1. Navigate to `/dashboard/projects/:id`.
  2. In the header action bar, click **Edit Details**.
  3. The modal exposes the following editable fields:
     * **Project Name (`project_name`):** Text title (locked if sourced from an official workbook).
     * **Project Classification (`project_kind`):** Infrastructure (Civil Works) or non-infrastructure category.
     * **Status (`overall_status`):** Lifecycle status (`not_yet_started`, `ongoing`, `completed`, `delayed`, `suspended`; locked if sourced from workbook).
     * **Budget Amount (`budget_amount`):** Numeric grant allocation amount (locked if sourced from workbook).
     * **Target Start Date (`target_start_date`):** Target implementation start date picker.
     * **Target End Date (`target_end_date`):** Target completion date picker.
     * **Notes (`notes`):** Internal operational remarks.
  4. Click **Save Changes** to submit the update payload to `PATCH /api/projects/:id`.
* **Workbook Lock Protection:** Fields marked with `isWorkbookFieldLocked` (such as `project_name`, `overall_status`, or `budget_amount`) are disabled when a project is bound to an imported official program workbook to maintain audit integrity with regional allocations.
* **Lifecycle Phase Transitions:** Moving a project from `pre_implementation` to `implementation` or `completed` is not performed through Edit Details. It requires clicking **Move to Next Phase**, selecting the target phase, and submitting a documented review reason (`transitionReason`).

---

## 4. AI Assistant Project Capabilities and Role Boundaries
The {assistant_name} provides natural-language project query and update tools:

| Operation Type | Action / Capability | Allowed Roles | Requires Confirmation | Required Information |
| :--- | :--- | :--- | :---: | :--- |
| **Read / Query** | Search projects by keyword | `admin`, `staff`, `field_officer` | No | Search terms or keyword |
| **Read / Query** | Query projects by structured filters | `admin`, `staff`, `field_officer` | No | Filter parameters |
| **Read / Detail** | View project overview | `admin`, `staff`, `field_officer` | No | Project identifier (`project_id`) |
| **Mutation** | Change project budget | `admin`, `staff` | **YES** | Project identifier, new budget amount |
| **Mutation** | Update project operational status | `admin`, `staff` | **YES** | Project identifier, target status |
| **Mutation** | Update milestone schedule | `admin`, `staff` | **YES** | Project identifier, target/actual dates |
| **Mutation** | Edit general project details | `admin`, `staff` | **YES** | Project identifier, updated fields |
| **Mutation** | Create new project | `admin`, `staff` | **YES** | LGU, program, project name, fiscal year |
| **Mutation** | Change assigned LGU | `admin`, `staff` | **YES** | Project identifier, target LGU |
| **Mutation** | Change program cycle | `admin`, `staff` | **YES** | Project identifier, target cycle |

* **Strict Deletion Ban:** Project deletion is not supported. There is no project deletion action in {app_name}.
* **Role Boundary Enforcement:** Field Officers (`field_officer`) cannot invoke mutating actions. Any modification attempt by an unauthorized role is rejected with HTTP 403 / `AiToolError`.

---

## 5. AI Assistant Update Preparation and Confirmation Gate
* **Prerequisite Information:** Before preparing a mutation plan, the assistant must have:
  1. A resolved `project_id` (either explicitly given by the user or disambiguated from conversation context).
  2. The specific target field and a validated value (e.g., valid numeric amount for `budget_amount`, or valid status string for `overall_status`).
  If either item is missing, the assistant must request clarification from the user rather than guessing or performing broad searches.
* **Mandatory Confirmation Gate:**
  * All mutating project tools are categorized as `risk_level: high` and `requires_confirmation: True`.
  * The tool call is created in `pending_confirmation` status with a structured preview display (e.g., current value, proposed value, delta).
  * The database record remains unchanged until the user explicitly confirms the operation.

---

## 6. When Users Must Use the UI Instead of the AI Assistant
Users must use the direct web interface rather than AI assistant commands when:
1. **Executing Phase Transitions:** Phase transitions require recording a formal administrative review reason in the "Move to Next Phase" dialog.
2. **Uploading Documentary Evidence:** Physical or scanned PDF/Word documents (POW, DED, PhilGEPS postings, SWA) must be uploaded via the Requirements tab review modal.
3. **Overriding Workbook Locks:** Updating locked project fields requires re-importing the official program workbook in the Program Workbook Workspace.
4. **Field Officer Action:** Field officers cannot update records through the AI assistant or UI forms; field observations must be logged through formal monitoring reports or communicated to PDMU staff.
