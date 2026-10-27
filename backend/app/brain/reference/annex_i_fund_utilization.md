---
topic: "Annex I - Report on Fund Utilization and Status of Program/Project Implementation"
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
  - "others/reference_data/COMET Files, Forms, Annexes, and More!/Omnibus Guidelines Forms Annexes/Annex-I-Report-on-Fund-Utilization-and-Status-of-Implementation-8.10.22.docx"
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "backend/app/models/project.py"
authority: "Level 1 - Official Authoritative Policy"
last_updated: "2026-10-18"
status: "verified"
keywords:
  - "annex i"
  - "fund utilization"
  - "status of implementation"
  - "quarterly report"
  - "local finance committee"
  - "lfc"
  - "lbo"
  - "lpdc"
  - "nadai"
  - "contracted"
  - "disbursed"
  - "full disclosure policy"
---

# Annex I: Report on Fund Utilization and Status of Program/Project Implementation

This reference guide provides the complete, authoritative structure, 12-column tracking matrix, codified instructions, Local Finance Committee (LFC) signatory protocol, and transparency mandates codified in **DILG Annex I (dated August 10, 2022)**, cross-referenced with the **PDMU Operations Manual Final (2024)** and {app_name}'s monitoring framework.

---

## 1. Regulatory Identification & Legal Framework

* **Official Document Title:** Annex I — Local Government Support Fund: Utilization and Status of Program / Project Implementation (For the Quarter Ended _______________).
* **Governing Authority:** Level 1 (Official Authoritative Policy). Prescribed under DILG LGSF Omnibus Guidelines (MC No. 2023-063), DBM Local Budget Circulars (LBC 131, 142, 146, 155), and annual General Appropriations Act (GAA) reporting mandates.
* **Core Purpose:** The official quarterly reporting instrument that LGUs must prepare, certify, and submit to monitor macro-financial inflows, contractual commitments, actual disbursements, and physical milestones across all locally funded projects.
* **Scope & Applicability:** Applies to all projects funded under the Local Government Support Fund (FALGU, SBDP, SGLG-IF, DRRAP, AC, GEF).
* **Distinction between Annex H and Annex I:**
  * **Annex H (Report of Disbursements & Liquidations / SORD):** Project-specific, check-level financial liquidation and disbursement register prepared by the Accountant and Treasurer for individual project closeout.
  * **Annex I (Fund Utilization and Implementation Status):** Portfolio-wide quarterly progress and utilization matrix prepared by the Local Finance Committee (LFC) covering all LGSF allocations received by the LGU.

---

## 2. The 12-Column Program / Project Implementation Matrix

Annex I organizes project and financial data into a comprehensive 12-column tabular layout:

| Col | Field Header | Official Definition / Data Content | Verification Standard |
| :---: | :--- | :--- | :--- |
| **1** | **Fund Source** | The specific national appropriation and General Appropriations Act (GAA) fiscal year from which funding was charged (e.g., *FY 2023 LGSF-FALGU*). | Cross-referenced with the applicable DBM Local Budget Circular (LBC). |
| **2** | **Date of NADAI Issued** | Date of the Notice of Authority to Debit Account Issued (NADAI) released by BTr. | Validates the fund crediting date and 15-day SubayBAYAN enrollment clock. |
| **3** | **Type of Program / Project** | Functional project classification per LBC enumeration (e.g., Local Access Road, Potable Water System, Evacuation Center, Motor Vehicle). | Ensures consistency with national program menus and eligible expenditure categories. |
| **4** | **Name / Title of Program / Project** | Formal project title conforming to Sanggunian Resolution and approved POW. | Must match project title in DILG and DBM portals. |
| **5** | **Specific Location** | Exact site location (Sitio, Barangay, Municipality/City). | Verified against GIS coordinates and field inspection logs. |
| **6** | **Mechanism / Mode of Implementation** | Execution modality: `By Contract` (commercial contractor via RA 9184) or `By Administration` (in-house LGU engineering force). | Checks compliance with approved mode and procurement guidelines. |
| **7** | **Estimated Number of Beneficiaries** | Quantified target population benefiting from project completion (households, farmers, residents). | Verified against initial project profile and Sanggunian resolution. |
| **8** | **Amount: Received** | Exact cash allocation credited to the LGU depository bank account as indicated in the NADAI. | Cross-checked with Bureau of the Treasury (BTr) remittance advisories. |
| **9** | **Amount: Contracted** | Total commitments arising from official contracts binding the LGU to immediate or eventual payment (e.g., signed Contract Price). | Reconciled with Notice of Award (NOA) and contract agreements. |
| **10** | **Amount: Disbursed / Utilized** | Total cumulative sum actually paid out by the LGU as of the end of the reporting quarter. | Reconciled with checks released in Annex H / SORD. |
| **11** | **Estimated Period of Completion** | Target completion date specified in `Month and Year` (e.g., *December 2024*). | Compared against original contract duration and approved time extensions. |
| **12** | **Remarks on Program / Project Status** | Percentage of physical completion or delivery of service, plus qualitative notes on implementation issues or suspension orders. | Must reconcile with monthly SubayBAYAN updates and verified SWA percentages. |

---

## 3. Codified Instructions in Annex I

The original source document explicitly articulates five fundamental instructions governing compilation:

1. **LFC Mandate & Cross-Departmental Coordination:**
   > *"The report shall be prepared by the LFC, in coordination with the other local officials concerned (e.g., local accountant on the allotment, obligation and disbursement; local engineer on the status of infrastructure projects, as may be applicable)."*
2. **Fund Source Identification:**
   > *"The fund source pertains to the type of fund and pertinent General Appropriations Act from which the implementation of the program / project was charged."*
3. **Consistency with Budget Circulars:**
   > *"The type of program/project shall be identified consistent with the program/projects enumerated under the applicable LBC."*
4. **Three-Tier Financial Definitions:**
   * **Amount Received:** *"Refers to the amount transferred by Bureau of the Treasury to the LGUs as indicated in the NADAI."*
   * **Amount Contracted Out:** *"Refers to the total commitments by the LGU arising from official acts binding the LGU to the immediate or eventual payment of a sum of money."*
   * **Disbursement:** *"Refers to the total amount paid by the LGU as of reporting period."*
5. **Physical Progress Standard:**
   > *"The status of programs / projects refers to the percentage of physical completion or delivery of service as of reporting period."*

---

## 4. Local Finance Committee (LFC) Governance & Signatories

Annex I establishes collective institutional responsibility through the Local Finance Committee (LFC), attested by the Local Chief Executive:

```
Certified correct by:
The Local Finance Committee                                Attested by:

______________________________________                      ______________________________
        Local Budget Officer                             Local Chief Executive (Mayor/Governor)

______________________________________
           Local Treasurer

______________________________________
Local Planning and Development Coordinator
```

### Institutional Responsibilities:
* **Local Budget Officer (LBO):** Certifies budget allotments, appropriations, and obligation status.
* **Local Treasurer (LT):** Certifies actual cash receipts from BTr (NADAI) and cumulative check disbursements.
* **Local Planning and Development Coordinator (LPDC):** Certifies alignment with the Local Development Plan (LDP) and monitors project milestones.
* **Local Chief Executive (LCE):** Attests to the truthfulness, accuracy, and official submission of the quarterly report.

---

## 5. Submission Cadence, SubayBAYAN Sync, & Full Disclosure

* **Quarterly Reporting Calendar (DBM LBC No. 155 Section 3.7.1):** Submitted to DILG Provincial Office and DBM Regional Office within fifteen (15) calendar days following the end of each fiscal quarter:
  * 1st Quarter: Ending March 31 (Due on or before April 15)
  * 2nd Quarter: Ending June 30 (Due on or before July 15)
  * 3rd Quarter: Ending September 30 (Due on or before October 15)
  * 4th Quarter: Ending December 31 (Due on or before January 15)
* **Full Disclosure Policy (FDP) Mandate:** Under statutory GAA rules and DILG FDP guidelines, the accomplished Annex I must be:
  1. Posted on the official LGU website / portal.
  2. Displayed in at least three (3) conspicuous public places (e.g., municipal hall bulletin board, public market, civic center).
* **Synchronization with SubayBAYAN:** PDMU civil engineers cross-check the physical percentage and disbursement figures reported in Annex I with the monthly progress updates recorded in **SubayBAYAN** (due on the 25th of every month under MC No. 2024-134). Any material discrepancy triggers an inquiry or field inspection.

---

## 6. System Implementation in {app_name}

In {app_name}'s architecture:
* **Financial Tracking:** Informs project financial analytics and disbursement progress metrics.
* **Intake & Verification:** When LGUs submit quarterly utilization reports, PDMU staff verify that `Amount Received` matches the recorded NADAI, `Amount Contracted` reflects the active contract sum, and `Disbursed` tallies with verified SORD entries.
* **Cross-Module Linkage:** Serves as a macro validation gate against the Project Closeout Console (`/dashboard/completion`), ensuring that no project is closed out with unresolved utilization or liquidation discrepancies.
