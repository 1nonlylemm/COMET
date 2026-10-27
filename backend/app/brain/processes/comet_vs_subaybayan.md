---
topic: "{app_name} vs SubayBAYAN Functional Comparison and Boundaries"
category: "process"
roles:
  - "admin"
  - "staff"
  - "field_officer"
  - "system_admin"
source_type:
  - "operations_manual"
  - "staff_interview"
  - "system_implementation"
sources:
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
  - "others/reference_data/NEW/Subaybayan_Manual_Discovery.md"
authority: "Level 1, Level 2, and Level 3 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "subaybayan"
  - "comet"
  - "comparison"
  - "differences"
  - "monthly reporting"
  - "engineering review"
  - "25th of the month"
---

# {app_name} vs. SubayBAYAN: Architectural & Functional Comparison

A clear distinction between SubayBAYAN and {app_name} is essential to understanding the system's purpose. {app_name} does not duplicate or replace SubayBAYAN; rather, it solves the critical pre-implementation engineering review problem that SubayBAYAN does not address.

{app_name} creates or imports project records for provincial tracking. Project enrollment happens in SUBAYBAYAN. Creating or importing a record in {app_name} does not enroll a project in SUBAYBAYAN; any SUBAYBAYAN enrollment status refers to that separate national system.

---

## 1. Functional Comparison Matrix

| Dimension | SubayBAYAN (National System) | {app_name} (Provincial System) |
| :--- | :--- | :--- |
| **System Scope** | National public-facing transparency portal. | Internal provincial DILG Laguna PDMU workflow system. |
| **Governing Policy** | DILG MC No. 2024-134 (Omnibus SubayBAYAN Guidelines). | DILG MC No. 2023-063 & PDMU Operations Manual. |
| **Primary Users** | National, Regional, Provincial DILG focal persons, LGU encoders, General Public. | DILG Laguna PDMU Engineers, Admin Staff, Provincial Directors, Field Officers. |
| **Core Purpose** | Macro physical (%) and financial (%) progress reporting; geotagged photo monitoring. | Granular technical intake, engineering plan evaluation, deficiency tracking, regional handoff. |
| **Reporting Cycle** | Monthly reporting deadline (due by the **25th of every month**). | Event-driven, continuous tracking of working-day statutory deadlines. |
| **Document Granularity** | High-level summary attachments (SWA, Executive Brief, photo sets). | 20+ granular engineering documents (POW, DED, DUPA, Soil Tests, PhilGEPS postings, NTP, NOA). |
| **Review / Revision** | No document review or return-for-revision capability. | Full "Return for Revision" workflow with deficiency logs and curing timelines. |
| **Escalation Support** | Generates system alerts for unupdated monthly reports. | Full progressive statutory notice pipeline (Reminder -> NNC1 -> NNC2 -> NNC3). |

---

## 2. Why SubayBAYAN Cannot Track Document Review
* As established in the **SubayBAYAN Manual Discovery** (pp. 46–47 of the SubayBAYAN operational guide), SubayBAYAN is designed as an implementation monitoring and reporting database.
* It does not feature technical evaluation rubrics, multi-party engineering annotations, versioned revisions, or document-level rejection workflows.
* The system (formerly developed under the internal project name COMET) was developed specifically because PDMU engineers lacked an automated mechanism to track the 20+ pre-construction documents mandated by Annex B before civil works can be initiated.
