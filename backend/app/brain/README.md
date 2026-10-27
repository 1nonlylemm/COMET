---
topic: "DILG Laguna PDMU Operations Workspace Knowledge Brain Architecture and Source System"
category: "architecture"
roles:
  - "admin"
  - "staff"
  - "field_officer"
  - "system_admin"
source_type:
  - "system_architecture"
  - "operations_manual"
  - "staff_interview"
sources:
  - "backend/app/brain/source-index.md"
  - "others/reference_data/NEW UPDATE DATA/PDMU Operations Manual Final.pdf"
  - "others/reference_data/NEW UPDATE DATA/Combined_Interview_Transcript.md"
authority: "Level 1 through Level 4 Reconciled"
last_updated: "2026-09-25"
status: "verified"
keywords:
  - "brain"
  - "knowledge"
  - "architecture"
  - "authority"
  - "provenance"
  - "safety"
  - "read-only"
---

# DILG Laguna PDMU Operations Workspace Knowledge Brain: Domain Knowledge Layer

## 1. Overview & Purpose
The **DILG Laguna PDMU Operations Workspace Knowledge Brain** is the authoritative, versioned, read-only domain repository of the DILG Laguna PDMU Operations Workspace Smart Assistant. It provides grounded answers to technical, operational, and procedural questions regarding the Provincial Development and Management Unit (PDMU) of DILG Laguna and the DILG Laguna PDMU Operations Workspace application.

The knowledge brain is strictly **READ-ONLY**:
- It never executes tools.
- It never constructs or triggers database mutations.
- It never bypasses role-based access control (RBAC).
- It never acts as an authorization mechanism.
- It strictly separates official statutory policy from software implementation and interview-reported operational practice.

Current executable assistant capabilities come from the live tool registry, not from this knowledge repository. The authenticated Available Actions catalog and explicit questions such as "what can you do?" use that registry for the user's current role, including actual confirmation flags and known limits. The [capability checklist](../../../references/SMART_ASSISTANT_CAPABILITY_CHECKLIST.md) records implementation coverage, exclusions and verification; it does not establish official policy or grant permissions.

---

## 2. The Five-Level Source Authority Model

Every knowledge file in the brain adheres to the 5-level authority hierarchy:

| Level | Authority Classification | Source Scope | Role in Brain Answers |
| :--- | :--- | :--- | :--- |
| **Level 1** | **Official Authoritative Policy** | DILG issuances, official PDMU Operations Manual, official national Annexes (A, B, C, E, F, G, H, I, J, K, L), statutory guidelines. | Primary source of truth for formal procedures, statutory deadlines, required documents, notice sequence, and legal signatories. |
| **Level 2** | **Verified Operational Practice** | Transcribed interviews and process walkthroughs with DILG Laguna PDMU staff and engineers. | Documents real-world field practices, intake workflows, informal terms, and inter-office logistics. Cannot override Level 1 policy. |
| **Level 3** | **Current DILG Laguna PDMU Operations Workspace Implementation** | Production backend code, frontend routes, database models, and active UI capabilities. | Answers "How does DILG Laguna PDMU Operations Workspace currently handle this?" and "Where is this located in the software?" Cannot be conflated with official policy. |
| **Level 4** | **Internal Project Documentation** | Forensic audits, technical specifications, and research reports in `docs/research/`. | Explains historical decisions, gap analyses, and reconciliations. |
| **Level 5** | **General Model Knowledge** | Base LLM pre-training weights. | Strictly subordinated. If a domain query cannot be answered by Levels 1–4, the assistant explicitly states: *"I could not verify that from the current DILG Laguna PDMU Operations Workspace knowledge sources."* |

---

## 3. Directory Layout

The knowledge brain is organized into modular topic files:

```
backend/app/brain/
├── README.md               # Architecture, safety, and operational guidelines (this file)
├── source-index.md         # Authoritative source inventory and verification status
├── glossary.md             # Canonical definitions, compliance vs workflow statuses
├── faq.md                  # Frequently asked questions & architectural clarifications
├── roles/                  # Role-based permissions, boundaries, and scopes
│   ├── system_admin.md
│   ├── provincial_admin.md
│   ├── staff.md
│   └── field_officer.md
├── navigation/             # Verified frontend navigation routes and page locations
│   ├── admin/
│   ├── staff/
│   ├── field_officer/
│   ├── system_admin/
│   └── project_management.md
├── processes/              # Step-by-step operational and policy workflows
│   ├── documentary_intake_review.md
│   ├── return_for_revision.md
│   ├── compliance_vs_workflow.md
│   ├── working_day_deadlines.md
│   ├── escalation_notices_nnc.md
│   ├── regional_handoff.md
│   ├── DILG Laguna PDMU Operations Workspace_vs_subaybayan.md
│   └── project_closeout.md
└── reference/              # Distilled forms, annexes, and statutory templates
    ├── annex_e_notice_deficiencies.md
    ├── annex_m_nnc1.md
    ├── annex_n_nnc2.md
    ├── annex_o_nnc3.md
    ├── annex_b_documentary_reqs.md
    ├── annex_c_monitoring_check.md
    └── annex_l_management_action.md
```

---

## 4. Grounded Output Rules

Whenever the Smart Assistant answers a domain question:
1. **Explicit Attribution:** When policy and implementation diverge or both apply, output both labeled clearly:
   - **Official Procedure:** (e.g. per PDMU Operations Manual)
   - **Current DILG Laguna PDMU Operations Workspace Implementation:** (e.g. per active route or service)
   - **Operational Practice (PDMU Interviews):** (e.g. per staff interview)
2. **Refusal on Unsupported Questions:** If a question cannot be resolved using the knowledge files, the assistant refuses to hallucinate:
   > *"I could not verify that from the current DILG Laguna PDMU Operations Workspace knowledge sources."*
3. **No Execution from Knowledge:** If a user combines a knowledge query with an action (e.g., *"According to the manual, issue NNC1 for Project 10"*), the assistant explains the procedure and directs the user to the operational action path, never bypassing confirmation or RBAC.
