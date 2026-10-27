from app.models import EscalationNotice, Project, ProjectRequirement, QaarInspection, SlaDeadline


def apply_project_fiscal_year(query, fiscal_year):
    if fiscal_year is None:
        return query
    return query.filter(Project.fiscal_year == fiscal_year)


def apply_requirement_project_fiscal_year(query, fiscal_year):
    if fiscal_year is None:
        return query
    return query.filter(ProjectRequirement.project.has(Project.fiscal_year == fiscal_year))


def apply_sla_project_fiscal_year(query, fiscal_year):
    if fiscal_year is None:
        return query
    return query.filter(SlaDeadline.project.has(Project.fiscal_year == fiscal_year))


def apply_notice_project_fiscal_year(query, fiscal_year):
    if fiscal_year is None:
        return query
    return query.filter(EscalationNotice.project.has(Project.fiscal_year == fiscal_year))


def apply_inspection_project_fiscal_year(query, fiscal_year):
    if fiscal_year is None:
        return query
    return query.filter(QaarInspection.project.has(Project.fiscal_year == fiscal_year))
