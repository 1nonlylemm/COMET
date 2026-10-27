---
topic: "Notice of Non-Compliance No. 1 (NNC1 / Annex M)"
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
  - "nnc1"
  - "annex m"
  - "notice of non-compliance 1"
  - "escalation"
  - "provincial director"
---

# Notice of Non-Compliance No. 1 (NNC1 / Annex M)

## 1. Statutory Identification & Authority
* **Official Document Title:** Notice of Non-Compliance No. 1.
* **System Template Convention:** Annex M (internal system code).
* **Authority Level:** Level 1 (PDMU Operations Manual, pp. 18, 20, 26, 51).
* **Authorized Signatory:** **Provincial Director (PD)** of DILG Laguna.

---

## 2. Triggering Conditions & Sequence
* **Trigger:** Issued when an LGU fails to act upon or cure deficiencies identified in a prior Reminder Letter or Annex E within **15 working days** of receipt.
* **Target Audience:** Addressed directly to the Local Chief Executive (Municipal/City Mayor).
* **Content:**
  * Recital of initial submission dates and prior reminder letters.
  * Explicit enumeration of outstanding requirements or unrectified deficiencies.
  * Formal warning that failure to comply within an additional **15 working days** will result in the issuance of Notice of Non-Compliance No. 2.

---

## 3. System Implementation
* Auto-generated via `notice_service.py` from overdue SLA tracker records.
* Dispatched with draft status requiring Provincial Admin confirmation (`/dashboard/escalation`).
