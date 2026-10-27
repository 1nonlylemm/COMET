---
topic: "Regional Handoff and Provincial Filtering Workflow"
category: "process"
roles:
  - "admin"
  - "staff"
source_type:
  - "operations_manual"
  - "staff_interview"
  - "official_annex"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
  - "others/reference_data/NEW UPDATE DATA/Video Runthrough Transcript.txt"
  - "backend/app/services/regional_handoff_service.py"
  - "backend/app/services/completion_documents_service.py"
authority: "Level 1, Level 2, and Level 3 Reconciled"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "regional handoff"
  - "transmittal"
  - "google drive"
  - "regional office"
  - "pdu"
  - "filtering"
  - "annex b handoff"
  - "completion handoff"
  - "closeout dossier"
---

# Regional Handoff and Provincial Filtering Workflow

This process guide outlines the regional handoff and transmittal workflow, detailing how the DILG Provincial Office acts as the mandatory filtering and validation gate between implementing LGUs and the DILG Regional Office (RO) for both pre-construction packages and final completion dossiers.

---

## 1. Official Regulatory Framework (PDMU Operations Manual)

* **Supervisory Authority:** The DILG Regional Office exercises administrative and technical supervision over all Locally Funded Projects across the region.
* **Two Distinct Handoff Phases in the Project Lifecycle:**
  1. **Phase 1: Pre-Construction Transmittal (Annex B Compliance):**
     * Following provincial desk review, engineering verification of the Program of Works (POW), Detailed Engineering Design (DED), Detailed Unit Price Analysis (DUPA), and procurement documents under Annex B and Annex C, the Provincial Office transmits the endorsed project package to the Regional Office for regional concurrence or disbursement release.
  2. **Phase 2: Project Closeout Transmittal (Full Completion Dossier):**
     * Upon project completion and provincial verification of the closeout matrix, the Provincial Office transmits the full completion dossier to the Regional Office Project Development Unit (PDU).
     * **Mandatory Closeout Transmittal Contents:**
       * Final Statement of Work Accomplished (Final SWA - Annex F) showing 100% completion
       * Certificate of Completion (Annex G) signed by the Local Chief Executive
       * Report of Disbursements & Liquidations / SORD (Annex H) stamped received by COA
       * Project Completion Report (Annex J) with CPES ratings and geotagged "As-Built" photos
       * Proof of Return of Funds (for unexpended balances reverted to BTr)
       * Certificate of Final Acceptance (COFA), transmitted following the 1-year Defects Liability Period.

---

## 2. Operational Reality & The Provincial "Filter" Role (Staff Interviews)

Field interviews with DILG Laguna PDMU personnel provide critical Level 2 operational context regarding how transmittals actually operate:

* **The Mandatory Provincial Filter:**
  > *"LGUs do not transmit directly to the Regional Office. Everything passes through the Provincial Office first. We filter everything, check the POW and DED against the approved GAA allocation, and verify signatures."*
  *(Combined Interview Transcript line 7)*
* **Operational Intake & Pre-Review:**
  * Submissions originating from Municipal Engineers or Local Chief Executives are initially received by deployed C/MLGOOs, endorsed through Cluster Heads within 3 working days, and funneled into the Provincial PDMU.
  * If deficiencies are identified, the Provincial Office returns them directly to the LGU using `returned_for_revision`. Incomplete or non-compliant files are **never** forwarded to the Regional Office.
* **Transmission Modality:**
  * In historical practice, PDMU technical staff uploaded verified, complete PDF packages to designated regional Google Drive folders maintained by the Regional Office, accompanied by a formal signed transmittal memorandum.

---

## 3. Current System Implementation in {app_name}

In {app_name}, the regional handoff process is centralized in `backend/app/services/regional_handoff_service.py` and accessed via the **Regional Handoff Console (`/dashboard/handoff`)**.

### Automated Eligibility & Manifest Compilation
* **100% Compliance Gate:**
  * For pre-construction packages, a project only appears in the handoff queue once all mandatory Annex B requirements have achieved `status = 'compliant'`.
  * For completed projects, the system verifies that all required rows in the Closeout Matrix (`final_swa`, `final_inspection_report`, `final_sord`, `proof_of_return_of_funds`) have achieved `workflow_status == 'approved'`.
* **Consolidated Transmittal Manifest:**
  * The system groups all approved files into an exportable, standardized transmittal package.
  * Generates an official DILG transmittal manifest detailing project metadata, document versions, dates of approval, and verifying engineers.
* **Transmittal Tracking:**
  * Allows PDMU staff to mark a package as *"Ready for Regional Transmittal"*.
  * Records the formal date of transmission, regional receiving clerk/officer, and Regional Office Document Management System (DMS) tracking reference number.
* **Access Control:**
  * Strictly restricted to `admin` (Provincial Director / Admin) and `staff` (PDMU technical engineers).
  * Field officers have view access to track transmittal status.
