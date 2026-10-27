---
topic: "Document Return for Revision and Deficiency Handling"
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
  - "return_for_revision"
  - "deficiency"
  - "comments"
  - "findings"
  - "notice of deficiencies"
  - "disapproval"
  - "binabalik"
  - "reasons for return"
---

# Document Return for Revision and Deficiency Handling

This guide outlines the official policies, verified operational practices, and {app_name} software procedures governing documentary returns, deficiency logging, and resubmissions.

---

## 1. Official Procedure (PDMU Operations Manual & National Issuances)

* **Deficiency Identification:** When submitted plans or bidding documents fail to satisfy technical standards under **[Annex B](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_b_documentary_reqs.md)** and **[Annex C](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_c_monitoring_check.md)**, PDMU civil engineers prepare a formal **[Notice of Deficiencies (Annex E)](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_e_notice_deficiencies.md)** or Findings Letter.
* **Annex E Structured Matrix:** Annex E organizes review findings into a four-column matrix:
  1. `FINDINGS / OBSERVATIONS`: Classified under Project Management, Quality of Works / Workmanship, Timeliness, or Safety & Health.
  2. `RECOMMENDATIONS AND AGREEMENTS`: Specific engineering remediation directives or lacking documentary attachments.
  3. `TIMELINES`: Prescribed curing days allocated to complete corrections.
  4. `REMARKS`: Technical notes, inspector observations, or re-inspection prerequisites.
* **The 15-Working-Day Administrative Escalation Cadence:** Under internal DILG operational policy (PDMU Operations Manual Final pp. 18, 20–21, 26, 36), the 15-working-day timeline is an **administrative procedural deadline** (not a statutory deadline rooted in an enacted act of Congress):
  * **Defect-Specific Timelines vs. Escalation Windows:** The Annex E form contains an open `TIMELINES` column for case-specific engineering schedules set by inspecting civil engineers. In the Operations Manual (pp. 18, 36), the 15-working-day administrative procedural countdown explicitly attaches to the **Reminder Letter** and subsequent **NNC stages**.
  * **Page 26 Textual Anomaly:** While the summary matrix on page 26 lists *"15 working days upon receipt of the Notice of Deficiency"* in the deadline column for NNC1, its adjacent duties column specifies the *"Reminder letter"*, matching pages 18 and 36.
  * **System Reconciliation:** {app_name}'s `escalation_service.py` reconciles this by requiring a recorded `annex_e` defect notice before `annex_m` (NNC1) can be generated (`missing_annex_e`), and enforcing a strict 15-working-day post-receipt tolling window (`FOLLOW_UP_WORKING_DAYS = 15`) between dispatched notices (`annex_m` $\rightarrow$ `annex_n` $\rightarrow$ `annex_o`).
  * If unheeded, the DILG Provincial Director issues **[Notice of Non-Compliance No. 1 (NNC1 / Annex M)](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_m_nnc1.md)**, followed after 15 working days by **[Notice of Non-Compliance No. 2 (NNC2 / Annex N)](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_n_nnc2.md)**, and finally **[Notice of Non-Compliance No. 3 (NNC3 / Annex O)](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_o_nnc3.md)** issued exclusively by the Regional Director.

---

## 2. Operational Practice (PDMU Interviews & Field Realities)

* **Colloquial Terminology:** In recorded staff interviews, PDMU personnel describe this action as: *"Binabalik namin kapag dis-approve"* (returned when disapproved; Copy of DILG Transcript line 167) or *"babalik sa LGU with comments"*.
* **Informal Consultation & Triage:** Engineers frequently conduct preliminary phone or Viber consultations with Municipal Planning and Development Coordinators (MPDCs) or Municipal Engineers to explain required adjustments before formal transmittals are logged.
* **Routine Digital Returns vs. Formal Escalation Notices:** Routine digital returns of draft PDFs in DMS occur frequently during iterative engineering review. These daily technical returns do not automatically trigger formal non-compliance notices unless persistent non-responsiveness surpasses established escalation milestones.

---

## 3. Top 10 Verified Real-World Reasons for Return

Based on primary evidence from DILG Annexes B, C, and E, and forensic review of PDMU evaluation records:

| Rank | Reason Category | Concrete Real-World Example | Primary Authority Reference |
| :---: | :--- | :--- | :--- |
| **1** | **Missing Mandatory Attachments & Schedules** | Transmittal submitted without mandatory Annex C checklist, detailed bid evaluation sheets, or geotagged photos. | PDMU Operations Manual p. 50; Annex C Item 1. |
| **2** | **Incomplete Signatures, Approvals, or Notarizations** | Program of Works (POW) signed by Municipal Engineer but lacking approval signature of the Mayor (LCE); Omnibus Sworn Statement lacking Notary Public jurat and seal. | Annex C Item 1.2; Operations Manual p. 50; LM Transcript line 28. |
| **3** | **Cross-Document Data Discrepancies** | Approved Budget for the Contract (ABC) on the POW conflicts with the Sangguniang Appropriation Ordinance; contract amount conflicts with Notice of Award. | Annex C Completeness Checklist; Annex E Matrix; Operations Manual p. 27. |
| **4** | **Defective Engineering Costing & DUPA** | Program of Works lacks Detailed Unit Price Analysis (DUPA); material unit rates diverge from DPWH regional indices without price escalation justification. | Annex C Pre-Implementation Checklist; Operations Manual p. 27. |
| **5** | **Missing Statutory Clearances (RROW, Geohazard, ECC)** | Road construction submitted without Proof of Land Ownership / Deed of Donation / RROW waiver; missing MGB Geohazard Assessment or DENR Environmental Compliance Certificate. | Annex B Item B.2; Annex C Section 1; DBM LBC 155. |
| **6** | **Vehicle-Specific Regulatory Non-Conformities** | Acquisition of rescue vehicle submitted without DBM Authority to Purchase Motor Vehicles (APMV) or exceeding DBM engine displacement caps. | PDMU Operations Manual p. 19; DBM Budget Circular 2022-1; Appendix 19. |
| **7** | **Financial Liquidation Inconsistencies** | Statement of Receipts and Disbursements (SORD) does not reconcile with bank statements; proof of return of unexpended balance to National Treasury omitted. | PDMU Operations Manual p. 19, 27; COA Circular 2012-001. |
| **8** | **Untimely Submission / Milestone Overdue** | Milestone document submitted past statutory cut-off (e.g., Monthly Progress Report submitted after the 25th of the month). | PDMU Operations Manual p. 18, 51–52; DILG MC 2024-134. |
| **9** | **Obsolete or Non-Standard Templates** | LGU submitted reports using repealed 2018 DILG MC templates rather than mandatory DILG MC 2023-063 Omnibus forms. | DILG MC 2023-063; PDMU Operations Manual p. 19. |
| **10** | **Illegible, Incomplete, or Truncated Scans** | Multi-page PDF missing alternating pages due to duplex scanning error; signature block or official dry seal cut off in scan. | Audio Transcript line 8; DMS Review SOP. |

---

## 4. Canonical Deficiency Categories and Resolution States

In {app_name}'s database model (`backend/app/models/workflow.py`), deficiencies logged during review are structured under canonical categories and lifecycle states:

### Canonical Deficiency Categories (`DEFICIENCY_CATEGORIES`)
1. `missing_attachment`: Omission of required annex checklists, bid evaluation sheets, or geotagged photos.
2. `missing_signature_notarization`: Missing LCE approval, engineer certification, or notary public jurat/seal.
3. `cross_document_inconsistency`: Conflicting amounts or dates between POW, ABC, appropriation ordinance, or contract.
4. `costing_dupa_defect`: Incomplete unit price breakdown, unjustified markups, or deviation from DPWH price standards.
5. `missing_statutory_clearance`: Lack of RROW deed/waiver, geohazard assessment, ECC/CNC, or building permit.
6. `program_specific_non_conformity`: Violation of program guidelines (e.g., APMV vehicle caps, ineligible expenditure).
7. `financial_reconciliation_defect`: SORD discrepancy, unreconciled bank balance, or missing refund proof.
8. `scan_quality_defect`: Truncated, illegible, upside-down, or missing pages in uploaded PDF.
9. `other_documented_defect`: Other documented technical or administrative deficiencies not covered above.

### Canonical Resolution States (`DEFICIENCY_RESOLUTION_STATES`)
* **`open`**: Deficiency recorded by reviewer; awaiting LGU corrective action and resubmission.
* **`resolved`**: Corrected document verified by reviewer; deficiency cleared.
* **`waived`**: Formally excused by authorized administrator with documented justification.

---

## 5. Current System Implementation in {app_name}

* **Reviewer Action:** In the Project Detail Requirements tab, an authorized reviewer (`admin` or `staff`) selects **Return for Revision**.
* **State Transition on Return:**
  * `workflow_status` transitions to `returned_for_revision`.
  * `compliance_status` **strictly remains `under_review`**. It is NOT marked `non_compliant`.
* **Deficiency Logging:** The reviewer enters required deficiency remarks under one of the canonical categories, which are recorded with the reviewer's identity and timestamp.
* **Resubmission Lifecycle:** When the LGU resubmits a corrected file, the existing version is archived, and the new upload transitions `workflow_status` to `resubmitted` (or `submitted`), while `compliance_status` **strictly remains `under_review`**, maintaining an unbroken audit trail for COA compliance.
* **Review Clock Tolling:** Under RA 11032 Sec. 9, returning a submission with deficiency remarks suspends the internal processing turnaround as a legal matter while triggering the LGU's corrective cure countdown. In {app_name}, this is an architectural principle and operational policy; automated database tolling is not currently implemented as an active background job in `sla_service.py`.
