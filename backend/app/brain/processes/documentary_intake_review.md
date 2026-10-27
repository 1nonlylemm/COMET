---
topic: "Documentary Intake and Technical Review Process"
category: "process"
roles:
  - "admin"
  - "staff"
source_type:
  - "operations_manual"
  - "staff_interview"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
  - "others/reference_data/NEW UPDATE DATA/LM Transcript.txt"
  - "backend/app/services/project_requirement_service.py"
  - "docs/research/PDMU_DOCUMENT_REVIEW_RETURN_PROCESS_ANALYSIS.md"
authority: "Level 1, Level 2, and Level 3 Reconciled"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "intake"
  - "document review"
  - "review requirements"
  - "requirements review"
  - "evaluation"
  - "pow"
  - "ded"
  - "dupa"
  - "annex b"
  - "annex c"
  - "filtering"
  - "dms"
---

# Documentary Intake and Technical Review Process

This guide details the end-to-end documentary intake, engineering scrutiny, and provincial quality filtering workflow executed by the Provincial Development and Management Unit (PDMU).

---

## 1. Official Procedure (PDMU Operations Manual & National Issuances)

* **Mandatory Checklist (Annex B):** Prior to project procurement and throughout implementation, the LGU must submit statutory and technical engineering documents codified in **[Annex B](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_b_documentary_reqs.md)**:
  * **Part I (Fund Release):** Governs initial project proposals submitted to DBM via the DRSL portal (FY 2023) or standard transmittals (FALGU, DRRAP, AC, GEF).
  * **Part II (Implementation - Table 7):** Codifies 33+ discrete requirements for infrastructure, 8 for motor vehicles, and specific non-infra monitoring templates (MT1–MT4A). Core documents include:
    * Notice of Authority to Debit Account Issued (NADAI) & Trust Fund Transfer Proof.
    * Program of Works (POW) and Detailed Unit Price Analysis (DUPA).
    * Detailed Engineering Design (DED) blueprints, structural calculations, and technical specifications.
    * Approved Budget for the Contract (ABC) approved by the Local Chief Executive (Mayor).
    * Statutory Clearances: Environmental Compliance (ECC/CNC), Right-of-Way (ROW deed/waiver), Water Permit, and Tree Cutting Permit (conditional).
    * Bidding & Contract Documents: PhilGEPS posting, BAC resolutions, Notice of Award (NOA), Contract, and Notice to Proceed (NTP).
* **Technical Evaluation Checklist (Annex C):** PDMU civil engineers review each submission against the 9 component tables and 43-item evaluation matrix of **[Annex C](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_c_monitoring_check.md)**, evaluating:
  1. Technical completeness, licensing, and mathematical consistency.
  2. Adherence of material unit prices to DPWH Construction Materials Price Data (CMPD) and regional price indices.
  3. Proper executive endorsements, Sanggunian resolutions, and municipal engineer certifications.
* **Prescribed Review Cadence:** The PDMU Operations Manual Final (p. 17 Step 2 Seq. 4) prescribes an internal technical evaluation window of **5 working days upon receipt of Annex C documentation**.
* **Deficiency Notification (Annex E):** When omissions, non-conforming unit costs, or engineering defects are identified, evaluators log findings using the structured 4-column matrix of **[Annex E](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_e_notice_deficiencies.md)**.

---

## 2. Operational Practice (PDMU Interviews & Field Realities)

* **The Provincial Quality Filtering Mandate:** PDMU serves as the primary technical filter between municipal LGUs and the DILG Regional Office. As explained by PDMU staff:
  > *"Documents from LGUs do not go directly to the Region. The Provincial Office filters everything. We check if the DED and POW match the approved allocation. If okay, upload namin sa drive ni regional office."* (Video Runthrough Transcript line 22).
* **Submission Intake Channels (DMS Intranet):** LGUs submit electronic transmittals primarily through the DILG intranet Document Management System (DMS), which assigns a barcoded tracking number.
* **Hierarchical Routing:** DMS transmittals follow strict channels:
  $$\text{LGU} \longrightarrow \text{Field Officer (C/MLGOO)} \longrightarrow \text{Cluster Head} \longrightarrow \text{Provincial PDMU} \longrightarrow \text{Regional Office}$$
  LGUs cannot bypass the provincial unit to submit directly to regional directors.
* **Technical Scrutiny in Action:** PDMU engineers verify that the unit rates for cement, rebar, aggregates, and equipment rental align with provincial DPWH benchmarks. Unjustified price escalations result in an immediate return for revision.

---

## 3. Current System Implementation in {app_name}

* **Intake Triage Page (`/dashboard/intake`):** Staff utilize this console to triage incoming submissions, capture DMS barcode numbers, record transmittal receipt dates, and assign documents to active project profiles.
* **Project Requirements Review Console (`/dashboard/projects/:id` - Requirements Tab):** Engineers inspect individual document records. When evaluating a submission, the review progression follows canonical stages:
  * **Intake & Verification:** When a document is transmitted, it enters `workflow_status = "submitted"` with `compliance_status = "under_review"`. As technical scrutiny proceeds against Annex C checklists and DPWH price standards, it transitions to `workflow_status = "under_verification"`.
  * **Staff Recommendation:** Technical evaluators / engineers verify engineering parameters and completeness, transitioning `workflow_status` to `staff_approved`.
  * **Provincial Endorsement & Full Approval:** Upon final review and administrative sign-off, `workflow_status` transitions to `approved` and `compliance_status` becomes `compliant`.
  * **Return for Revision:** If omissions, defects, or pricing discrepancies exist, the reviewer logs canonical deficiency remarks and sets `workflow_status = "returned_for_revision"`, while `compliance_status` **strictly remains `under_review`** (never `non_compliant`).
  * **Resubmission:** Corrected uploads transition `workflow_status` to `resubmitted` with `compliance_status` remaining `under_review`, queuing the corrected files for reviewer re-evaluation.
* **Audit Trail & Provenance:** Every review action automatically captures the evaluator's user ID, timestamp, and review remarks, ensuring compliance with state auditing standards.
