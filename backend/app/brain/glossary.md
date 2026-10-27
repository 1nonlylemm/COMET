---
topic: "{app_name} and PDMU Domain Glossary"
category: "glossary"
roles:
  - "admin"
  - "staff"
  - "field_officer"
  - "system_admin"
source_type:
  - "operations_manual"
  - "system_implementation"
  - "staff_interview"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
  - "others/reference_data/NEW UPDATE DATA/LM Transcript.txt"
  - "others/reference_data/NEW UPDATE DATA/Video Runthrough Transcript.txt"
  - "backend/app/models/project.py"
  - "backend/app/models/workflow.py"
  - "docs/research/PDMU_DOCUMENT_REVIEW_RETURN_PROCESS_ANALYSIS.md"
authority: "Level 1, Level 2, and Level 3 Reconciled"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "glossary"
  - "compliance status"
  - "workflow status"
  - "deficiency"
  - "returned_for_revision"
  - "non_compliant"
  - "waived"
  - "working_day_deadline"
  - "sla"
  - "nnc1"
  - "nnc2"
  - "nnc3"
  - "pdmu"
  - "lgu"
  - "dms"
  - "subaybayan"
  - "closeout"
  - "regional handoff"
  - "pow"
  - "ded"
  - "dupa"
  - "abc"
  - "philgeps"
  - "noa"
  - "ntp"
  - "swa"
  - "nadai"
  - "sord"
  - "qaar"
  - "aide memoire"
  - "lgsf"
  - "falgu"
  - "sbdp"
  - "sglg"
  - "rcsp"
  - "gef"
  - "binabalik"
  - "chine-check"
  - "program of works"
  - "detailed engineering design"
  - "detailed unit price analysis"
  - "approved budget for the contract"
  - "notice of award"
  - "notice to proceed"
  - "statement of work accomplished"
  - "notice of authority to debit account issued"
  - "statement of receipts and disbursements"
  - "quality assurance assessment report"
  - "growth equity fund"
  - "local government support fund"
  - "financial assistance to local government units"
  - "support to barangay development program"
  - "seal of good local governance"
  - "retooled community support program"
  - "authority to purchase motor vehicles"
  - "management action report"
  - "bids and awards committee"
  - "local chief executive"
  - "municipal engineer"
  - "certificate of completion"
  - "project completion report"
  - "fund utilization"
  - "defects liability period"
  - "certificate of final acceptance"
  - "cofa"
  - "dlp"
  - "asset booking"
  - "cpes"
  - "report of disbursement / liquidations"
  - "appendix 1"
  - "appendix 2"
  - "appendix 3"
  - "mt-1"
  - "mt1a"
  - "mt1b"
  - "non-infrastructure monitoring templates"
---

# {app_name} and PDMU Domain Glossary

This glossary provides authoritative, source-grounded definitions across the Provincial Development and Management Unit (PDMU) domain, national statutory oversight policies, field operational practices, and the {app_name} software architecture.

---

## 1. Core Status & Lifecycle Taxonomy: Compliance Status vs. Workflow Status

A fundamental architectural distinction in {app_name} and DILG documentary review is the separation between **Compliance Status** (statutory state) and **Workflow Status** (procedural document movement state).

### Compliance Status (`status`)
Represents the legal and statutory compliance condition of a project requirement under national DILG/DBM guidelines and database constraint `ck_project_req_status`:
* **`pending`**: Baseline state before the LGU submits the documentary requirement, or awaiting initial review action.
* **`under_review`**: The document has been submitted or returned with findings; PDMU technical evaluation is actively ongoing.
* **`compliant`**: The document meets all technical, engineering, and administrative criteria stipulated in Annex B/C.
* **`non_compliant`**: Administrative escalation windows (15 working days post-NNC1/NNC2) have expired without deficiency resolution, or formal non-compliance has been adjudicated by the Provincial or Regional Director.
* **`waived`**: The requirement has been formally exempted by authorized authorities due to specific project modalities (e.g., RROW waiver when work is entirely within existing public road alignment), accompanied by mandatory written justification.

### Workflow Status (`workflow_status`)
Represents the tactical movement and custody stage of a document file within the review lifecycle under database constraint `ck_project_req_workflow_status`:
* **`draft`**: Document recorded or drafted internally, not yet formally submitted for evaluation.
* **`submitted`**: Document transmitted by the LGU or encoded by staff, awaiting engineering review.
* **`under_verification`**: Document submission is undergoing cross-verification against external systems (e.g., SubayBAYAN progress, DMS transmittals) or technical checklists.
* **`staff_approved`**: PDMU technical staff/engineer has completed evaluation and verified document completeness, recommending approval.
* **`pending_provincial_approval`**: Awaiting formal administrative endorsement or executive sign-off by the Provincial Director or designated authority.
* **`approved`**: Document successfully cleared technical review and validated as fully compliant.
* **`returned_for_revision`**: Deficiencies or technical errors were identified; custody of the document is returned to the LGU for corrections.
* **`resubmitted`**: The LGU has uploaded a revised version (`v2`, `v3`) addressing previously logged deficiencies; queued for reviewer re-evaluation.

> **CRITICAL RULE:** Returning a document for revision (`workflow_status = "returned_for_revision"`) does **NOT** make the requirement `non_compliant`. Its `compliance_status` remains `under_review` while the LGU addresses deficiencies during the allowed compliance window.

### Additional Lifecycle Terminology
* **`isWorkbookFieldLocked`**: System security state indicating that a data cell or project record is locked against direct inline edits due to active workflow review, regional handoff freeze, or administrative lock.
* **Review Clock Tolling**: The administrative legal principle derived from Republic Act No. 11032 (Ease of Doing Business Act, Sec. 9) whereby returning a submission with deficiency remarks suspends the internal reviewer turnaround clock while starting the LGU's corrective cure countdown. *(Note: In {app_name}, this is an architectural principle and operational expectation; automated database tolling is not currently implemented as an active background job in `sla_service.py`).*

---

## 2. Funding Programs & Allocations

* **LGSF (Local Government Support Fund)**:
  * *Official Policy:* National financial mechanism appropriated under the annual General Appropriations Act (GAA) to fund local development projects of LGUs.
  * *Operational Scope:* Encompasses FALGU, SBDP, SGLG-IF, and disaster rehabilitation allocations monitored by the PDMU.
  * *Sources:* DILG Operations Manual p. 11; DBM Local Budget Circulars.
* **FALGU (Financial Assistance to Local Government Units)**:
  * *Official Policy:* Sub-program of the LGSF providing financial assistance directly to municipalities, cities, and provinces for priority socio-economic infrastructure (roads, bridges, water supply, evacuation centers).
  * *Operational Practice:* Staff interview transcripts refer to this colloquially as *"Falbo"* (Video Transcript line 43; LM Transcript line 5).
  * *Sources:* DILG MC No. 2023-063; Operations Manual p. 11.
* **SBDP (Support to Barangay Development Program)**:
  * *Official Policy:* Development intervention providing infrastructure funding (farm-to-market roads, health stations, rural electrification) to cleared barangays under the Retooled Community Support Program (RCSP).
  * *Operational Context:* Considered the capital investment phase following grassroots community validation.
  * *Sources:* Operations Manual p. 11; LM Transcript line 8.
* **SGLG-IF (Seal of Good Local Governance Incentive Fund)**:
  * *Official Policy:* Financial grant awarded to LGUs that successfully achieve the Seal of Good Local Governance, utilized to finance local development initiatives.
  * *Operational Context:* Previously known as the Performance Challenge Fund (PCF).
  * *Sources:* Operations Manual p. 11; RA 11292.
* **GEF / GAF (Growth Equity Fund)**:
  * *Official Policy:* National government fund providing financial support to 4th, 5th, and 6th class municipalities with high poverty incidence to close developmental disparities.
  * *Operational Context:* Staff transcripts note GAF as targeted infrastructure grants for lower-income LGUs (LM Transcript line 11).
  * *Sources:* Executive Order No. 138 s. 2021; LM Transcript line 11.
* **RCSP (Retooled Community Support Program)**:
  * *Official Policy:* Core DILG convergence program focused on identifying community issues and enhancing Barangay Development Plans (BDP) in priority areas.
  * *Sources:* LM Transcript line 20; Operations Manual p. 12.
* **Trust Fund Transfers**:
  * *Official Policy:* Fiscal procedure whereby national funding (LGSF) is transferred to an LGU's dedicated bank account under a trust liability agreement, subject to strict timeline tracking and COA liquidation rules.
  * *Sources:* COA Circular 2012-001; DILG Operations Manual p. 15.
* **Cash-Budgeting Reversion**:
  * *Official Policy:* National budget rule under the Executive One-Year Cash Budgeting System mandating that unexpended balances of completed or terminated projects must be reverted to the National Treasury upon expiration of fund validity.
  * *Sources:* General Appropriations Act (GAA); Operations Manual p. 27.

---

## 3. Engineering, Procurement, & Technical Review

* **POW (Program of Works)**:
  * *Official Policy:* Mandatory pre-procurement engineering document detailing project scope, work items, physical dimensions, material specifications, equipment schedules, and total estimated budget.
  * *Review Gate:* Must be signed by the Municipal/City Engineer and approved by the Local Chief Executive (Mayor). Evaluated by PDMU engineers under Annex C.
  * *Sources:* Annex B Item 1.1; Annex C Pre-Implementation Checklist.
* **DED (Detailed Engineering Design)**:
  * *Official Policy:* Comprehensive architectural and engineering drawings, structural computations, plan and profile, cross-sections, and technical specifications governing construction.
  * *Review Gate:* Evaluated against National Building Code (PD 1096), DPWH Design Standards, and accessibility laws (BP 344).
  * *Sources:* Annex B Item 1.2; Operations Manual p. 27.
* **DUPA (Detailed Unit Price Analysis)**:
  * *Official Policy:* Itemized breakdown of unit costs comprising direct costs (materials, labor, equipment rental), indirect costs (overhead, contingencies, miscellaneous [OCM], contractor's profit), and applicable taxes.
  * *Engineering Review:* Evaluated by PDMU engineers against prevailing Construction Materials Price Data (CMPD) and DPWH regional unit rates to prevent cost inflation.
  * *Sources:* Annex B Item 1.3; Annex C Item 1.2.
* **ABC (Approved Budget for the Contract)**:
  * *Official Policy:* The maximum budget ceiling approved by the Head of the Procuring Entity (Local Chief Executive) for a contract, established in the POW and Annual Procurement Plan (APP). Bids exceeding the ABC are automatically rejected under RA 9184.
  * *Sources:* Republic Act No. 9184 Sec. 5(a); Annex B Item 2.
* **PhilGEPS (Philippine Government Electronic Procurement System)**:
  * *Official Policy:* Centralized electronic portal for government procurement where invitations to bid, bidding documents, notice of award, and notice to proceed must be publicly posted.
  * *Review Verification:* PDMU reviews PhilGEPS posting printouts with reference numbers as mandatory Annex B procurement requirements.
  * *Sources:* RA 9184 Sec. 8; Annex B Item 2.
* **NOA (Notice of Award)**:
  * *Official Policy:* Formal written notice from the LGU to the winning bidder stating that its bid has been accepted, triggering the contractor's obligation to post performance security within 10 calendar days.
  * *Sources:* RA 9184 Sec. 37.1; Annex B Item 2.7.
* **NTP (Notice to Proceed)**:
  * *Official Policy:* Executive issuance to the winning contractor authorizing the immediate commencement of civil works, specifying the contract start date and completion period.
  * *Review Prerequisite:* Mandatory prerequisite before physical construction can be acknowledged as officially ongoing.
  * *Sources:* RA 9184 Sec. 37.4; Annex B Item 2.9.
* **SWA (Statement of Work Accomplished)**:
  * *Official Policy:* Monthly technical report officially documented in **Annex F (dated August 10, 2022)**, detailing cumulative physical progress, itemized quantities, and billable amounts across a standardized **19-column mathematical matrix**.
  * *Mathematical Integrity:* PDMU civil engineers verify formulas: $\text{Col D} = A \times C$, $\text{Col H} = F + G$, $\text{Col J} = \frac{G \times E}{A}$, $\text{Col K} = I + J$, $\text{Col M} = \left(\frac{G}{A}\right) \times 100$, and $\text{Col P} = G \times C$.
  * *Tripartite Signatories:* Prepared by Contractor Authorized Representative, Checked & Verified by Municipal Engineer, Approved by Local Chief Executive.
  * *Final SWA Closeout Gate:* For project closeout, the Final SWA must show exactly 100.00% physical accomplishment across all contracted pay items; serves as an indispensable prerequisite for Annex G.
  * *Sources:* Annex F DOCX; Operations Manual pp. 16, 26; `completion_documents_service.py`.
* **Geotechnical Soil Investigation**:
  * *Official Policy:* Subsurface soil drilling and laboratory bearing capacity report required for multi-story buildings, evacuation centers, bridges, and slope mitigation structures.
  * *Common Deficiency:* Frequently omitted by LGUs for smaller municipal structures; absence triggers formal deficiency return under Annex B.
  * *Sources:* National Structural Code of the Philippines (NSCP); Annex B Item 1.4.
* **Variation Order (Change Order / Extra Work Order)**:
  * *Official Policy:* Formal contract modification covering additive or deductive changes within the general scope of the project, capped at 10% of original contract price under RA 9184.
  * *Review Procedure:* Requires prior technical justification, revised POW/DED, and submission to DILG/PDMU for evaluation.
  * *Sources:* RA 9184 Annex E; Operations Manual p. 21.
* **Suspension Order / Resume Order**:
  * *Official Policy:* Executive orders issued by the LGU temporarily halting civil works due to force majeure, right-of-way disputes, or adverse weather, followed by an official Resume Order adjusting contract duration.
  * *Sources:* RA 9184 Annex E Item 9; Operations Manual p. 21.
* **As-Built Plans**:
  * *Official Policy:* Final, scaled engineering drawings reflecting the exact dimensions, elevations, and structural modifications executed during construction, submitted during closeout.
  * *Sources:* Annex J Project Completion Report Template; Operations Manual p. 27.
* **Republic Act No. 9184 (Government Procurement Reform Act)**:
  * *Official Policy:* Primary statutory legislation governing public bidding, procurement modes, BAC resolutions, and contractual obligations in Philippine public works.
  * *Transitional Applicability:* Under Section 113 of RA 12009 and GPPB Resolution No. 05-2025, procurements where the invitation or bid posting occurred prior to the effectivity of the NGPA IRR (February 25, 2025) continue to be governed by RA 9184 and its 2016 Revised IRR.
* **Republic Act No. 12009 (New Government Procurement Act / NGPA)**:
  * *Official Policy:* Landmark national procurement statute enacted on July 20, 2024 (effective August 13, 2024, with its IRR effective February 25, 2025), modernizing public procurement processes, standard forms, and implementation.
  * *Section 112 (IRR and Standard Forms):* Mandates formulation of the IRR and updated Standard Procurement Forms (PBDs, APPs).
  * *Section 113 (Transitory Provision):* Mandates that prior to the effectivity of the NGPA IRR, RA 9184 and its IRR remained in full force, and grants procuring entities a three (3)-year transitory period to fully comply, reckoned from the approval/issuance of new Standard Procurement Forms (GPPB Resolution No. 05-2025 / Circular No. 01-2025).
* **Republic Act No. 11032 (Ease of Doing Business and Efficient Government Service Delivery Act of 2018)**:
  * *Official Policy:* Statutory act prescribing processing turnarounds (3 to 7 working days) and codifying the legal rule that processing clocks are suspended while applications are returned for client corrections.

---

## 4. Administrative Escalation, Legal Clearances, & Monitoring Forms

* **NADAI (Notice of Authority to Debit Account Issued)**:
  * *Official Policy:* Official banking transmittal/notice issued by the Bureau of the Treasury (BTr) via the DILG Regional Office notifying the LGU that project funds have been credited directly to its designated trust account.
  * *Procedural Trigger:* Receipt of the NADAI by an LGU formally starts the 15-working-day administrative procedural countdown (Operations Manual p. 16, Step 2, Seq. 2) for the LGU to confirm fund receipt and enroll the project in SubayBAYAN.
  * *Sources:* PDMU Operations Manual p. 15–16 (Steps 1 & 2); DBM LBC 155; SEED_DOCUMENTARY_REQUIREMENTS_CLEANUP.md.
* **SORD (Statement of Receipts and Disbursements) / Report of Disbursement / Liquidations (Annex H)**:
  * *Official Policy & Title Reconciliation:* Formally titled **"Report of Disbursement / Liquidations"** in the DILG Omnibus Guidelines (Annex H dated August 10, 2022); universally designated as the **Statement of Receipts and Disbursements (SORD)** in the PDMU Operations Manual Final (pp. 26–27, 34, 44), SGLG-IF guidelines, and {app_name} database models (`final_sord`).
  * *Financial Structure:* 6-column disbursement ledger (Payee, Nature of Payment, Check No., Date, Amount, Remarks) tracking cumulative payments against the NTA/NADAI grant allocation.
  * *Signatory Chain:* Certified Correct by Local Accountant and Local Treasurer; Approved by Local Chief Executive.
  * *COA Receipt & 3-Month Fund Reversion:* For project closeout, must bear the official "Received" stamp of the resident COA Auditor. If an unexpended balance remains, statutory rules under the annual General Appropriations Act (GAA) Special Provisions mandate reversion to the National Treasury (BTr) within three (3) months after payment of final billing.
  * *Sources:* Annex H DOCX; COA Circular 2012-001; Operations Manual pp. 26, 44; `completion_documents_service.py`.
* **Certificate of Completion (Annex G)**:
  * *Official Policy:* Formal completion certificate issued by the Local Chief Executive (Mayor/Governor) and acknowledged by the Contractor upon 100% completion of civil works, based on a joint Inspectorate Team Inspection Report.
  * *Statutory Preservation of Liability:* Expressly stipulates that issuance does NOT relieve the contractor of warranty obligations under RA 9184 during the 1-year Defects Liability Period (DLP).
  * *Downstream Countdown:* Triggers the 30-day administrative compliance window for the submission of the Project Completion Report (Annex J) under Operations Manual p. 26.
  * *Sources:* Annex G DOCX; Operations Manual pp. 19, 26–27, 44.
* **Report on Fund Utilization and Status of Implementation (Annex I)**:
  * *Official Policy:* Official quarterly reporting instrument prescribed under DBM Local Budget Circulars (e.g., LBC 155 Sec. 3.7.1) and DILG Omnibus Guidelines (dated August 10, 2022) detailing project-by-project fund receipts, contractual obligations, actual disbursements, and physical progress across 12 structured columns.
  * *Governance & Signatories:* Certified correct by the Local Finance Committee (Local Budget Officer, Local Treasurer, Local Planning and Development Coordinator); Attested by the Local Chief Executive.
  * *Transparency Mandate:* Subject to the statutory Full Disclosure Policy (FDP) under annual GAA rules, requiring public posting on the LGU portal and in 3 conspicuous physical locations.
  * *Sources:* Annex I DOCX; DBM LBC 155; Operations Manual p. 19.
* **Project Completion Report (PCR - Annex J)**:
  * *Official Policy:* Comprehensive 6-section closeout compilation dossier due within thirty (30) days upon issuance of the Certificate of Completion.
  * *Components:* Includes Basic Data (Table 0), Procurement & Implementation Milestones (Table 1), Disbursements (Table 2), CPES Contractor Performance ratings @ 30%, 60%, 100% (Table 3), qualitative Problem/Assessment narratives, and 4 mandatory attachments (Annex G, COA-stamped Annex H, contract modification orders, geotagged "As-Built" photos).
  * *Dual Signatory Framework:* Prepared by Municipal Engineer and Noted by LCE (for LGU); Prepared by DILG Project Engineer and Noted by Provincial Director (for DILG PO).
  * *Sources:* Annex J DOCX; Operations Manual pp. 19, 26–27, 34, 44.
* **Defects Liability Period (DLP)**:
  * *Official Policy:* One-year statutory warranty period codified under Section 62 of Republic Act No. 9184 and its 2016 Revised IRR Annex E Section 12.3, starting from the completion date certified in Annex G, during which the contractor is legally bound to repair structural defects and failures at their own expense. Under Section 113 of RA 12009, legacy contracts continue under this warranty regime.
  * *Sources:* RA 9184 Sec. 62; RA 12009 Sec. 113; Annex G; Operations Manual pp. 26–27.
* **Certificate of Final Acceptance (COFA)**:
  * *Official Policy:* Final executive certification issued by the LGU within thirty (30) days following the conclusion of the 1-year Defects Liability Period, preceded by a joint project assessment conducted thirty (30) days prior to DLP expiration.
  * *Legal Consequence:* Formally discharges the contractor from patent/latent defect liability and authorizes the final release of retention money and performance bond under RA 9184 IRR Annex E Section 12.4.
  * *Sources:* RA 9184 IRR Annex E Sec. 12.4; Operations Manual pp. 26–27, 44; `completion_documents_service.py`.
* **Asset Booking**:
  * *Official Policy:* Mandatory fiscal procedure wherein the DILG C/MLGOO ensures that the completed facility, infrastructure, or vehicle is formally booked into the LGU's Property, Plant, and Equipment (PPE) asset ledger within one (1) month after payment of the Final Billing.
  * *Sources:* Operations Manual p. 44 (Step 5).
* **CPES (Constructors Performance Evaluation System)**:
  * *Official Policy:* Standardized national technical evaluation system measuring contractor performance, workmanship, materials quality, timeliness, and safety across three compulsory project milestones: @ 30%, @ 60%, and @ 100% completion. Recorded in Table 3 of Annex J.
  * *Sources:* CIAP / NEDA CPES Guidelines; Annex J Table 3.
* **Form 3 (LGU Progress Inspection Request)**:
  * *Official Policy:* LGU request form transmitted to DILG Provincial Office requesting on-site engineering inspection or final completion validation.
  * *Sources:* Operations Manual p. 16, 26.
* **QAAR (Quality Assurance Assessment Report)**:
  * *Official Policy:* Structured engineering assessment conducted during site visits, evaluating construction quality, adherence to specifications, and material test certificates.
  * *Sources:* PDMU Operations Manual p. 17.
* **Aide Memoire**:
  * *Official Policy:* Operational on-site summary document executed by visiting PDMU engineers and LGU officials immediately following a field inspection, recording observed defects, agreed corrective measures, and deadlines.
  * *Sources:* Operations Manual p. 17; LM Transcript line 104.
* **Notice of Deficiencies (Annex E)**:
  * *Official Policy:* Standardized notification form issued by PDMU engineers cataloging specific omissions, engineering defects, or non-conforming rates across a 4-column matrix (Findings, Recommendations, Timelines, Remarks) spanning Project Management, Quality, Timeliness, and Safety.
  * *Timeline & Escalation Nuance:* The Annex E form contains an open **TIMELINES** column for prescribed and agreed completion dates based on engineering defect severity. Under official procedure (Operations Manual pp. 18, 36), the formal 15-working-day administrative procedural deadline attaches to the **Reminder Letter** and subsequent **Notices of Non-Compliance (NNC1, NNC2, NNC3)**, while Page 26 contains a single textual anomaly referencing "Notice of Deficiency" in the deadline column for NNC1 next to "Reminder letter" in the duty column. In {app_name}'s system implementation (`escalation_service.py`), generating an `annex_e` record is required before `annex_m` (NNC1) can be dispatched, and the 15-working-day follow-up window is enforced between successive formal notices.
  * *Sources:* Annex E PDF; Operations Manual pp. 18, 26, 36; `escalation_service.py`.
* **Reminder Letter / Findings Letter**:
  * *Official Policy:* Administrative letter issued by the DILG Provincial Office giving an LGU 15 working days upon receipt to resolve outstanding deficiencies or submit lacking documents before formal notices are triggered.
  * *Sources:* Operations Manual p. 18, 51.
* **Notice of Non-Compliance No. 1 (NNC1)**:
  * *Official Policy:* Formal administrative notice signed and issued exclusively by the **Provincial Director (PD)** when an LGU remains unresponsive or non-compliant 15 working days following receipt of a Reminder Letter.
  * *Official / System Convention:* Officially prescribed as **Annex M** in DILG MC No. 2023-063 p. 17; referred to as "Notice of Non-Compliance No. 1" in PDMU Operations Manual Final (pp. 18, 20, 26, 51); labeled as `annex_m` in {app_name} seed templates.
  * *Sources:* DILG MC No. 2023-063 p. 17; Operations Manual p. 18, 20, 26, 51.
* **Notice of Non-Compliance No. 2 (NNC2)**:
  * *Official Policy:* Formal second notice signed and issued exclusively by the **Provincial Director (PD)** when non-compliance persists 15 working days following receipt of NNC1.
  * *Official / System Convention:* Officially prescribed as **Annex N** in DILG MC No. 2023-063 p. 17; referred to as "Notice of Non-Compliance No. 2" in PDMU Operations Manual Final (pp. 18, 20, 26, 51); labeled as `annex_n` in {app_name} seed templates.
  * *Sources:* DILG MC No. 2023-063 p. 17; Operations Manual p. 18, 20, 26, 51.
* **Notice of Non-Compliance No. 3 (NNC3)**:
  * *Official Policy:* Formal third notice signed and issued exclusively by the **Regional Director (RD / RO)**, NOT the Provincial Director. Issued if non-compliance persists 15 working days following receipt of NNC2.
  * *Legal Consequence:* Triggers formal referral to Bantay Korapsyon for legal concurrence and endorsement to the Office of the Undersecretary for Local Government (OUSLG).
  * *Official / System Convention:* Officially prescribed as **Annex O** in DILG MC No. 2023-063 p. 17; referred to as "Notice of Non-Compliance No. 3" in PDMU Operations Manual Final (pp. 18, 21, 26, 51); labeled as `annex_o` in {app_name} seed templates.
  * *Sources:* DILG MC No. 2023-063 p. 17; Operations Manual p. 18, 21, 26, 51.
* **Letter of Commitment (Annex K)**:
  * *Official Policy:* Executive written commitment executed by the Local Chief Executive (Mayor/Governor) for ongoing projects near fund validity expiration where funds cannot be transferred to trust accounts. Note: While styled on the signature line as "Affiant", the form is titled Letter of Commitment and lacks a notary jurat or acknowledgment block.
  * *Three Codified Undertakings:* (1) Revert unutilized grant funds to the Bureau of the Treasury (BTr) and allocate counterpart local funds equivalent to the reverted amount to complete remaining civil works; (2) Complete the project not later than the target date agreed with the DILG Regional Office; and (3) Submit the Project Completion Report (Annex J) within thirty (30) calendar days after the issuance of the Certificate of Completion.
  * *Cross-Program Disambiguation:* In the DILG Omnibus Guidelines, Annex K designates this Sample Letter of Commitment. In SGLG-IF guidelines, Annex K designates the Motor Vehicle Report Form (for vehicle grants).
  * *Sources:* Annex K DOCX; PDMU Operations Manual Final p. 20 (Step 4, Seq. 4).
* **Management Action Report Summary (Annex L)**:
  * *Official Policy & Purview:* Internal monthly administrative reporting instrument formally subtitled *"List of Non-Compliant Local Government Units Issued with a Notice of Non Compliance"*. Used by DILG Provincial and Regional Offices to consolidate and report all LGUs issued formal Notices of Non-Compliance (NNC1, NNC2, NNC3) upward to the DILG Central Office (OPDS).
  * *Standard 5-Column Matrix:* Province, Local Government Unit, Program / Project Title (`<Year / Program / Project Title>`), Action Taken (NNC number and date issued), Remarks.
  * *Monthly Cadence (Manual pp. 17, 34):* DILG PO conducts monthly risk assessment on the 25th and submits the provincial MAR to DILG RO on the 26th (or within 1 working day); DILG RO consolidates regional submissions and transmits the MAR to DILG Central Office on the 28th.
  * *Signatory Chain:* Prepared by DILG Regional Engineer, Approved by PDMU Chief, Noted by DILG Regional Director.
  * *Cross-Program Disambiguation:* In the DILG Omnibus Guidelines, Annex L designates this Management Action Report. In SGLG-IF guidelines, Annex L designates the Permanent Marker for Completed Projects.
  * *Sources:* Annex L DOCX; PDMU Operations Manual Final pp. 17, 34.
* **Official DILG Annex D (Unverified Gap)**:
  * *Status:* **NOT FOUND / NOT VERIFIED** in repository reference archives.
  * *Context:* While Annexes A, B, C, E, F, G, H, I, J, K, L exist in official archives, Annex D is missing from local disk. The Smart Assistant must acknowledge this evidentiary limitation rather than inferring or fabricating its contents.
* **Appendix 1–19 Non-Infrastructure Monitoring Forms**:
  * *Official Policy:* DILG monitoring templates governing non-civil works (Operations Manual pp. 17, 19): MT1 (Learning Materials / Appendices 1–3), MT2 (Financial Assistance / Appendices 4–10), MT3 (Livelihood Assistance / Appendices 11–15), MT4 (Medical Devices / Appendices 16–17), Appendix 18 (DRR Vehicles), and Appendix 19 (APMV). Mandatory during implementation field monitoring and project closeout.
  * *Sources:* Omnibus Guidelines Appendices 1–19; PDMU Operations Manual Final pp. 17, 19.
* **Summary of Distribution for Learning Materials (Appendix 1 / MT-1)**:
  * *Official Policy:* 13-column non-infra monitoring summary tracking itemized allocations, prior distributions, current period distributions, cumulative to-date distributions, and remaining balances for educational materials. Prepared by LGU General Services Officer (GSO) and approved by Local Chief Executive (LCE). Must be supported by MT-1A and MT-1B.
  * *Sources:* Appendix 1 XLSX; PDMU Operations Manual Final pp. 17, 19; Annex B Table 7.
* **Distribution Receipt for Learning Materials (Appendix 2 / MT-1A)**:
  * *Official Policy:* Institutional delivery and acknowledgment receipt acknowledging receipt of learning materials in good condition from Implementing LGU to recipient school or educational institution. Certified by the Institution Supply Officer (with Date Received) and noted by the Head of Institution (Principal). Serves as mandatory primary evidence supporting MT-1 current period distributions.
  * *Sources:* Appendix 2 XLSX; PDMU Operations Manual Final pp. 17, 19; Annex B Table 7.
* **Report on Beneficiaries Provided with Learning Materials (Appendix 3 / MT-1B)**:
  * *Official Policy:* 10-column granular end-beneficiary distribution roster documenting student names, sex, age, address, contact, education level, valid school ID (commonly LRN), received items, and signatures. Includes explicit instruction that if the beneficiary is below 18 years old, a parent or guardian must sign. Prepared by Institution Supply Officer and noted by Head of Institution.
  * *Sources:* Appendix 3 XLSX; PDMU Operations Manual Final pp. 17, 19; Annex B Table 7.
* **Summary of Financial Assistance (Appendix 4 / MT-2)**:
  * *Official Policy:* 9-column non-infra monitoring summary tracking previous, current period, and cumulative beneficiaries and amounts granted across 6 standardized assistance types (Medical, Burial, Transportation, Food, Other Support Services, Educational). Features a 4-line financial utilization summary block. Prepared by Social Worker, noted by P/C/M Accountant, reviewed by P/C/MSWDO Head, and approved by Local Chief Executive. Must be supported by MT-2A through MT-2F.
  * *Sources:* Appendix 4 XLSX; PDMU Operations Manual Final pp. 17, 19; Annex B Table 7.
* **Medical Financial Assistance Beneficiary Report (Appendix 5 / MT-2A)**:
  * *Official Policy:* 18-column granular medical assistance roster documenting patient details, representative interviewee identity, medical institution, payment amounts, and 5 supporting document checkboxes. Features printed allowable assistance caps (hospitalization P1,000–P150,000, out-patient medicines/lab P1,000–P10,000 every 3 months) and valid ID alternative rule (Barangay Certification). Signed by Social Worker, reviewed by MSWDO Head, noted by Accountant, approved by LCE.
  * *Sources:* Appendix 5 XLSX; PDMU Operations Manual Final pp. 17, 19; Annex B Table 7.
* **Burial Financial Assistance Beneficiary Report (Appendix 6 / MT-2B)**:
  * *Official Policy:* 18-column granular burial assistance roster documenting deceased details, ethnicity, cause/date of death, representative interviewee identity, payment amounts, and 3 supporting document checkboxes (Death Certificate, Funeral Contract, Transfer Permit). Features printed allowable assistance caps (funeral P5,000–25,000, transfer of cadaver P5,000–P25,000, disaster casualty outright P10,000 without case study report). Signed by Social Worker, reviewed by MSWDO Head, noted by Accountant, approved by LCE.
  * *Sources:* Appendix 6 XLSX; PDMU Operations Manual Final pp. 17, 19; Annex B Table 7.
* **APMV (Authority to Purchase Motor Vehicles - Appendix 19)**:
  * *Official Policy:* Statutory authorization issued by the Department of Budget and Management (DBM) required before an LGU can procure motor vehicles or heavy equipment, enforcing engine displacement limits.
  * *Sources:* DBM Budget Circular No. 2022-1; Appendix 19.
* **Bantay Korapsyon Referral**:
  * *Official Policy:* Formal transmittal of non-compliant project dossiers to the DILG Bantay Korapsyon unit for investigation of suspected fraudulent acts, willful default, or violation of RA 3019 (Anti-Graft and Corrupt Practices Act).
  * *Sources:* Operations Manual p. 21; LM Transcript line 116.

---

## 5. Organizational Roles, Units, & Personnel

* **PDMU (Provincial Development and Management Unit)**:
  * The technical unit of the DILG Provincial Office responsible for monitoring, evaluating, and providing technical assistance for locally funded projects (LGSF, FALGU, SBDP, SGLG-IF).
* **LGU (Local Government Unit)**:
  * The municipality, city, or provincial government implementing the project.
* **LCE (Local Chief Executive)**:
  * The Municipal or City Mayor (or Provincial Governor); statutory head of the LGU who approves POWs, signs contracts, authorizes transmittals, and receives formal notices.
* **Municipal / City Engineer**:
  * The head of the local engineering office responsible for preparing the POW, DED, and DUPA, supervising construction, and certifying SWA physical accomplishments.
* **MPDC / CPDO (Municipal/City Planning and Development Coordinator)**:
  * Head of the local planning office coordinating project identification and BDP inclusion.
* **BAC (Bids and Awards Committee)**:
  * The statutory body within the LGU responsible for publishing procurement opportunities, conducting bid openings, evaluating bids, and recommending contract awards under RA 9184.
* **C/MLGOO (City/Municipal Local Government Operations Officer)**:
  * DILG field personnel deployed to specific municipalities. Acts as field liaison and monitoring coordinator between the LGU, cluster heads, and the provincial PDMU.
* **Provincial Director (PD)**:
  * Head of the DILG Provincial Office; official signatory of Reminder Letters, NNC1, and NNC2 notices.
* **Regional Director (RD / RO)**:
  * Head of the DILG Regional Office; exclusive signatory of NNC3 notices and receiver of regional handoff packages.
* **OUSLG (Office of the Undersecretary for Local Government)**:
  * Executive central office unit overseeing national LGU project monitoring and escalation concurrence.
* **DBM (Department of Budget and Management)**:
  * National agency releasing fund allocations, Local Budget Circulars (LBC), and APMV approvals.
* **COA (Commission on Audit)**:
  * Independent constitutional commission governing state audits, pre- and post-disbursement validation, and liquidation standards under COA Circular 2012-001.
* **System Administrator (`system_admin`)**:
  * Application role responsible for database health, security policies, user provisioning, and audit log inspection.
* **Provincial Administrator (`admin`)**:
  * Operational director role overseeing high-level project approval, formal notice sign-offs, and cluster allocations.
* **PDMU Technical Staff (`staff`)**:
  * Civil engineers and technical officers who evaluate submitted engineering plans, log deficiencies, execute returns for revision, and curate handoff files.
* **Field Officer (`field_officer`)**:
  * Field monitoring inspectors who conduct on-site project visits, log photo evidence, and inspect checklist items.

---

## 6. Taglish & Filipino Operational Idioms (from Field Interviews)

* **"Binabalik kapag dis-approve"**:
  * *Meaning:* Colloquial shorthand used by PDMU staff to describe returning a documentary submission to the LGU for corrections due to identified deficiencies.
  * *Official Correlate:* `workflow_status = "returned_for_revision"`.
  * *Source:* Copy of DILG Transcript line 167.
* **"Chine-check" / "Nagche-check-check"**:
  * *Meaning:* Operational phrasing describing PDMU staff checking regional monitoring spreadsheets, Google Drive folders, and submitted engineering plans against technical checklists.
  * *Source:* Combined Interview Transcript line 5.
* **"Side visit / Aide Memoire check"**:
  * *Meaning:* Operational practice where PDMU staff conduct on-site field inspections to verify if construction is actually ongoing and record field observations in an Aide Memoire.
  * *Source:* LM Transcript lines 101–104.
* **"Sisingilin ni field officer"**:
  * *Meaning:* The specific missing documentary requirements that the field officer is tasked with collecting from the municipal engineer or MPDC.
  * *Source:* LM Transcript line 149.
* **"Naka-under" / "Saang proyekto naka-under"**:
  * *Meaning:* Operational expression referring to which project record, funding program, or municipal cluster a specific document or expenditure belongs.
  * *Source:* Combined Interview Transcript line 7.
* **"Makikita sa folder" / "Regional Drive"**:
  * *Meaning:* Refers to the shared Google Drive folder structures maintained by the Regional Office (e.g. FileBook 2024, FileBook 2025) where PDMU uploads approved project dossiers.
  * *Source:* Combined Interview Transcript lines 5, 7.
* **"Mano-mano"**:
  * *Meaning:* Manual, spreadsheet-based data collation and paper filing performed prior to system digitization.
  * *Source:* LM Transcript line 161.
* **"Endorse sa Regional"**:
  * *Meaning:* Transmitting fully evaluated, compliant project packages to the Regional Office repository for final regional reporting.
  * *Source:* LM Transcript line 47.

---

## 7. Systems, Intranets, & Software Platforms

* **DMS (Document Management System)**:
  * *Official Context:* The internal intranet barcoding and document routing system used across DILG Laguna for incoming/outgoing correspondence.
  * *Operational Reality:* LGUs submit digital scans through DMS. It follows a strict hierarchical channel: LGU $\rightarrow$ Field Officer $\rightarrow$ Cluster Head $\rightarrow$ Provincial PDMU $\rightarrow$ Regional Office. {app_name} is not a replacement for DMS.
  * *Sources:* Combined Interview Transcript line 16; LM Transcript line 119.
* **SubayBAYAN**:
  * *Official Context:* The national public-facing online platform for monitoring LGU infrastructure projects under DILG MC No. 2024-134.
  * *Operational Scope:* Requires monthly reporting (due on the 25th of each month) of high-level physical and financial progress (SWA, geotagged photos, risk level, TPM).
  * *Key Difference:* SubayBAYAN does *not* track granular engineering document reviews, revision histories, or technical deficiency matrices (POW, DED, DUPA, NOA, NTP).
  * *Sources:* Combined Interview Transcript line 33; Subaybayan_Manual_Discovery.md.
* **{app_name}**:
  * *System Definition:* The provincial-level internal software system built for DILG Laguna PDMU to track 20+ engineering and bidding documents (Annex B/C), manage technical reviews, calculate working-day deadlines, and curate regional handoff packages.
* **SLA (Service Level Agreement)**:
  * *Current System Implementation:* Software term used in {app_name} for tracking statutory compliance deadlines (`sla_service.py`, `SlaTrackerPage`).
  * *Official Policy Note:* The acronym "SLA" appears **0 times** in the official DILG Operations Manual. Officially, these are designated as **Procedural Compliance Deadlines** or **Statutory Timelines**.
* **Working-Day Deadline**:
  * Compliance deadlines calculated strictly in business working days, excluding Saturdays, Sundays, regular national holidays, and proclaimed special non-working days.
* **Regional Handoff**:
  * The operational milestone where PDMU staff assemble fully reviewed, compliant project documentary packages and upload them to the DILG Regional Office repository (historically Google Drive).
* **Closeout**:
  * The final administrative stage following physical project completion, consisting of Annex G (Certificate of Completion), Annex H (Disbursements and Liquidations), Annex J (Project Completion Report), and reversion of unexpended balances.
