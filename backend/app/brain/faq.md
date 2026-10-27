---
topic: "DILG Laguna PDMU Operations Workspace Frequently Asked Questions and Domain Clarifications"
category: "faq"
roles:
  - "admin"
  - "staff"
  - "field_officer"
  - "system_admin"
source_type:
  - "operations_manual"
  - "staff_interview"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
  - "backend/app/services/ai_tool_registry.py"
authority: "Level 1 through Level 3 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "faq"
  - "dms"
  - "subaybayan"
  - "lgu login"
  - "approval permissions"
  - "returned_for_revision"
  - "nnc3"
  - "annex d"
  - "auto-generation"
---

# DILG Laguna PDMU Operations Workspace Frequently Asked Questions (FAQ)

### 1. Is DILG Laguna PDMU Operations Workspace a Document Management System (DMS)?
* **Official Procedure & Operational Practice:** No. DILG Laguna utilizes an official internal intranet DMS for incoming and outgoing document barcoding, receiving, and routing across the provincial office.
* **Current DILG Laguna PDMU Operations Workspace Implementation:** DILG Laguna PDMU Operations Workspace is an internal technical evaluation, documentary compliance tracking, deficiency recording, and procedural deadline management tool. It does not replace the DILG intranet DMS.

---

### 2. Is DILG Laguna PDMU Operations Workspace a replacement for SubayBAYAN?
* **Official Procedure:** No. SubayBAYAN is the mandatory national DILG system for monthly public status updates (financial and physical accomplishment percentages, SWA, geotagged photos) due on the 25th of each month under DILG MC 2024-134.
* **Current DILG Laguna PDMU Operations Workspace Implementation:** DILG Laguna PDMU Operations Workspace operates upstream at the provincial level. It manages the granular technical evaluation of 20+ engineering and procurement documents (Annex B/C) required before civil works begin, tracks revision cycles, and prepares approved packages for regional handoff.

---

### 3. Can Local Government Units (LGUs) log directly into DILG Laguna PDMU Operations Workspace?
* **Current DILG Laguna PDMU Operations Workspace Implementation:** No. DILG Laguna PDMU Operations Workspace does not provide external accounts or login portals for LGUs. DILG Laguna PDMU Operations Workspace is strictly an internal application for DILG Laguna PDMU engineers, administrative staff, provincial admins, and field officers.
* **Operational Practice (PDMU Interviews):** LGUs submit project documents to the Provincial Office via DMS, email, or physical transmittal. PDMU staff encode and evaluate the documents within DILG Laguna PDMU Operations Workspace.

---

### 4. Can Field Officers approve documentary requirements?
* **Official Procedure & DILG Laguna PDMU Operations Workspace Implementation:** No. Field Officers perform on-site project monitoring, verify physical progress, and complete field checklists. Approval of documentary requirements (e.g., POW, DED, PhilGEPS postings) is restricted to PDMU Technical Staff and Provincial Admins.

---

### 5. What does `returned_for_revision` mean? Does it mean the document is `non_compliant`?
* **Official Procedure & DILG Laguna PDMU Operations Workspace Implementation:** No. `returned_for_revision` is a **workflow status**, not a compliance status. It indicates that the reviewing engineer found deficiencies in the submitted document and sent it back with comments for correction.
* **Compliance Rule:** The requirement's **compliance status** remains `under_review` while the LGU addresses findings. It only becomes `non_compliant` if statutory escalation timelines expire without the LGU curing the deficiencies.

---

### 6. Who signs and issues Notice of Non-Compliance No. 3 (NNC3)?
* **Official Procedure (PDMU Operations Manual, pp. 18, 21, 51):** NNC3 is officially issued and signed by the **Regional Director (RD)** of DILG Region IV-A, NOT the Provincial Director.
* **Notice Sequence:**
  1. *Reminder / Findings Letter:* PDMU / Provincial Office
  2. *NNC1 (Annex M):* Provincial Director (PD)
  3. *NNC2 (Annex N):* Provincial Director (PD)
  4. *NNC3 (Annex O):* **Regional Director (RD)**
  5. *Escalation:* Bantay Korapsyon legal concurrence and OUSLG endorsement.

---

### 7. Does official DILG Annex D exist in the repository?
* **Source Audit Finding:** **NOT FOUND / NOT VERIFIED**. In the local repository files (`others/reference_data/`), Annexes A, B, C, E, F, G, H, I, J, K, L, and Appendices 1–19 exist. Annex D is not present in the files. The assistant must state that Annex D cannot be verified from local sources.

---

### 8. Are Annexes M, N, and O official DILG letter designations?
* **Reconciliation:** No. In the official DILG Operations Manual, these documents are officially titled **Notice of Non-Compliance No. 1, 2, and 3**. The labels "Annex M", "Annex N", and "Annex O" are internal DILG Laguna PDMU Operations Workspace system template conventions used in seed data and generation services.

---

### 9. Where do I review project requirements in DILG Laguna PDMU Operations Workspace?
* **Current DILG Laguna PDMU Operations Workspace Implementation:**
  * To review requirements for a specific project: Navigate to **Projects** (`/dashboard/projects`), select the project to open the **Project Detail Page** (`/dashboard/projects/:id`), and open the **Requirements** tab.
  * For batch intake triage: Navigate to **Intake Triage** (`/dashboard/intake`).

---

### 10. Where do I track overdue compliance deadlines?
* **Current DILG Laguna PDMU Operations Workspace Implementation:** Navigate to the **Compliance Deadline Tracker (SLA Tracker)** at `/dashboard/sla`. Overdue items are also highlighted on the **Operational Dashboard** (`/dashboard`).
