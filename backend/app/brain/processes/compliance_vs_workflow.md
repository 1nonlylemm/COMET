---
topic: "Compliance Status vs Workflow Status Distinction"
category: "process"
roles:
  - "admin"
  - "staff"
  - "system_admin"
source_type:
  - "system_implementation"
  - "operations_manual"
sources:
  - "backend/app/models/project.py"
  - "backend/app/models/workflow.py"
  - "docs/research/PHASE_SLA_NOTICES_FOLLOWUP_AUDIT.md"
  - "docs/research/PDMU_DOCUMENT_REVIEW_RETURN_PROCESS_ANALYSIS.md"
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
authority: "Level 1 and Level 3 Reconciled"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "compliance status"
  - "workflow status"
  - "semantics"
  - "under_review"
  - "under_verification"
  - "resubmitted"
  - "non_compliant"
  - "returned_for_revision"
  - "tolling"
  - "ra 11032"
---

# Compliance Status vs. Workflow Status Distinction

Understanding the dual-state model of project requirements is vital for legal data integrity, operational reporting, and COA audit defense in {app_name}.

---

## 1. Dual-State Architecture

Every `ProjectRequirement` record maintains two independent status enumerations that must never be conflated:

```
┌─────────────────────────────────────────────────────────────┐
│                     ProjectRequirement                      │
├──────────────────────────────┬──────────────────────────────┤
│       compliance_status      │        workflow_status       │
│  (Legal / Statutory State)   │   (Document Movement Stage)  │
├──────────────────────────────┼──────────────────────────────┤
│  • pending                   │  • draft                     │
│  • under_review              │  • submitted                 │
│  • compliant                 │  • under_verification        │
│  • non_compliant             │  • staff_approved            │
│  • waived                    │  • pending_provincial_       │
│                              │    approval                  │
│                              │  • approved                  │
│                              │  • returned_for_revision     │
│                              │  • resubmitted               │
└──────────────────────────────┴──────────────────────────────┘
```

---

## 2. The Core Non-Compliance Invariant

> **INVARIANT:** Returning a requirement for revision does **NEVER** automatically change its compliance status to `non_compliant`.

* **Operational Reality:** In day-to-day operations, returning a document with deficiency comments is a standard, collaborative step between PDMU engineers and municipal engineers. Deficiencies (e.g., missing unit price breakdowns, unsealed engineering blueprints, lack of notarization) are routine findings identified during technical scrutiny.
* **Statutory Meaning:** An LGU is legally within its rights to cure identified deficiencies during the allowed compliance window. Labeling a project `non_compliant` merely because a draft submission required revisions would misrepresent local performance, distort regional dashboards, and trigger unwarranted administrative penalties.
* **When does a requirement become `non_compliant`?**
  A requirement transitions to `non_compliant` **only** when:
  1. The LGU fails to submit or correct documents after formal escalation notice windows (15 working days post-NNC1, followed by NNC2) have expired without compliance.
  2. The Provincial Director or Regional Office formally adjudicates non-compliance following procedural exhaustion.
  3. An authorized administrator manually confirms non-compliance following administrative escalation.

---

## 3. Detailed Enumeration Definitions

### Compliance Status (`status` / `compliance_status`)
Reflects the formal compliance condition of the requirement under DILG Guidelines, national issuances, and database constraint `ck_project_req_status`:
1. **`pending`**: Initial baseline state. The requirement is mandatory for the project, but the LGU has not yet submitted the initial dossier, or the submission awaits formal review triage.
2. **`under_review`**: The submission is physically or digitally in the custody of PDMU technical staff. Active engineering review, verification, or deficiency curing is underway.
3. **`compliant`**: The document strictly meets all engineering, administrative, and legal standards stipulated in Annex B/C, verified by civil engineers and authorized staff.
4. **`non_compliant`**: Administrative escalation windows have expired without deficiency resolution, formal non-compliance has been adjudicated, or formal letters (NNC1/NNC2/NNC3) have lapsed unheeded.
5. **`waived`**: The requirement has been formally exempted by authorized authorities due to specific project modalities (e.g., Right-of-Way waiver when civil works are situated wholly on public property), supported by mandatory written justification.

### Workflow Status (`workflow_status`)
Reflects the tactical document custody and review stage within {app_name} under database constraint `ck_project_req_workflow_status`:
1. **`draft`**: Created internally as a placeholder or encoded by staff, not yet submitted for formal evaluation.
2. **`submitted`**: Transmitted by the LGU (via DMS or physical transmittal) and logged by staff; awaiting engineering evaluation.
3. **`under_verification`**: PDMU civil engineer is actively evaluating plans, POW, DED, DUPA, or bidding documents against technical checklists and external registries.
4. **`staff_approved`**: Technical evaluator / engineer has verified engineering parameters and completeness, endorsing the document for provincial sign-off.
5. **`pending_provincial_approval`**: Held for final administrative sign-off or executive endorsement by the Provincial Director.
6. **`approved`**: Reviewer or director determined the document satisfies all technical requirements, clearing it for regional packaging.
7. **`returned_for_revision`**: Reviewer identified specific technical omissions or errors and returned custody to the LGU with formal deficiency remarks.
8. **`resubmitted`**: The LGU has uploaded an updated version (`v2`, `v3`) addressing previous findings, queued for re-verification.

---

## 4. Legal vs. Procedural Consequences Matrix

| Dimension | `returned_for_revision` (Workflow Action) | `non_compliant` (Compliance Adjudication) |
| :--- | :--- | :--- |
| **Administrative Nature** | Operational routing; technical correction cycle. | Formal administrative default under DILG/DBM rules. |
| **Review Clock Impact** | Review clock legally suspended (tolled under RA 11032 principle); LGU cure clock begins. *(Operational principle; no automated DB timer)*. | Procedural compliance timeline expired; formal notices triggered. |
| **Escalation Path** | Normal engineering feedback; no formal notice issued. | Triggers sequential Reminder Letter $\rightarrow$ NNC1 $\rightarrow$ NNC2 $\rightarrow$ NNC3. |
| **Dashboard Representation** | Displayed in Yellow / Info as "Awaiting LGU Revision". | Displayed in Red / Danger as "Overdue / Non-Compliant". |
| **SubayBAYAN Equivalent** | Corresponds to SubayBAYAN status **`For Revision`**. | Flagged as critical implementation lag / risk. |
| **Curing Mechanism** | LGU uploads revised document version (`v2`). | Requires formal justification and executive acceptance by Provincial/Regional Director. |

---

## 5. Status Transition Lifecycle Matrix

| Scenario / Trigger | Action Taken | Resulting `workflow_status` | Resulting `compliance_status` | Rationale & Legal Authority |
| :--- | :--- | :--- | :--- | :--- |
| Project enrollment | System creates requirements profile | `draft` | `pending` | Mandatory documentary checklist initialized from Annex B. |
| LGU transmits file | Staff receives via DMS & logs file | `submitted` | `under_review` | Custody received; internal evaluation queue opened. |
| Engineer begins review | Reviewer opens engineering checklist | `under_verification` | `under_review` | Active technical scrutiny of DED, POW, or DUPA. |
| Deficiencies found | Reviewer logs remarks & returns | `returned_for_revision` | `under_review` | LGU is actively correcting; legal status remains under review (RA 11032). |
| LGU resubmits file | LGU transmits revised `v2` file | `resubmitted` | `under_review` | Custody returned to PDMU; delta verification queued. |
| Staff clears technicals | Engineer recommends approval | `staff_approved` | `under_review` | Technical verification passed; awaiting provincial sign-off. |
| Provincial sign-off | Provincial Director endorses / approves | `approved` | `compliant` | Technical & regulatory criteria fully cleared under Annex B/C. |
| Escalation deadline lapses | Escalation notices exhausted (15 days post-NNC2) | `returned_for_revision` or `draft` | `non_compliant` | Procedural non-responsiveness adjudicated under DILG Operations Manual p. 18. |
| Exemption granted | Administrator records written waiver | *(retains workflow status)* | `waived` | Specific project modality formally exempts requirement. |
