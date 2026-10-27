---
topic: "Annex E - Notice of Defects and Deficiencies"
category: "reference"
roles:
  - "admin"
  - "staff"
  - "field_officer"
source_type:
  - "official_annex"
  - "operations_manual"
  - "system_implementation"
sources:
  - "others/reference_data/COMET Files, Forms, Annexes, and More!/Omnibus Guidelines Forms Annexes/Annex E - Notice of Deficiencies.pdf"
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "backend/app/models/workflow.py"
  - "docs/research/PDMU_DOCUMENT_REVIEW_RETURN_PROCESS_ANALYSIS.md"
authority: "Level 1 - Official Authoritative Policy"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "annex e"
  - "notice of deficiencies"
  - "notice of defects"
  - "defects"
  - "findings"
  - "corrective action"
  - "project management"
  - "quality of works"
  - "timeliness"
  - "15 working days"
  - "administrative escalation"
  - "escalation"
  - "nnc1"
  - "conforme"
---

# Annex E: Notice of Defects / Deficiencies

This reference guide details the authoritative legal mandate, exact form structure, deficiency matrix, and administrative escalation role of **DILG Annex E**, cross-referenced with the **PDMU Operations Manual Final (2024)** and {app_name}'s deficiency tracking architecture.

---

## 1. Document Identification & Operational Framework

* **Official Document Title:** Annex E — Notice of Defects / Deficiencies.
* **Governing Authority:** Level 1 (Official Authoritative Policy). Codified under DILG Memorandum Circular No. 2023-063 and PDMU Operations Manual Final (2024, p. 26 line 7, pp. 51–52).
* **Core Purpose:** Serves as the formal administrative instrument issued by DILG Provincial Development and Management Unit (PDMU) engineers to officially notify an implementing Local Government Unit (LGU) and its contractor of technical non-conformities, engineering defects, or documentary omissions discovered during field inspections or desk reviews.
* **Operational Force & Defect-Specific Timelines:** The Annex E form contains an open **TIMELINES** column where inspecting engineers prescribe case-specific completion timelines based on the nature and severity of the observed defect. The form does **not** prescribe a blanket 15-working-day window on its face. (In the Operations Manual pp. 18 and 36, the 15-working-day administrative procedural deadline formally attaches to the **Reminder Letter** and subsequent **Notices of Non-Compliance**, while page 26 contains a single textual anomaly referencing Notice of Deficiency in the deadline column for NNC1 next to Reminder letter in the duties column).

---

## 2. Exact Source Form Layout & Fields

Direct inspection of the official template (`Annex E - Notice of Deficiencies.pdf`) reveals the following exact layout and metadata fields:

### 2.1 Header & Metadata Blocks
* **Government Header:** `Republic of the Philippines`
* **Issuing Office:** `OFFICE OF THE MUNICIPAL MAYOR` / `DILG PROVINCIAL OFFICE — PDMU`
* **Official Document Title:** `NOTICE OF DEFECTS / DEFICIENCIES`
* **Form Metadata Fields:**
  * `FY`: Fiscal year of funding allocation.
  * `Date of Issuance`: Official transmittal date.
  * `Inspection Report No.`: Mandatory cross-reference connecting the notice to the specific QAAR tool, Aide Memoire, or documentary evaluation report that substantiated the findings.
* **Addressee Salutation:** `Dear Sir / Madame:`
* **Formal Opening Recital:**
  > *"Based on Inspection Report No. ___, the following defects and deficiencies have been noted:"*

---

### 2.2 The Four-Column Structured Deficiency Matrix

The core of Annex E is a structured four-column evaluation table:

```
┌─────────────────────────────────┬─────────────────────────────────┬───────────┬─────────┐
│     FINDINGS / OBSERVATIONS     │ RECOMMENDATIONS AND AGREEMENTS  │ TIMELINES │ REMARKS │
├─────────────────────────────────┼─────────────────────────────────┼───────────┼─────────┤
│ 1. PROJECT MANAGEMENT           │ [Required corrective action]    │ [Days]    │ [Notes] │
│ 2. QUALITY OF WORKS/WORKMANSHIP │ [Engineering rectification]     │ [Days]    │ [Notes] │
│ 3. TIMELINESS                   │ [Catch-up / recovery plan]      │ [Days]    │ [Notes] │
│ 4. SAFETY AND HEALTH RATING     │ [Safety compliance measure]     │ [Days]    │ [Notes] │
└─────────────────────────────────┴─────────────────────────────────┴───────────┴─────────┘
```

#### Detailed Breakdown of Columns:
1. **`FINDINGS / OBSERVATIONS`**:
   The source template explicitly categorizes inspection findings across four technical domains:
   * **`PROJECT MANAGEMENT`**: Administrative omissions, lack of approved variation orders, missing concrete pouring permits, absence of resident engineer/safety officer on site, or lack of required project billboards per COA Circular No. 2013-004.
   * **`QUALITY OF WORKS / WORKMANSHIP`**: Engineering non-conformities, substandard material test results (concrete compression failure, inadequate slump), honeycomb or voids in poured concrete, defective rebar spacing, uncompacted subgrade, or structural deviations from approved Detailed Engineering Designs (DED).
   * **`TIMELINESS`**: Negative physical slippage ($\ge 5\%$), milestone delays, overdue submission of monthly Statements of Work Accomplished (SWA), or failure of the contractor to mobilize manpower/equipment according to the approved CPM/PERT or S-Curve.
   * **`ASSESSMENT RATING FOR SAFETY AND HEALTH DURING THE COVID-19 PUBLIC HEALTH CRISIS`**: Occupational safety deficiencies, lack of personal protective equipment (PPE), uncertified first-aiders, or non-compliance with health guidelines.
2. **`RECOMMENDATIONS AND AGREEMENTS`**:
   Specific, actionable engineering directives and remediation measures agreed upon between PDMU engineers, the LGU Municipal Engineer, and the contractor (e.g., *"Chipping and recasting of defective concrete column at Station 0+120; submission of updated DUPA and revised POW"*).
3. **`TIMELINES`**:
   Prescribed calendar or working days allocated to complete the remediation (e.g., *"Within 7 calendar days upon receipt"*).
4. **`REMARKS`**:
   Statutory references, prior finding numbers, or verification conditions (e.g., *"Subject to joint re-inspection before subsequent progress billing approval"*).

---

### 2.3 Closing Legal Recital & Mandatory Signatories

* **Statutory Notice Recital:**
  The form concludes with an explicit legal mandate:
  > *"You are given prescribed and agreed timelines to commence the repair works and as well as the missing documents and complete them within the prescribed timelines above after receipt of this Notice."*
* **Signatory Blocks:**
  * **Issuing Authority:**
    `Very truly yours,`
    `[Signature over Printed Name of Inspecting Engineer / Provincial Director]`
  * **Conforme / Acknowledgment:**
    `Conforme:`
    `[Signature over Printed Name of Local Chief Executive / Municipal Engineer / Contractor Authorized Managing Officer]`
    *(Ensures legal receipt and starts the administrative curing clock).*

---

## 3. Administrative Escalation Role & Procedural Delineation

To avoid procedural ambiguity, the Smart Assistant must distinguish three separate operational tracks regarding deficiencies and deadlines:

1. **Track 1: Technical Project Defects (Annex E / Aide Memoire):**
   * Generated during on-site inspections or engineering evaluations.
   * Uses the open **TIMELINES** column on Annex E to set defect-specific curing schedules based on engineering severity (e.g. 7 days for material certifications, 15 days to recast defective structural elements).
   * Does **not** prescribe a blanket 15-working-day deadline on its face.
2. **Track 2: Routine Documentary Returns & DMS Corrections:**
   * Day-to-day administrative returns during documentary intake review.
   * LGU is notified of missing attachments or signatures; `workflow_status` is updated to `"returned_for_revision"` while `compliance_status` strictly remains `"under_review"`.
   * Under RA 11032, processing clocks are paused during client correction.
   * Routine digital returns do **not** initiate formal non-compliance notices or legal sanctions.
3. **Track 3: Formal Notice Escalation Chain (Reminder Letter $\rightarrow$ NNC1 $\rightarrow$ NNC2 $\rightarrow$ NNC3):**
   * Internal DILG administrative mechanism for unaddressed deficiencies or milestone delays.
   * Governed by **15-working-day administrative procedural intervals** (Operations Manual pp. 18, 20–21, 36).
   * Culminates in regional referral to Bantay Korapsyon lawyers and the Office of the Undersecretary for Local Government (OUSLG).

### Escalation Hierarchy & Page 26 Textual Anomaly

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           DILG Administrative Escalation Ladder (Manual p. 26)                    │
├───────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                   │
│  [ Step 1: Inspection Findings ] ─── PDMU issues Notice of Deficiencies (Annex E)                │
│                                      or Reminder Letter to LGU                                    │
│                                                                                                   │
│     ▼ (15 working days post-receipt of Reminder Letter / Notice of Deficiency)                    │
│                                                                                                   │
│  [ Step 2: Formal Notice No. 1 ] ─── Provincial Director (PD) issues                              │
│                                      Notice of Non-Compliance No. 1 (NNC1 / Annex M)              │
│                                                                                                   │
│     ▼ (15 working days post-receipt of NNC1 without resolution)                                    │
│                                                                                                   │
│  [ Step 3: Formal Notice No. 2 ] ─── Provincial Director (PD) issues                              │
│                                      Notice of Non-Compliance No. 2 (NNC2 / Annex N)              │
│                                                                                                   │
│     ▼ (15 working days post-receipt of NNC2 without resolution)                                    │
│                                                                                                   │
│  [ Step 4: Regional Escalation ] ─── Regional Director (RD / RO) issues                           │
│                                      Notice of Non-Compliance No. 3 (NNC3 / Annex O)              │
│                                      (Triggers Bantay Korapsyon referral & OUSLG endorsement)     │
│                                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

* **Administrative Procedural Nature (Not Statutory):** The 15-working-day interval is an administrative procedural deadline established by internal DILG operational policy (PDMU Operations Manual Final), not an act of Congress (statute).
* **The Page 26 Textual Anomaly:** In the Operations Manual summary matrix on page 26 (Step 4, Item 7), the "Duties and Responsibilities" column specifies: *"Issue Notice of Non-Compliance No. 1 for any non-compliance with the Reminder letter"*, but the adjacent "Deadline/Duration" column states: *"15 working days upon receipt of the Notice of Deficiency"*. In contrast, pages 18, 20–21, and 36 uniformly attach the 15-working-day trigger for NNC1 to the *Reminder Letter*.
* **System Implementation Reconciliation (`escalation_service.py`):** The software bridges this duality by requiring an existing `annex_e` defect record before `annex_m` (NNC1) can be generated (`missing_annex_e`), and tolling a strict 15-working-day post-receipt window (`FOLLOW_UP_WORKING_DAYS = 15`) between dispatched notices (`annex_m` $\rightarrow$ `annex_n` $\rightarrow$ `annex_o`).
* **Signatory Authority Boundary:**
  * NNC1 (Annex M) and NNC2 (Annex N) are issued and signed exclusively by the **Provincial Director (PD)**.
  * NNC3 (Annex O) is issued and signed exclusively by the **Regional Director (RD / RO)**. Provincial Directors have no legal authority to sign NNC3.

---

## 4. Current System Implementation in {app_name}

In {app_name}, the procedural mechanisms of Annex E are integrated directly into the document review and deficiency tracking workflow:

### 4.1 Canonical Deficiency Categories (`DEFICIENCY_CATEGORIES`)
When an evaluator returns a document in `{app_name}`, the findings are structured under the nine canonical database categories defined in `backend/app/models/workflow.py`:
1. `missing_attachment`: Missing annex checklists, bid sheets, or geotagged photos.
2. `missing_signature_notarization`: Unsigned engineering plans, unnotarized OSS or contract.
3. `cross_document_inconsistency`: Data conflicts between POW, ABC, ordinance, or contract.
4. `costing_dupa_defect`: Incomplete unit price analysis or inflated material rates.
5. `missing_statutory_clearance`: Missing RROW deed/waiver, geohazard clearance, or ECC/CNC.
6. `program_specific_non_conformity`: APMV engine limits, unapproved variation orders.
7. `financial_reconciliation_defect`: SORD discrepancies, missing treasury reversion proof.
8. `scan_quality_defect`: Truncated, missing, or illegible pages.
9. `other_documented_defect`: Miscellaneous technical defects.

### 4.2 Canonical Resolution States (`DEFICIENCY_RESOLUTION_STATES`)
Every deficiency recorded under Annex E is tracked through three discrete lifecycle states:
* **`open`**: Deficiency recorded by reviewer; awaiting LGU corrective resubmission.
* **`resolved`**: Verified by reviewer upon evaluating corrected upload (`v2`, `v3`).
* **`waived`**: Formally excused by authorized administrator with documented justification.

### 4.3 The Critical Status Invariant
> **CRITICAL RULE:** Issuing deficiency findings under Annex E or executing **Return for Revision** in {app_name} transitions `workflow_status` to `"returned_for_revision"`, but `compliance_status` **strictly remains `"under_review"`**. It does **NOT** make the requirement `"non_compliant"`.
>
> A requirement transitions to `"non_compliant"` **only** when formal escalation windows (15 working days post-NNC1/NNC2) expire without compliance or when formal non-compliance is adjudicated by the Provincial or Regional Director.

---

## 5. Cross-References

* Documentary requirements catalog: [Annex B Reference](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_b_documentary_reqs.md)
* Evaluation checklist & review cadence: [Annex C Reference](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_c_monitoring_check.md)
* Return for revision process guide: [Return for Revision Guide](file:///c:/Users/marka/Projects/COMET/backend/app/brain/processes/return_for_revision.md)
* Notice of Non-Compliance No. 1: [Annex M Reference](file:///c:/Users/marka/Projects/COMET/backend/app/brain/reference/annex_m_nnc1.md)
* Status taxonomy: [Compliance vs. Workflow Status](file:///c:/Users/marka/Projects/COMET/backend/app/brain/processes/compliance_vs_workflow.md)
