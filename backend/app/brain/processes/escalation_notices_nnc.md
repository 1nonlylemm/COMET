---
topic: "Administrative Escalation and Notice Generation Process (NNC1, NNC2, NNC3)"
category: "process"
roles:
  - "admin"
  - "staff"
source_type:
  - "operations_manual"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "backend/app/services/notice_generation_service.py"
  - "backend/app/services/escalation_service.py"
authority: "Level 1 and Level 3 Reconciled"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "escalation"
  - "notices"
  - "nnc1"
  - "nnc2"
  - "nnc3"
  - "annexes m, n, and o"
  - "annexes m n o"
  - "letter designations"
  - "official designations"
  - "signatories"
  - "regional director"
  - "management action report"
---

# Administrative Escalation and Notice Generation (NNC1, NNC2, NNC3)

## 1. Official Procedure (PDMU Operations Manual, pp. 18, 20–21, 26, 51)

When an LGU fails to submit required project documents, correct noted deficiencies, or meet implementation milestones, DILG guidelines mandate a progressive 5-stage escalation chain:

```
┌────────────────────────────────────────────────────────┐
│               Stage 1: Reminder Letter                 │
│      Issued by PDMU / Provincial Office to LCE         │
└──────────────────────────┬─────────────────────────────┘
                           │ 15 working days post-receipt
                           ▼
┌────────────────────────────────────────────────────────┐
│     Stage 2: Notice of Non-Compliance No. 1 (NNC1)     │
│   Signed & Issued by: Provincial Director (PD)         │
│   Internal System Template: Annex M                    │
└──────────────────────────┬─────────────────────────────┘
                           │ 15 working days post-receipt
                           ▼
┌────────────────────────────────────────────────────────┐
│     Stage 3: Notice of Non-Compliance No. 2 (NNC2)     │
│   Signed & Issued by: Provincial Director (PD)         │
│   Internal System Template: Annex N                    │
└──────────────────────────┬─────────────────────────────┘
                           │ 15 working days post-receipt
                           ▼
┌────────────────────────────────────────────────────────┐
│     Stage 4: Notice of Non-Compliance No. 3 (NNC3)     │
│   Signed & Issued by: REGIONAL DIRECTOR (RD) ONLY      │
│   Internal System Template: Annex O                    │
└──────────────────────────┬─────────────────────────────┘
                           │ Continued non-compliance
                           ▼
┌────────────────────────────────────────────────────────┐
│ Stage 5: Bantay Korapsyon & OUSLG Legal Action         │
│ Endorsement for administrative/legal sanctions & audit │
└────────────────────────────────────────────────────────┘
```

### Critical Signatory Rule
* **NNC1 & NNC2:** Signed and issued by the **Provincial Director (PD)** of DILG Laguna.
* **NNC3:** Signed and issued **EXCLUSIVELY by the Regional Director (RD)** of DILG Region IV-A. A Provincial Director or PDMU head **cannot** legally issue NNC3.

---

## 2. Monthly Upward Reporting of Issued Notices: Management Action Report (Annex L)

While Reminder Letters and Notices of Non-Compliance (NNC1, NNC2, NNC3) are outward notices served directly on the Local Chief Executive, the DILG internal oversight framework requires a corresponding **monthly upward reporting mechanism** to monitor all non-compliant local governments across the province and region:

* **The Reporting Instrument (Annex L):** Formally titled **Management Action Report Summary Template** (with the official subtitle *List of Non-Compliant Local Government Units Issued with a Notice of Non Compliance*).
* **The Standard 5-Column Ledger:**
  1. `PROVINCE`: Geographic and administrative jurisdiction.
  2. `LOCAL GOVERNMENT UNIT`: Implementing LGU name.
  3. `PROGRAM / PROJECT TITLE`: Standardized project descriptor in the format `<Year / Program / Project Title>`.
  4. `ACTION TAKEN`: The specific notice issued (**NNC1**, **NNC2**, or **NNC3**) and its exact issuance date.
  5. `REMARKS`: Summary narrative detailing the factual basis of non-compliance.
* **The Monthly Reporting Cadence (Operations Manual pp. 17, 34):**
  * **25th of the Month:** DILG PO conducts monthly risk assessment across all ongoing and closeout-stage projects (p. 34, Step 7, Seq. 1).
  * **26th of the Month:** DILG PO accomplishes and transmits the Management Action Report to the DILG Regional Office (p. 17, Step 3, Seq. 3; p. 34, Step 7, Seq. 2).
  * **28th of the Month:** DILG Regional Office consolidates all provincial submissions and submits the regional Management Action Report to the **DILG Central Office (CO / OPDS)** (p. 17, Step 3, Seq. 4; p. 34, Step 7, Seq. 3).
* **Signatory Chain:** Prepared by DILG Regional Engineer (or PO project engineer), Approved by PDMU Chief, Noted by DILG Regional Director.

---

## 3. Policy vs. Implementation Reconciliation

### Document Titling and Template Codes
* **Official DILG Terminology:** In the official DILG manual, these notices are formally titled **Reminder Letter**, **Notice of Non-Compliance No. 1 (NNC1)**, **Notice of Non-Compliance No. 2 (NNC2)**, and **Notice of Non-Compliance No. 3 (NNC3)**.
* **Internal System Template Identifiers:** The application internally registers notice types as `annex_m` (NNC1), `annex_n` (NNC2), `annex_o` (NNC3), `annex_e` (Notice of Deficiency / Defects), `reminder_letter`, and `annex_l` (Management Action Report) within `VALID_NOTICE_TYPES` (`escalation_service.py`).

### Delineation of Three Separate Operational Tracks
To prevent procedural confusion, the Smart Assistant must keep the following three tracks strictly separated:
1. **Track 1: Technical Project Defects (Annex E / Aide Memoire):**
   * Discovered during physical field inspections or engineering desk evaluations.
   * Documented on **Annex E** (Notice of Defects/Deficiencies), which features an open `TIMELINES` column (*"prescribed and agreed timelines"*).
   * Deadlines are item-specific, calibrated by inspecting civil engineers according to the engineering severity of each defect (e.g., 7 calendar days to submit a cylinder test certificate, 15 days to recast defective concrete, 30 days to execute a revised catch-up plan).
   * Annex E does **not** mandate a blanket 15-working-day curing period on its face.
2. **Track 2: Routine Documentary Returns and DMS Corrections:**
   * Handled administratively during document intake review when submitted plans or bidding documents have minor omissions or unattached annexes.
   * Set to `workflow_status = "returned_for_revision"` while `compliance_status` strictly remains `"under_review"`.
   * Under the legal principles of RA 11032 (Ease of Doing Business), the processing turnaround clock is paused while the LGU prepares corrected files.
   * Routine digital returns do **not** trigger formal non-compliance notices or legal sanctions.
3. **Track 3: Formal Notice Escalation Chain (Reminder Letter $\rightarrow$ NNC1 $\rightarrow$ NNC2 $\rightarrow$ NNC3):**
   * Triggered when an LGU exhibits persistent non-responsiveness or fails to cure defects within agreed timelines.
   * Progresses through sequential 15-working-day administrative intervals: Reminder Letter $\rightarrow$ NNC1 (Provincial Director) $\rightarrow$ NNC2 (Provincial Director) $\rightarrow$ NNC3 (Regional Director).
   * Culminates in regional referral to Bantay Korapsyon and the Office of the Undersecretary for Local Government (OUSLG).

### Nature of the 15-Working-Day Escalation Deadline
* **Administrative Procedural Deadline (Not Statutory):** The 15-working-day window is an **administrative procedural deadline** established by internal DILG operational policy (PDMU Operations Manual Final, pp. 18, 20–21, 26, 36). It is not a "statutory" deadline created by an act of Congress (such as the 1-year warranty period under RA 9184 or the 3-month fund reversion under annual GAA Special Provisions). The word "statutory" does not appear in the Operations Manual for these escalation steps.
* **Operations Manual Baseline (pp. 18, 36):** In the procedural sequences of the Operations Manual:
  1. The Provincial Office issues a **Reminder Letter** following unacted inspection findings or milestone delays.
  2. If the LGU fails to act within **15 working days** of receipt of the Reminder Letter, **NNC1** is issued.
  3. If unacted within **15 working days** of NNC1 receipt, **NNC2** is issued.
  4. If unacted within **15 working days** of NNC2 receipt, **NNC3** is issued exclusively by the Regional Director.
* **Operations Manual Page 26 Textual Anomaly:** In the summary matrix on page 26 (Step 4, Item 7), the "Duties and Responsibilities" column specifies: *"Issue Notice of Non-Compliance No. 1 for any non-compliance with the Reminder letter"*, but the adjacent "Deadline/Duration" column states: *"15 working days upon receipt of the Notice of Deficiency"*. In contrast, pages 18, 20–21, and 36 consistently attach the 15-working-day trigger for NNC1 to receipt of the *Reminder Letter*.
* **System Implementation Reconciliation (`escalation_service.py`):** The application bridges this textual divergence through two concrete mechanisms:
  1. **Prerequisite Check (`missing_annex_e`):** The system requires an existing `annex_e` defect record before `annex_m` (NNC1) can be generated (`"An Annex E notice must exist before Annex M can be generated."`), ensuring formal legal notices are grounded in documented technical defects.
  2. **15-Working-Day Tolling Window (`FOLLOW_UP_WORKING_DAYS = 15`):** The system enforces a strict 15-working-day post-receipt tolling window between dispatched formal notices (`annex_m` $\rightarrow$ `annex_n` $\rightarrow$ `annex_o`), preventing premature escalation (`awaiting_annex_n_window`, `awaiting_annex_o_window`).
  3. **Notice Scope:** `annex_l` (Management Action Report) is recognized in `VALID_NOTICE_TYPES` for administrative tracking, but is not treated as a prerequisite or trigger for NNC escalation.

---

## 4. Current System Implementation
* **Escalation Dashboard (`/dashboard/escalation`):** Displays overdue requirements that have surpassed the 15-working-day threshold.
* **Notice Generation (`notice_service.py`):**
  * Auto-populates project title, LGU name, Mayor/LCE details, specific deficient requirements, and missed dates into official document templates.
  * Ensures NNC1 and NNC2 designate the Provincial Director as signatory.
  * Prepares NNC3 drafts formatted for transmittal to the Regional Director.
* **Guardrails & Confirmation:** Formal notice generation is an operational mutation requiring explicit confirmation in the Smart Assistant (Notice of Deficiency generation for SLA deadlines), and is restricted to authorized roles (`admin`, `staff`).
