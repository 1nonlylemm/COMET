import re

from app.extensions import db
from app.models import LguProfile, Program, ProgramCycle, Project, ProjectRequirement
from app.services import search_query_service


MAX_SEARCH_CANDIDATES = 500


PROJECT_FIELD_WEIGHTS = {
    'project_name': 6.0,
    'source_project_code': 5.0,
    'source_row_key': 3.0,
    'source_sheet_name': 2.0,
    'lgu_name': 5.0,
    'municipality': 5.0,
    'province': 2.0,
    'program_name': 3.0,
    'program_code': 4.0,
    'program_type': 2.0,
    'cycle_name': 2.0,
    'cycle_code': 3.0,
    'fiscal_year': 3.0,
    'current_phase': 3.0,
    'overall_status': 3.0,
    'notes': 1.0,
    'custom_fields': 1.0,
}

REQUIREMENT_FIELD_WEIGHTS = {
    'requirement_name': 6.0,
    'requirement_type': 3.0,
    'annex_reference': 4.0,
    'phase_name': 3.0,
    'status': 3.0,
    'project_name': 5.0,
    'source_project_code': 4.0,
    'lgu_name': 5.0,
    'municipality': 5.0,
    'province': 2.0,
    'program_name': 3.0,
    'program_code': 4.0,
    'fiscal_year': 3.0,
    'custom_fields': 1.0,
}


def search_projects(query, search, page=1, per_page=20, serialize=None):
    parsed = search_query_service.parse_search_query(search)
    if parsed.is_empty:
        pagination = query.order_by(Project.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return _pagination_result('projects', pagination, serialize)

    candidates = (
        apply_project_prefilter(query, parsed)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .limit(MAX_SEARCH_CANDIDATES)
        .all()
    )
    ranked = _rank_items(candidates, parsed, project_search_fields, PROJECT_FIELD_WEIGHTS)
    ranked_page = _paginate_ranked(ranked, page, per_page)
    return {
        'projects': [_serialize_ranked(item, serialize) for item in ranked_page['items']],
        'total': ranked_page['total'],
        'page': ranked_page['page'],
        'per_page': ranked_page['per_page'],
        'pages': ranked_page['pages'],
    }


def search_requirements(query, search, page=1, per_page=20, serialize=None, order_by=None):
    parsed = search_query_service.parse_search_query(search)
    if parsed.is_empty:
        ordered_query = query.order_by(*order_by) if order_by else query
        pagination = ordered_query.paginate(page=page, per_page=per_page, error_out=False)
        return _pagination_result('items', pagination, serialize)

    candidates = apply_requirement_prefilter(query, parsed)
    if order_by:
        candidates = candidates.order_by(*order_by)
    candidates = candidates.limit(MAX_SEARCH_CANDIDATES).all()

    ranked = _rank_items(candidates, parsed, requirement_search_fields, REQUIREMENT_FIELD_WEIGHTS)
    ranked_page = _paginate_ranked(ranked, page, per_page)
    return {
        'items': [_serialize_ranked(item, serialize) for item in ranked_page['items']],
        'total': ranked_page['total'],
        'page': ranked_page['page'],
        'per_page': ranked_page['per_page'],
        'pages': ranked_page['pages'],
    }


def apply_project_prefilter(query, parsed):
    code = search_query_service.project_code_query(parsed)
    conditions = []
    # Keep a structured identifier whole, but search every supported field:
    # its shape alone cannot distinguish a project code from a cycle code.
    for token in ((code,) if code else parsed.sql_tokens):
        like = f'%{_escape_like(token)}%'
        conditions.extend([
            Project.project_name.ilike(like),
            Project.source_project_code.ilike(like),
            Project.source_row_key.ilike(like),
            Project.source_sheet_name.ilike(like),
            Project.current_phase.ilike(like),
            Project.overall_status.ilike(like),
            Project.notes.ilike(like),
            db.cast(Project.fiscal_year, db.String).ilike(like),
            Project.lgu.has(db.or_(
                LguProfile.name.ilike(like),
                LguProfile.municipality.ilike(like),
                LguProfile.province.ilike(like),
            )),
            Project.program.has(db.or_(
                Program.name.ilike(like),
                Program.code.ilike(like),
                Program.program_type.ilike(like),
                Program.funding_agency.ilike(like),
            )),
            Project.program_cycle.has(db.or_(
                ProgramCycle.name.ilike(like),
                ProgramCycle.cycle_code.ilike(like),
                db.cast(ProgramCycle.fiscal_year, db.String).ilike(like),
            )),
        ])

    if code:
        return query.filter(db.or_(*conditions))

    for status in parsed.status_terms:
        conditions.append(Project.overall_status == status)
    for phase in parsed.phase_terms:
        conditions.append(Project.current_phase == phase)
    for fiscal_year in parsed.fiscal_years:
        conditions.append(Project.fiscal_year == fiscal_year)

    if not conditions:
        return query
    return query.filter(db.or_(*conditions))


def apply_requirement_prefilter(query, parsed):
    code = search_query_service.project_code_query(parsed)
    conditions = []
    for token in ((code,) if code else parsed.sql_tokens):
        like = f'%{_escape_like(token)}%'
        conditions.extend([
            ProjectRequirement.requirement_name.ilike(like),
            ProjectRequirement.requirement_type.ilike(like),
            ProjectRequirement.annex_reference.ilike(like),
            ProjectRequirement.phase_name.ilike(like),
            ProjectRequirement.status.ilike(like),
            ProjectRequirement.project.has(_project_match_clause(like)),
        ])

    if code:
        return query.filter(db.or_(*conditions))

    for status in parsed.status_terms:
        conditions.append(ProjectRequirement.status == status)
        conditions.append(ProjectRequirement.project.has(Project.overall_status == status))
    for phase in parsed.phase_terms:
        conditions.append(ProjectRequirement.phase_name.ilike(f'%{phase.replace("_", " ")}%'))
        conditions.append(ProjectRequirement.project.has(Project.current_phase == phase))
    for fiscal_year in parsed.fiscal_years:
        conditions.append(ProjectRequirement.project.has(Project.fiscal_year == fiscal_year))

    if not conditions:
        return query
    return query.filter(db.or_(*conditions))


def project_search_fields(project):
    lgu = project.lgu
    program = project.program
    cycle = project.program_cycle
    return {
        'project_name': project.project_name,
        'source_project_code': project.source_project_code,
        'source_row_key': project.source_row_key,
        'source_sheet_name': project.source_sheet_name,
        'lgu_name': lgu.name if lgu else None,
        'municipality': lgu.municipality if lgu else None,
        'province': lgu.province if lgu else None,
        'program_name': program.name if program else None,
        'program_code': program.code if program else None,
        'program_type': program.program_type if program else None,
        'cycle_name': cycle.name if cycle else None,
        'cycle_code': cycle.cycle_code if cycle else None,
        'fiscal_year': project.fiscal_year,
        'current_phase': project.current_phase,
        'overall_status': project.overall_status,
        'notes': project.notes,
        'custom_fields': project.custom_fields or {},
    }


def requirement_search_fields(requirement):
    project = requirement.project
    project_fields = project_search_fields(project) if project else {}
    return {
        'requirement_name': requirement.requirement_name,
        'requirement_type': requirement.requirement_type,
        'annex_reference': requirement.annex_reference,
        'phase_name': requirement.phase_name,
        'status': requirement.status,
        'custom_fields': requirement.custom_fields or {},
        **{
            key: project_fields.get(key)
            for key in (
                'project_name',
                'source_project_code',
                'lgu_name',
                'municipality',
                'province',
                'program_name',
                'program_code',
                'cycle_name',
                'cycle_code',
                'fiscal_year',
            )
        },
    }


def _project_match_clause(like):
    return db.or_(
        Project.project_name.ilike(like),
        Project.source_project_code.ilike(like),
        Project.source_row_key.ilike(like),
        Project.source_sheet_name.ilike(like),
        Project.current_phase.ilike(like),
        Project.overall_status.ilike(like),
        db.cast(Project.fiscal_year, db.String).ilike(like),
        Project.lgu.has(db.or_(
            LguProfile.name.ilike(like),
            LguProfile.municipality.ilike(like),
            LguProfile.province.ilike(like),
        )),
        Project.program.has(db.or_(
            Program.name.ilike(like),
            Program.code.ilike(like),
            Program.program_type.ilike(like),
            Program.funding_agency.ilike(like),
        )),
        Project.program_cycle.has(db.or_(
            ProgramCycle.name.ilike(like),
            ProgramCycle.cycle_code.ilike(like),
        )),
    )


def _rank_items(items, parsed, field_builder, weights):
    ranked = []
    for item in items:
        score, matched_fields = score_fields(field_builder(item), parsed, weights)
        if score > 0:
            ranked.append({
                'item': item,
                'score': score,
                'matched_fields': matched_fields,
            })
    ranked.sort(key=lambda row: (-row['score'], -_updated_at(row['item']), -getattr(row['item'], 'id', 0)))
    return ranked


def score_fields(fields, parsed, weights):
    code = search_query_service.project_code_query(parsed)
    if code:
        # Do not let fragments of a missing identifier match unrelated rows.
        # Accept the whole identifier in any searchable field, including cycles.
        pattern = re.compile(r'(?<![\w/-])' + re.escape(code) + r'(?![\w/-])', re.I)
        matched_fields = [key for key, value in fields.items()
                          if pattern.search(' '.join(search_query_service.flatten_values(value)))]
        return (100.0, sorted(matched_fields)) if matched_fields else (0.0, [])
    normalized_fields = {
        key: search_query_service.normalize_text(' '.join(search_query_service.flatten_values(value)))
        for key, value in fields.items()
    }
    full_text = ' '.join(value for value in normalized_fields.values() if value)

    score = 0.0
    matched_fields = set()
    if parsed.normalized and len(parsed.normalized) >= 3:
        for field, text in normalized_fields.items():
            if text and parsed.normalized in text:
                score += 12.0 * weights.get(field, 1.0)
                matched_fields.add(field)

    token_matches = 0
    for token in parsed.tokens:
        variants = search_query_service.expand_token(token)
        best_score = 0.0
        best_field = None
        for field, text in normalized_fields.items():
            if not text:
                continue
            weight = weights.get(field, 1.0)
            words = set(text.split())
            for variant in variants:
                if not variant:
                    continue
                if variant in words:
                    field_score = 2.0 * weight
                elif variant in text:
                    field_score = 1.1 * weight
                else:
                    continue
                if field_score > best_score:
                    best_score = field_score
                    best_field = field
        if best_score:
            token_matches += 1
            score += best_score
            matched_fields.add(best_field)

    if parsed.tokens:
        coverage = token_matches / len(parsed.tokens)
        if coverage < _minimum_coverage(parsed.tokens):
            return 0.0, []
        score += coverage * 10.0

    for status in parsed.status_terms:
        if status in full_text:
            score += 8.0
            matched_fields.add('status')
    for phase in parsed.phase_terms:
        if phase in full_text or phase.replace('_', ' ') in full_text:
            score += 8.0
            matched_fields.add('phase')
    for fiscal_year in parsed.fiscal_years:
        if str(fiscal_year) in full_text:
            score += 6.0
            matched_fields.add('fiscal_year')

    return score, sorted(field for field in matched_fields if field)


def _minimum_coverage(tokens):
    if len(tokens) <= 2:
        return 1.0
    if len(tokens) <= 4:
        return 0.5
    return 0.4


def _serialize_ranked(row, serialize):
    payload = serialize(row['item']) if serialize else row['item']
    if isinstance(payload, dict):
        payload = dict(payload)
        payload['search_score'] = round(row['score'], 2)
        payload['matched_fields'] = row['matched_fields']
    return payload


def _paginate_ranked(ranked, page, per_page):
    page = max(int(page or 1), 1)
    per_page = max(min(int(per_page or 20), 100), 1)
    total = len(ranked)
    pages = (total + per_page - 1) // per_page if total else 0
    start = (page - 1) * per_page
    return {
        'items': ranked[start:start + per_page],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    }


def _pagination_result(key, pagination, serialize):
    return {
        key: [serialize(item) if serialize else item for item in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def _updated_at(item):
    value = getattr(item, 'updated_at', None)
    return value.timestamp() if value else 0


def _escape_like(value):
    return str(value)
