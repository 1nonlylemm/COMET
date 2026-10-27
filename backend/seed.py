import sys
import os
import re
import unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import (
    User, PasswordReset,
    LguCluster, LguProfile, UserScopeAssignment,
    Program, ProgramPhase, Requirement,
    Project, ProjectRequirement,
    BeneficiaryCategory,
)
from seed_reference_templates import seed_reference_templates
from app.utils.seed_safety import validate_seed_database_safety
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash


def _email_slug(value):
    normalized = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '', normalized.lower())


def seed():
    app = create_app('development')
    with app.app_context():
        validate_seed_database_safety(app, operation='seed', is_destructive=True)
        db.drop_all()
        db.create_all()

        print("Seeding users...")
        sysadmin = User(
            email='sysadmin@dilgpdmu.tech',
            password_hash=generate_password_hash('sysadmin123'),
            first_name='System',
            last_name='Administrator',
            role='system_admin',
            is_active=True,
        )
        admin = User(
            email='padmin@dilgpdmu.tech',
            password_hash=generate_password_hash('admin123'),
            first_name='Provincial',
            last_name='Admin',
            role='admin',
            is_active=True,
        )
        staff1 = User(
            email='staff1@dilgpdmu.tech',
            password_hash=generate_password_hash('staff123'),
            first_name='Juan',
            last_name='Dela Cruz',
            role='staff',
            is_active=True,
        )
        staff2 = User(
            email='staff2@dilgpdmu.tech',
            password_hash=generate_password_hash('staff123'),
            first_name='Ana',
            last_name='Reyes',
            role='staff',
            is_active=True,
        )
        field1 = User(
            email='field1@dilgpdmu.tech',
            password_hash=generate_password_hash('field123'),
            first_name='Elena',
            last_name='Mercado',
            role='field_officer',
            is_active=True,
        )
        db.session.add_all([sysadmin, admin, staff1, staff2, field1])
        db.session.flush()

        print("Seeding LGU clusters...")
        cluster_north = LguCluster(name='Cluster 1 - North', description='Northern Laguna LGUs')
        cluster_central = LguCluster(name='Cluster 2 - Central', description='Central Laguna LGUs')
        cluster_south = LguCluster(name='Cluster 3 - South', description='Southern Laguna LGUs')
        db.session.add_all([cluster_north, cluster_central, cluster_south])
        db.session.flush()

        print("Seeding LGU profiles...")
        cluster_ids = {
            'north': cluster_north.id,
            'central': cluster_central.id,
            'south': cluster_south.id,
        }
        # PSGC Laguna province master list: 24 municipalities and 6 component cities.
        # Cluster assignment is a local demo grouping and should be updated if DILG Laguna
        # provides an official cluster roster.
        lgus_data = [
            ('Municipality of Alaminos', 'Alaminos', 'south'),
            ('Municipality of Bay', 'Bay', 'central'),
            ('City of Biñan', 'Biñan City', 'north'),
            ('City of Cabuyao', 'Cabuyao City', 'north'),
            ('City of Calamba', 'Calamba City', 'north'),
            ('Municipality of Calauan', 'Calauan', 'central'),
            ('Municipality of Cavinti', 'Cavinti', 'central'),
            ('Municipality of Famy', 'Famy', 'north'),
            ('Municipality of Kalayaan', 'Kalayaan', 'central'),
            ('Municipality of Liliw', 'Liliw', 'south'),
            ('Municipality of Los Baños', 'Los Baños', 'central'),
            ('Municipality of Luisiana', 'Luisiana', 'south'),
            ('Municipality of Lumban', 'Lumban', 'central'),
            ('Municipality of Mabitac', 'Mabitac', 'north'),
            ('Municipality of Magdalena', 'Magdalena', 'south'),
            ('Municipality of Majayjay', 'Majayjay', 'south'),
            ('Municipality of Nagcarlan', 'Nagcarlan', 'south'),
            ('Municipality of Paete', 'Paete', 'north'),
            ('Municipality of Pagsanjan', 'Pagsanjan', 'central'),
            ('Municipality of Pakil', 'Pakil', 'north'),
            ('Municipality of Pangil', 'Pangil', 'north'),
            ('Municipality of Pila', 'Pila', 'central'),
            ('Municipality of Rizal', 'Rizal', 'south'),
            ('City of San Pablo', 'San Pablo City', 'south'),
            ('City of San Pedro', 'San Pedro City', 'north'),
            ('Municipality of Santa Cruz', 'Santa Cruz', 'central'),
            ('Municipality of Santa Maria', 'Santa Maria', 'north'),
            ('City of Santa Rosa', 'Santa Rosa City', 'north'),
            ('Municipality of Siniloan', 'Siniloan', 'north'),
            ('Municipality of Victoria', 'Victoria', 'central'),
        ]
        lgu_objects = []
        for name, mun, cluster_key in lgus_data:
            lgu = LguProfile(
                name=name,
                municipality=mun,
                province='Laguna',
                cluster_id=cluster_ids[cluster_key],
                contact_email=f'lgu_{_email_slug(mun)}@laguna.gov.ph',
                is_active=True,
            )
            lgu_objects.append(lgu)
        db.session.add_all(lgu_objects)
        db.session.flush()

        lgu_by_municipality = {lgu.municipality: lgu for lgu in lgu_objects}

        print("Seeding user scope assignments...")
        db.session.add_all([
            UserScopeAssignment(user_id=staff1.id, scope_type='cluster', cluster_id=cluster_north.id, is_active=True),
            UserScopeAssignment(user_id=staff2.id, scope_type='cluster', cluster_id=cluster_central.id, is_active=True),
            UserScopeAssignment(user_id=staff2.id, scope_type='cluster', cluster_id=cluster_south.id, is_active=True),
            UserScopeAssignment(user_id=field1.id, scope_type='lgu', lgu_id=lgu_by_municipality['Biñan City'].id, is_active=True),
            UserScopeAssignment(user_id=field1.id, scope_type='lgu', lgu_id=lgu_by_municipality['Santa Rosa City'].id, is_active=True),
        ])

        print("Seeding programs...")
        lgsf = Program(
            name='Local Government Support Fund - Financial Assistance to Local Government Units (LGSF-FALGU)',
            code='LGSF-FALGU',
            description='National government financial assistance for priority local infrastructure and development projects that improve LGU service delivery.',
            program_type='hybrid',
            funding_agency='DILG Central Office',
            is_active=True,
        )
        sbdp = Program(
            name='Local Government Support Fund - Support to Barangay Development Program (LGSF-SBDP)',
            code='LGSF-SBDP',
            description='Funding support for development projects in insurgency-cleared and conflict-affected barangays, including roads, schools, water systems, and health stations.',
            program_type='infrastructure',
            funding_agency='DILG Central Office',
            is_active=True,
        )
        rbme = Program(
            name='Results Based Monitoring and Evaluation of LGUs Infrastructure Projects (RBME-RLIP)',
            code='RBME-RLIP',
            description='Results-based monitoring and evaluation of LGU infrastructure projects, including locally funded projects and 20 percent development fund works.',
            program_type='infrastructure',
            funding_agency='DILG',
            is_active=True,
        )
        g3p = Program(
            name='Green Green Green Program (G3P)',
            code='G3P',
            description='Support for LGU development, improvement, and rehabilitation of parks, plazas, green corridors, and other public open spaces.',
            program_type='infrastructure',
            funding_agency='DILG / DHSUD',
            is_active=True,
        )
        gef = Program(
            name='Growth Equity Fund (GEF)',
            code='GEF',
            description='Support for disadvantaged LGUs, especially 4th to 6th income class LGUs, to bridge fiscal gaps and fund priority infrastructure, solar power, and health facility projects.',
            program_type='infrastructure',
            funding_agency='DILG Central Office',
            is_active=True,
        )
        safpb = Program(
            name='Support and Assistance Fund to Participatory Budgeting (SAFPB)',
            code='SAFPB',
            description='Participatory budgeting support implemented with CSO participation for basic services, with emphasis on water supply, sanitation, hygiene, and ending open defecation.',
            program_type='infrastructure',
            funding_agency='DILG',
            is_active=True,
        )
        db.session.add_all([lgsf, sbdp, rbme, g3p, gef, safpb])
        db.session.flush()

        print("Seeding program phases...")
        phases_data = [
            (lgsf.id, 'Pre-Implementation', 1, 'Document triage and approval before project starts'),
            (lgsf.id, 'Implementation', 2, 'Active project monitoring and field validation'),
            (lgsf.id, 'Completion', 3, 'Final audit and vault'),
            (sbdp.id, 'Pre-Implementation', 1, 'Document triage and approval before project starts'),
            (sbdp.id, 'Implementation', 2, 'Active project monitoring and field validation'),
            (sbdp.id, 'Completion', 3, 'Final audit and vault'),
            (rbme.id, 'Pre-Implementation', 1, 'LGU infrastructure inventory and monitoring plan validation'),
            (rbme.id, 'Implementation', 2, 'Results-based field validation and performance reporting'),
            (rbme.id, 'Completion', 3, 'Monitoring closeout and management action tracking'),
            (g3p.id, 'Pre-Implementation', 1, 'Open-space design, work plan, and site readiness review'),
            (g3p.id, 'Implementation', 2, 'Greening and public open-space implementation monitoring'),
            (g3p.id, 'Completion', 3, 'Turnover, maintenance, and sustainability documentation'),
            (gef.id, 'Pre-Implementation', 1, 'Priority project eligibility and documentary review'),
            (gef.id, 'Implementation', 2, 'Priority project monitoring and field validation'),
            (gef.id, 'Completion', 3, 'Completion, liquidation, and closeout review'),
            (safpb.id, 'Pre-Implementation', 1, 'CSO participation and water/sanitation project preparation'),
            (safpb.id, 'Implementation', 2, 'Water, sanitation, and hygiene implementation monitoring'),
            (safpb.id, 'Completion', 3, 'Turnover, service-readiness, and sanitation closeout'),
        ]
        phase_objects = []
        for pid, name, order, desc in phases_data:
            phase_objects.append(ProgramPhase(program_id=pid, name=name, phase_order=order, description=desc))
        db.session.add_all(phase_objects)
        db.session.flush()

        print("Seeding requirements (Annex C items)...")
        def phase_for(program, phase_name):
            return next(p for p in phase_objects if p.program_id == program.id and p.name == phase_name)

        lgsf_pre = phase_for(lgsf, 'Pre-Implementation')
        lgsf_impl = phase_for(lgsf, 'Implementation')
        lgsf_comp = phase_for(lgsf, 'Completion')
        sbdp_pre = phase_for(sbdp, 'Pre-Implementation')
        sbdp_impl = phase_for(sbdp, 'Implementation')
        sbdp_comp = phase_for(sbdp, 'Completion')
        rbme_pre = phase_for(rbme, 'Pre-Implementation')
        rbme_impl = phase_for(rbme, 'Implementation')
        rbme_comp = phase_for(rbme, 'Completion')
        g3p_pre = phase_for(g3p, 'Pre-Implementation')
        g3p_impl = phase_for(g3p, 'Implementation')
        g3p_comp = phase_for(g3p, 'Completion')
        gef_pre = phase_for(gef, 'Pre-Implementation')
        gef_impl = phase_for(gef, 'Implementation')
        gef_comp = phase_for(gef, 'Completion')
        safpb_pre = phase_for(safpb, 'Pre-Implementation')
        safpb_impl = phase_for(safpb, 'Implementation')
        safpb_comp = phase_for(safpb, 'Completion')

        requirements_data = [
            (lgsf_pre.id, 'Draft Detailed Engineering Design (DED)', 'document', 'Annex C', 1, True, None),
            (lgsf_pre.id, 'Draft Project Proposal', 'document', 'Annex C', 2, True, None),
            (lgsf_pre.id, 'Program of Works (POW)', 'document', 'Annex C', 3, True, None),
            (lgsf_pre.id, 'Sangguniang Bayan Resolution', 'resolution', 'Annex C', 4, True, None),
            (lgsf_pre.id, 'Omnibus Sworn Statement', 'document', 'Annex C', 5, True, None),
            (lgsf_pre.id, 'PhilGEPS Bidding Posting', 'document', 'Annex C', 6, True, None),
            (lgsf_pre.id, 'Notice of Award (NOA)', 'document', 'Annex C', 7, True, None),
            (lgsf_pre.id, 'Notice to Proceed (NTP)', 'document', 'NTP', 8, True, None),
            (lgsf_impl.id, 'Quality Assurance Assessment Report (Annex D)', 'inspection', 'Annex D', 1, True, None),
            (lgsf_impl.id, 'Monthly Progress Report', 'document', 'Monthly', 2, True, None),
            (lgsf_comp.id, 'Certificate of Completion', 'certificate', 'Annex J', 1, True, None),
            (lgsf_comp.id, 'Final Statement of Work Accomplished (SWA)', 'document', 'Annex J', 2, True, None),
            (lgsf_comp.id, 'Annex J - Project Completion Report', 'document', 'Annex J', 3, True, None),
            (sbdp_pre.id, 'Draft Detailed Engineering Design (DED)', 'document', 'Annex C', 1, True, None),
            (sbdp_pre.id, 'Barangay Development Council Resolution', 'resolution', 'Annex C', 2, True, None),
            (sbdp_pre.id, 'Sangguniang Bayan Resolution', 'resolution', 'Annex C', 3, True, None),
            (sbdp_impl.id, 'QAAR (Annex D)', 'inspection', 'Annex D', 1, True, None),
            (sbdp_comp.id, 'Certificate of Completion', 'certificate', 'Annex J', 1, True, None),
            (sbdp_comp.id, 'Annex J - Project Completion Report', 'document', 'Annex J', 2, True, None),
            (rbme_pre.id, 'LGU Infrastructure Project Inventory / 20 Percent Development Fund List', 'document', 'Inventory', 1, True, None),
            (rbme_pre.id, 'RBME Monitoring Plan and Baseline Indicators', 'document', 'RBME Plan', 2, True, None),
            (rbme_impl.id, 'Quality Assurance Assessment Report (Annex D)', 'inspection', 'Annex D', 1, True, None),
            (rbme_impl.id, 'Monthly Validation and Management Action Update', 'document', 'MAR', 2, True, None),
            (rbme_comp.id, 'RBME Closeout and Lessons-Learned Summary', 'document', 'Closeout', 1, True, None),
            (g3p_pre.id, 'Site Development / Landscape or Architectural Plan', 'engineering', 'Site Plan', 1, True, None),
            (g3p_pre.id, 'DHSUD Orientation / Design Workshop Record', 'document', 'DHSUD', 2, False, None),
            (g3p_impl.id, 'Quality Assurance Assessment Report (Annex D)', 'inspection', 'Annex D', 1, True, None),
            (g3p_impl.id, 'Monthly Greening Progress Report', 'document', 'Monthly', 2, True, None),
            (g3p_comp.id, 'Maintenance and Sustainability Plan', 'document', 'Maintenance', 1, True, None),
            (gef_pre.id, 'Income-Class / Eligibility Certification', 'certificate', 'Eligibility', 1, True, None),
            (gef_pre.id, 'Priority Project Proposal and Work Plan', 'document', 'Proposal', 2, True, None),
            (gef_impl.id, 'GEF Physical and Financial Accomplishment Report', 'document', 'Monthly', 1, True, None),
            (gef_comp.id, 'Certificate of Completion', 'certificate', 'COC', 1, True, None),
            (safpb_pre.id, 'CSO Participation and Prioritization Record', 'document', 'CSO Record', 1, True, None),
            (safpb_pre.id, 'Water Supply / Sanitation Project Design and Work Plan', 'engineering', 'WASH Work Plan', 2, True, None),
            (safpb_impl.id, 'WASH Implementation Progress Report', 'document', 'Monthly', 1, True, None),
            (safpb_impl.id, 'Community Consultation / Hygiene Promotion Evidence', 'document', 'CSO/WASH', 2, False, None),
            (safpb_comp.id, 'Water and Sanitation Service Turnover Certificate', 'certificate', 'Turnover', 1, True, None),
            (safpb_comp.id, 'Post-Implementation Sanitation and O&M Plan', 'document', 'O&M', 2, True, None),
        ]
        req_objects = []
        for rd in requirements_data:
            if len(rd) == 8:
                req_objects.append(Requirement(
                    phase_id=rd[0], name=rd[1], requirement_type=rd[2],
                    annex_reference=rd[3], sort_order=rd[4], is_mandatory=rd[5],
                    has_sla=rd[6], sla_days=rd[7],
                ))
            else:
                req_objects.append(Requirement(
                    phase_id=rd[0], name=rd[1], requirement_type=rd[2],
                    annex_reference=rd[3], sort_order=rd[4], is_mandatory=rd[5],
                ))
        db.session.add_all(req_objects)

        print("Seeding beneficiary categories (MT1-MT4)...")
        categories = [
            BeneficiaryCategory(code='MT1A', name='Distribution Receipt for Learning Materials/ Educational Assistance', mt_level='MT1'),
            BeneficiaryCategory(code='MT1B', name='Distribution Receipt for Educational Assistance - Tertiary', mt_level='MT1'),
            BeneficiaryCategory(code='MT2A', name='Distribution Receipt for Medical Assistance', mt_level='MT2'),
            BeneficiaryCategory(code='MT2B', name='Distribution Receipt for Hospitalization Assistance', mt_level='MT2'),
            BeneficiaryCategory(code='MT3A', name='Distribution Receipt for Burial Assistance', mt_level='MT3'),
            BeneficiaryCategory(code='MT3B', name='Distribution Receipt for Transportation Assistance', mt_level='MT3'),
            BeneficiaryCategory(code='MT4A', name='Distribution Receipt for Food Assistance', mt_level='MT4'),
            BeneficiaryCategory(code='MT4B', name='Distribution Receipt for Skills Training / Livelihood Assistance', mt_level='MT4'),
        ]
        db.session.add_all(categories)

        seeded_templates = seed_reference_templates()
        from app.services.holiday_seed_data import seed_verified_holidays
        seeded_holidays = seed_verified_holidays(db.session)

        print("Seed data committed successfully!")
        print(f"  Statutory Holidays: {seeded_holidays}")
        print(f"  Users: 4")
        print(f"  LGU Clusters: 3")
        print(f"  LGU Profiles: {len(lgu_objects)}")
        print(f"  User Scope Assignments: {UserScopeAssignment.query.count()}")
        print(f"  Programs: 6")
        print(f"  Program Phases: {len(phase_objects)}")
        print(f"  Requirements: {len(req_objects)}")
        print(f"  Beneficiary Categories: {len(categories)}")
        print("  Standard Reference Library templates:")
        for item in seeded_templates:
            print(f"    {item['template_type']}: {item['file_name']}")


if __name__ == '__main__':
    seed()
