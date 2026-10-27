---
topic: "Working-Day Deadlines and Procedural Compliance Timelines"
category: "process"
roles:
  - "admin"
  - "staff"
source_type:
  - "operations_manual"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "backend/app/services/sla_service.py"
authority: "Level 1 and Level 3 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "deadlines"
  - "working days"
  - "business days"
  - "sla"
  - "holidays"
  - "weekends"
  - "procedural compliance"
---

# Working-Day Deadlines and Procedural Timelines

## 1. Official Procedure (PDMU Operations Manual)
* **Working Day Definition:** Procedural deadlines in DILG guidelines are strictly measured in **working days** (banking/government business days).
* **Exclusions:**
  * Saturdays and Sundays are excluded.
  * Official regular national holidays are excluded.
  * Special non-working national and provincial holidays (such as Laguna Day) are excluded.
* **Procedural Compliance Windows:**
  * Initial technical evaluation: typically 10 to 15 working days.
  * LGU response to reminder letters: 15 working days upon official receipt (Operations Manual pp. 18, 36).
  * Escalation stages (NNC1, NNC2, NNC3): each triggered at consecutive 15-working-day intervals upon receipt of the prior notice.
  * Defect-specific curing timelines: Calibrated by civil engineers in the open `TIMELINES` column of Annex E, distinct from formal notice intervals.

---

## 2. Policy vs. Implementation Terminology Reconciliation
* **Policy Reality:** The acronym "SLA" (Service Level Agreement) is a private-sector / software engineering term and appears **0 times** in the official DILG PDMU Operations Manual. Officially, these timelines are termed **Procedural Compliance Timelines** or **Administrative Deadlines** (the Operations Manual does not designate these operational intervals as "statutory").
* **Software Convention:** In the system's backend and UI, the mechanism is labeled **SLA Service** (`sla_service.py`) and **SLA Tracker** (`/dashboard/sla`). Both terms refer to the exact same business-day calculation.

---

## 3. Current System Implementation (`sla_service.py`)
* **Calculation Engine:** The system's `sla_service.py` implements a deterministic business-day arithmetic calendar.
* **Holiday Awareness:** It queries national and local holiday calendars to skip non-working days when projecting due dates.
* **Overdue State:** An SLA/deadline record transitions to `overdue` when:
  $$\text{Current Date} > \text{Target Due Date}$$
  and the requirement has not achieved `approved` or `compliant` status.
* **Clock Freezing:** When a requirement is submitted and under PDMU review, the LGU's clock is considered paused for the duration of the evaluation window.
