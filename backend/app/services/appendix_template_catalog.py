"""Catalog and metadata registry for Omnibus Guidelines Appendices 1-19.

Provides canonical descriptors, file paths, and project-kind mappings for all
19 Non-Infrastructure Monitoring and Beneficiary Evidence templates.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from flask import current_app

VALID_APPENDIX_REFERENCES = tuple(f"Appendix {i}" for i in range(1, 20))

APPENDIX_CATALOG: List[Dict[str, Any]] = [
    {
        "appendix_number": 1,
        "appendix_reference": "Appendix 1",
        "code": "MT-1",
        "title": "Summary of Distribution for Learning Materials",
        "filename": "Appendix-1-MT-1-Summary-of-Distribution-for-Learning-Materials-8.10.22.xlsx",
        "applicable_kinds": ["goods"],
        "sub_type": "learning_materials",
        "record_target": "non_infra_monitoring",
        "description": "Summary of learning materials distributed, unit costs, and inventory balances.",
    },
    {
        "appendix_number": 2,
        "appendix_reference": "Appendix 2",
        "code": "MT-1A",
        "title": "Distribution Receipt for Learning Materials",
        "filename": "Appendix-2-MT1A-Distribution-Receipt-for-Learning-Materials-8.10.22.xlsx",
        "applicable_kinds": ["goods"],
        "sub_type": "learning_materials",
        "record_target": "beneficiary_evidence",
        "description": "Institutional distribution receipt signed by the supply officer of the receiving school/institution.",
    },
    {
        "appendix_number": 3,
        "appendix_reference": "Appendix 3",
        "code": "MT-1B",
        "title": "Report on Beneficiaries Provided with Learning Materials",
        "filename": "Appendix-3-MT1B-Report-on-Beneficiaries-provided-with-Learning-Materials-8.10.22.xlsx",
        "applicable_kinds": ["goods"],
        "sub_type": "learning_materials",
        "record_target": "beneficiary_evidence",
        "description": "Detailed student beneficiary roster including age, sex, grade level, and school ID.",
    },
    {
        "appendix_number": 4,
        "appendix_reference": "Appendix 4",
        "code": "MT-2",
        "title": "Summary of Financial Assistance",
        "filename": "Appendix-4-MT2-Summary-of-Financial-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "summary",
        "record_target": "non_infra_monitoring",
        "description": "Consolidated financial assistance summary across medical, burial, transport, food, educational sub-types.",
    },
    {
        "appendix_number": 5,
        "appendix_reference": "Appendix 5",
        "code": "MT-2A",
        "title": "Report on Beneficiaries Provided with Financial Assistance - Medical",
        "filename": "Appendix-5-MT2A-Report-on-Beneficiaries-Provided-with-Financial-Assistance-Medical-Financial-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "medical",
        "record_target": "beneficiary_evidence",
        "description": "Beneficiary roster for medical financial assistance with patient details, payment mode, and hospital records.",
    },
    {
        "appendix_number": 6,
        "appendix_reference": "Appendix 6",
        "code": "MT-2B",
        "title": "Report on Beneficiaries Provided with Financial Assistance - Burial",
        "filename": "Appendix-6-MT2B-Report-on-Beneficiaries-Provided-with-Financial-Assistance-Burial-Financial-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "burial",
        "record_target": "beneficiary_evidence",
        "description": "Beneficiary roster for burial financial assistance with deceased records and claimant details.",
    },
    {
        "appendix_number": 7,
        "appendix_reference": "Appendix 7",
        "code": "MT-2C",
        "title": "Report on Beneficiaries Provided with Financial Assistance - Transportation",
        "filename": "Appendix-7-MT2C-Report-on-Beneficiaries-Provided-with-Financial-Assistance-Transportation-Financial-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "transportation",
        "record_target": "beneficiary_evidence",
        "description": "Beneficiary roster for transportation financial assistance with travel purpose and ticket details.",
    },
    {
        "appendix_number": 8,
        "appendix_reference": "Appendix 8",
        "code": "MT-2D",
        "title": "Report on Beneficiaries Provided with Financial Assistance - Food",
        "filename": "Appendix-8-MT2D-Report-on-Beneficiaries-Provided-with-Financial-Assistance-Food-Financial-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "food",
        "record_target": "beneficiary_evidence",
        "description": "Beneficiary roster for food assistance and residential care facility (CRCF) support.",
    },
    {
        "appendix_number": 9,
        "appendix_reference": "Appendix 9",
        "code": "MT-2E",
        "title": "Report on Beneficiaries Provided with Financial Assistance - Cash Assistance for Other Support Services",
        "filename": "Appendix-9-MT2E-Report-on-Beneficiaries-Provided-with-Financial-Assistance-Cash-Assistance-for-Other-Support-Services-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "cash_assistance_other",
        "record_target": "beneficiary_evidence",
        "description": "Beneficiary roster for other support service cash assistance grants.",
    },
    {
        "appendix_number": 10,
        "appendix_reference": "Appendix 10",
        "code": "MT-2F",
        "title": "Report on Beneficiaries Provided with Financial Assistance - Educational",
        "filename": "Appendix-10-MT2F-Report-on-Beneficiaries-Provided-with-Financial-Assistance-Educational-Financial-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "educational",
        "record_target": "beneficiary_evidence",
        "description": "Student beneficiary roster for educational financial assistance stipends and tuition support.",
    },
    {
        "appendix_number": 11,
        "appendix_reference": "Appendix 11",
        "code": "MT-3",
        "title": "Summary of Livelihood and Employment Assistance",
        "filename": "Appendix-11-MT3-Summary-of-Livelihood-and-Employment-Assistance-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance", "goods"],
        "sub_type": "livelihood_summary",
        "record_target": "non_infra_monitoring",
        "description": "Summary report covering Cash for Work, Individual/Group Livelihood, and Skills Training.",
    },
    {
        "appendix_number": 12,
        "appendix_reference": "Appendix 12",
        "code": "MT-3A",
        "title": "Report on Beneficiaries Provided with Livelihood and Employment Assistance - Cash for Work",
        "filename": "Appendix-12-MT3A-Report-on-Beneficiaries-Provided-with-Livelihood-and-Employment-Assistance-Cash-for-Work-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance"],
        "sub_type": "cash_for_work",
        "record_target": "beneficiary_evidence",
        "description": "Worker roster, days worked, daily rates, and total wage disbursements under Cash for Work.",
    },
    {
        "appendix_number": 13,
        "appendix_reference": "Appendix 13",
        "code": "MT-3B",
        "title": "Report on Beneficiaries Provided with Livelihood and Employment Assistance - Individual Livelihood",
        "filename": "Appendix-13-MT3B-Report-on-Beneficiaries-Provided-with-Livelihood-and-Employment-Assistance-Livelihood-for-Individual-8.10.22.xlsx",
        "applicable_kinds": ["goods", "financial_assistance"],
        "sub_type": "livelihood_individual",
        "record_target": "beneficiary_evidence",
        "description": "Individual beneficiary receipt of livelihood starter kits, seeds, fingerlings, or livestock.",
    },
    {
        "appendix_number": 14,
        "appendix_reference": "Appendix 14",
        "code": "MT-3C",
        "title": "Report on Beneficiaries Provided with Livelihood and Employment Assistance - Organized Group",
        "filename": "Appendix-14-MT3C-Report-on-Beneficiaries-Provided-with-Livelihood-and-Employment-Assistance-Livelihood-for-Organized-Group-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance", "goods"],
        "sub_type": "livelihood_group",
        "record_target": "beneficiary_evidence",
        "description": "Cooperative and organized association capital assistance, business plans, and bank records.",
    },
    {
        "appendix_number": 15,
        "appendix_reference": "Appendix 15",
        "code": "MT-3D",
        "title": "Report on Beneficiaries Provided with Livelihood and Employment Assistance - Skills Training",
        "filename": "Appendix-15-MT3D-Report-on-Beneficiaries-Provided-with-Livelihood-and-Employment-Assistance-Skills-Training-8.10.22.xlsx",
        "applicable_kinds": ["financial_assistance", "goods"],
        "sub_type": "skills_training",
        "record_target": "beneficiary_evidence",
        "description": "Trainee attendance, skills qualification, training provider, and actual training expenses.",
    },
    {
        "appendix_number": 16,
        "appendix_reference": "Appendix 16",
        "code": "MT-4",
        "title": "Summary of Distribution for Medical Devices (Equipment/Supplies)",
        "filename": "Appendix-16-MT4-Summary-of-Distribution-for-Medical-Devices-8.10.22.xlsx",
        "applicable_kinds": ["goods"],
        "sub_type": "medical_devices",
        "record_target": "non_infra_monitoring",
        "description": "Summary of medical equipment, hospital beds, and clinical diagnostic device distributions.",
    },
    {
        "appendix_number": 17,
        "appendix_reference": "Appendix 17",
        "code": "MT-4A",
        "title": "Distribution Receipt of Medical Devices",
        "filename": "Appendix-17-MT4A-Distribution-Receipt-of-Medical-Devices-8.10.22.xlsx",
        "applicable_kinds": ["goods"],
        "sub_type": "medical_devices",
        "record_target": "beneficiary_evidence",
        "description": "Health facility and hospital property custodian acknowledgment receipt for delivered medical devices.",
    },
    {
        "appendix_number": 18,
        "appendix_reference": "Appendix 18",
        "code": "DRR-1",
        "title": "Rescue Vehicle / Equipment Monitoring Form",
        "filename": "Appendix-18-DRR-Vehicle-Monitoring-Form-1-8.10.22.xlsx",
        "applicable_kinds": ["motor_vehicles", "vehicle", "goods"],
        "sub_type": "rescue_vehicle",
        "record_target": "non_infra_monitoring",
        "description": "Monitoring checklist for disaster risk reduction rescue vehicles and specialized equipment.",
    },
    {
        "appendix_number": 19,
        "appendix_reference": "Appendix 19",
        "code": "APMV",
        "title": "Authority to Purchase Motor Vehicle (APMV) Endorsement Checklist",
        "filename": "Appendix-19-APMV-Endorsement-Checklist-Form-8.10.22.xlsx",
        "applicable_kinds": ["motor_vehicles", "vehicle"],
        "sub_type": "apmv_checklist",
        "record_target": "non_infra_monitoring",
        "description": "DILG/DBM APMV pre-procurement checklist verifying engine specs, inventory, and LCE request.",
    },
]

for item in APPENDIX_CATALOG:
    item["applicable_project_kinds"] = item["applicable_kinds"]

_BY_NUMBER = {item["appendix_number"]: item for item in APPENDIX_CATALOG}
_BY_REFERENCE = {item["appendix_reference"].lower(): item for item in APPENDIX_CATALOG}
_BY_REFERENCE.update({f"appendix_{item['appendix_number']}": item for item in APPENDIX_CATALOG})


def get_appendices_dir() -> Path:
    """Returns absolute path to the stored appendix reference templates directory."""
    if current_app:
        candidate = Path(current_app.root_path).parent / "seed_assets" / "reference_templates" / "appendices"
        if candidate.exists():
            return candidate
    candidate2 = Path(__file__).resolve().parents[2] / "seed_assets" / "reference_templates" / "appendices"
    if candidate2.exists():
        return candidate2
    return Path("/app/seed_assets/reference_templates/appendices")


def get_appendix_by_number(appendix_number: int) -> Optional[Dict[str, Any]]:
    try:
        return _BY_NUMBER.get(int(appendix_number))
    except (ValueError, TypeError):
        return None


def get_appendix_by_reference(reference: str) -> Optional[Dict[str, Any]]:
    if not reference:
        return None
    cleaned = reference.strip().lower()
    return _BY_REFERENCE.get(cleaned)


def list_appendix_templates(project_kind: Optional[str] = None) -> List[Dict[str, Any]]:
    if not project_kind:
        return list(APPENDIX_CATALOG)
    kind_lower = project_kind.strip().lower()
    return [item for item in APPENDIX_CATALOG if kind_lower in item["applicable_kinds"]]


def get_appendix_file_path(appendix_number: int) -> Optional[Path]:
    item = get_appendix_by_number(appendix_number)
    if not item:
        return None
    target_path = get_appendices_dir() / item["filename"]
    if target_path.exists():
        return target_path
    return None
