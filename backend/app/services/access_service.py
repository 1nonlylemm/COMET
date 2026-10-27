from sqlalchemy import false

from app.extensions import db
from app.models import LguCluster, LguProfile, Project, ProjectRequirement, User, UserScopeAssignment
from app.services import settings_service


class AccessError(Exception):
    def __init__(self, message='You do not have permission to access this resource', status_code=403):
        self.message = message
        self.status_code = status_code


class MovementPausedError(AccessError):
    def __init__(
        self,
        message="This project's program is deactivated. All project movements and mutations are paused.",
        status_code=409,
        program_id=None,
    ):
        super().__init__(message=message, status_code=status_code)
        self.program_id = program_id


def _coerce_user_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise AccessError('Invalid user identity', 422)


def get_user(user_id):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AccessError('User not found', 404)
    return user


def get_user_role(user_id):
    return get_user(user_id).role


def _active_scope_rows(user_id):
    return (
        UserScopeAssignment.query
        .filter_by(user_id=user_id, is_active=True)
        .order_by(
            UserScopeAssignment.scope_type.asc(),
            UserScopeAssignment.cluster_id.asc(),
            UserScopeAssignment.lgu_id.asc(),
        )
        .all()
    )


def get_access_scope(user_id):
    user = get_user(user_id)
    if user.role not in {'staff', 'field_officer', 'system_admin'}:
        if user.role != 'admin':
            app_name = settings_service.get_app_name()
            raise AccessError(
                f'This account does not have access to the internal {app_name} dashboard.',
                403,
            )

    rows = _active_scope_rows(user.id)
    cluster_ids = sorted({
        row.cluster_id
        for row in rows
        if row.scope_type == 'cluster' and row.cluster_id is not None
    })
    lgu_ids = sorted({
        row.lgu_id
        for row in rows
        if row.scope_type == 'lgu' and row.lgu_id is not None
    })

    if user.role == 'admin':
        return {
            'role': user.role,
            'unrestricted': True,
            'cluster_ids': cluster_ids,
            'lgu_ids': [],
        }
    if user.role == 'staff':
        return {
            'role': user.role,
            'unrestricted': False,
            'cluster_ids': cluster_ids,
            'lgu_ids': [],
        }
    return {
        'role': user.role,
        'unrestricted': False,
        'cluster_ids': [],
        'lgu_ids': lgu_ids,
    }


def get_assigned_cluster_ids(user_id):
    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return None
    return list(scope['cluster_ids'])


def get_assigned_lgu_ids(user_id):
    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return None
    return list(scope['lgu_ids'])


def restrict_cluster_query(query, user_id):
    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(LguCluster.id.in_(cluster_ids))


def restrict_lgu_query(query, user_id):
    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(LguProfile.id.in_(lgu_ids))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(LguProfile.cluster_id.in_(cluster_ids))


def restrict_project_query(query, user_id):
    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(Project.lgu_id.in_(lgu_ids))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(Project.lgu.has(LguProfile.cluster_id.in_(cluster_ids)))


def restrict_project_requirement_query(query, user_id):
    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(
            ProjectRequirement.project.has(Project.lgu_id.in_(lgu_ids))
        )
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(
        ProjectRequirement.project.has(
            Project.lgu.has(LguProfile.cluster_id.in_(cluster_ids))
        )
    )


def _log_scope_violation(user_id, action, entity_type, entity_id, reason):
    try:
        from flask import g, request as flask_request
        from app.services import audit_service
        if not getattr(g, '_security_event_logged', False):
            g._security_event_logged = True
            scope = get_access_scope(user_id) if user_id else {}
            audit_service.log_security_event(
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details={
                    'role': scope.get('role'),
                    'reason': reason,
                    'endpoint': flask_request.endpoint if flask_request else None,
                    'path': flask_request.path if flask_request else None,
                    'method': flask_request.method if flask_request else None,
                },
            )
    except Exception:
        pass


def ensure_cluster_access(cluster_id, user_id):
    cluster = db.session.get(LguCluster, cluster_id)
    if not cluster:
        raise AccessError('Cluster not found', 404)

    scope = get_access_scope(user_id)
    if not scope['unrestricted'] and cluster.id not in scope['cluster_ids']:
        _log_scope_violation(user_id, 'cross_cluster_access_denied', 'cluster', cluster.id, f"User {user_id} lacks access to cluster {cluster.id}")
        raise AccessError()
    return cluster


def ensure_lgu_access(lgu_or_id, user_id):
    lgu = lgu_or_id if isinstance(lgu_or_id, LguProfile) else db.session.get(LguProfile, lgu_or_id)
    if not lgu:
        raise AccessError('LGU not found', 404)

    scope = get_access_scope(user_id)
    if scope['unrestricted']:
        return lgu
    if scope['lgu_ids'] and lgu.id in scope['lgu_ids']:
        return lgu
    if scope['cluster_ids'] and lgu.cluster_id in scope['cluster_ids']:
        return lgu

    if scope.get('role') == 'staff':
        action = 'cross_cluster_access_denied'
        reason = f"Staff user {user_id} lacks access to Cluster {lgu.cluster_id} for LGU {lgu.id}"
    elif scope.get('role') == 'field_officer':
        action = 'cross_lgu_access_denied'
        reason = f"Field officer {user_id} lacks access to LGU {lgu.id}"
    else:
        action = 'out_of_scope_access_denied'
        reason = f"User {user_id} lacks access to LGU {lgu.id}"

    _log_scope_violation(user_id, action, 'lgu', lgu.id, reason)
    raise AccessError()


def ensure_project_access(project_or_id, user_id):
    project = project_or_id if isinstance(project_or_id, Project) else db.session.get(Project, project_or_id)
    if not project:
        raise AccessError('Project not found', 404)

    ensure_lgu_access(project.lgu_id, user_id)
    return project


def ensure_project_requirement_access(requirement_or_id, user_id):
    requirement = (
        requirement_or_id
        if isinstance(requirement_or_id, ProjectRequirement)
        else db.session.get(ProjectRequirement, requirement_or_id)
    )
    if not requirement:
        raise AccessError('Project requirement not found', 404)

    ensure_project_access(requirement.project_id, user_id)
    return requirement


def assert_project_movement_allowed(project_or_id):
    """
    Assert that project movements and mutations are allowed.
    Raises MovementPausedError (409) if the project belongs to a deactivated program.
    """
    if project_or_id is None:
        return None

    project = project_or_id if isinstance(project_or_id, Project) else db.session.get(Project, project_or_id)
    if not project:
        return None

    if project.program and not project.program.is_active:
        program_name = project.program.name or f"#{project.program_id}"
        raise MovementPausedError(
            message=f"Movement paused: Program '{program_name}' is currently deactivated.",
            status_code=409,
            program_id=project.program_id,
        )
    return project


def assert_project_requirement_movement_allowed(requirement_or_id, *, require_applicable=False):
    """
    Assert that project requirement movements and mutations are allowed.
    Resolves the parent project and validates program active status.
    Evidence/workflow writes also require applicability when explicitly requested;
    applicability restoration and read-only history access remain available.
    """
    if requirement_or_id is None:
        return None

    requirement = (
        requirement_or_id
        if isinstance(requirement_or_id, ProjectRequirement)
        else db.session.get(ProjectRequirement, requirement_or_id)
    )
    if not requirement:
        return None

    if require_applicable and requirement.applicability == 'not_applicable':
        raise AccessError(
            'This requirement is marked Not Applicable. Restore applicability before uploading or reviewing evidence.',
            409,
        )

    project_target = getattr(requirement, 'project', None) or getattr(requirement, 'project_id', None)
    if project_target is None:
        return None
    return assert_project_movement_allowed(project_target)
