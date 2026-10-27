"""Canonical, scoped reference records available to the conversational planner."""
from app.services import lgu_service, program_service


def for_user(user):
    lgu_page = lgu_service.list_lgus(user_id=user.id, page=1, per_page=200)
    program_page = program_service.list_programs(page=1, per_page=100)
    programs = program_page['programs']
    program_rows = []
    for row in programs:
        entry = {key: row.get(key) for key in ('id', 'name', 'code', 'program_type', 'is_active')}
        entry['allowed_project_kinds'] = (['infrastructure'] if row.get('program_type') == 'infrastructure'
            else ['goods', 'vehicle', 'financial_assistance'] if row.get('program_type') == 'non_infrastructure'
            else ['infrastructure', 'goods', 'vehicle', 'financial_assistance'])
        entry['requires_project_kind'] = row.get('program_type') in ('hybrid', 'non_infrastructure')
        entry['cycles'] = []
        for cycle in program_service.list_program_cycles(row['id']):
            short_name = cycle['name']
            if short_name.startswith(row['name']):
                short_name = short_name[len(row['name']):].strip()
            entry['cycles'].append({'id': cycle['id'], 'name': short_name,
                                    'code': cycle['cycle_code'], 'year': cycle['fiscal_year'],
                                    'active': cycle['is_active']})
        program_rows.append(entry)
    return {
        'lgus': [{key: row.get(key) for key in ('id', 'name', 'municipality', 'province', 'cluster_id', 'is_active')}
                 for row in lgu_page['lgus']],
        'programs': program_rows,
        'clusters': [{key: row.get(key) for key in ('id', 'name')}
                     for row in lgu_service.list_clusters(user_id=user.id)],
        'truncated': lgu_page['total'] > 200 or program_page['total'] > 100,
    }
