---
topic: "Notice of Non-Compliance No. 2 (NNC2 / Annex N)"
category: "reference"
roles:
  - "admin"
  - "staff"
source_type:
  - "operations_manual"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "backend/app/services/notice_generation_service.py"
authority: "Level 1 and Level 3 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "nnc2"
  - "annex n"
  - "notice of non-compliance 2"
  - "escalation"
  - "provincial director"
---

# Notice of Non-Compliance No. 2 (NNC2 / Annex N)

## 1. Statutory Identification & Authority
* **Official Document Title:** Notice of Non-Compliance No. 2.
* **System Template Convention:** Annex N (internal system code).
* **Authority Level:** Level 1 (PDMU Operations Manual, pp. 18, 20, 26, 51).
* **Authorized Signatory:** **Provincial Director (PD)** of DILG Laguna.

---

## 2. Triggering Conditions & Sequence
* **Trigger:** Issued when the LGU fails to submit or rectify requirements within **15 working days** following official receipt of Notice of Non-Compliance No. 1 (NNC1).
* **Target Audience:** Addressed to the Local Chief Executive (Mayor), copied to the Provincial Governor, Municipal Vice Mayor, and Sangguniang Bayan Presiding Officer.
* **Content:**
  * Chronological documentation of prior reminders and NNC1.
  * Formal reiteration of delinquent items.
  * Clear warning that continued failure to comply within **15 working days** will escalate the matter directly to the DILG Regional Director for issuance of Notice of Non-Compliance No. 3 and referral to the Bantay Korapsyon legal team.

---

## 3. System Implementation
* Generated via `notice_service.py` when an SLA enters secondary overdue escalation.
* Requires Provincial Admin authorization prior to transmittal.
