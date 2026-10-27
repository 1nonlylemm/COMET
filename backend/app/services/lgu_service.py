from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import LguCluster, LguProfile, User, UserScopeAssignment
from app.services import access_service, audit_service


class LguError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code


def _is_scope_assignment_conflict(exc, scope_type):
    """
    Identify whether an IntegrityError was caused by a duplicate scope assignment unique constraint.
    Inspects PostgreSQL diagnostics when available (exc.orig.diag.constraint_name),
    or uses exact narrow SQLite constraint messages when running under SQLite.
    Never matches generic substrings or unrelated field names.
    """
    orig = getattr(exc, 'orig', None)
    expected_constraint = 'uq_user_scope_cluster' if scope_type == 'cluster' else 'uq_user_scope_lgu'
    target_field = 'cluster_id' if scope_type == 'cluster' else 'lgu_id'

    if orig is not None:
        diag = getattr(orig, 'diag', None)
        if diag is not None:
            constraint_name = getattr(diag, 'constraint_name', None)
            if constraint_name == expected_constraint:
                return True

    msg = str(orig if orig is not None else exc).lower()
    if expected_constraint in msg:
        return True
    if 'unique constraint failed:' in msg and 'user_scope_assignments' in msg and target_field in msg:
        return True
    return False


# ── Cluster CRUD ──────────────────────────────────────────────────────────

def create_cluster(name, description=None, user_id=None):
    name = _require_text(name, 'Cluster name')
    description = _optional_text(description)

    if _cluster_by_name(name):
        raise LguError('Cluster name already exists', 409)

    cluster = LguCluster(name=name, description=description)
    db.session.add(cluster)
    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='create',
            entity_type='lgu_cluster',
            entity_id=cluster.id,
            old_value=None,
            new_value=_serialize_cluster(cluster),
        )

    return cluster


def get_cluster(cluster_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_cluster_access(cluster_id, user_id)
    except access_service.AccessError as exc:
        raise LguError(exc.message, exc.status_code)

    cluster = db.session.get(LguCluster, cluster_id)
    if not cluster:
        raise LguError('Cluster not found', 404)
    return cluster


def list_clusters(search=None, user_id=None):
    query = LguCluster.query
    if user_id is not None:
        query = access_service.restrict_cluster_query(query, user_id)
    if search:
        query = query.filter(LguCluster.name.ilike(f'%{search}%'))
    clusters = query.order_by(LguCluster.name).all()
    return [_serialize_cluster(c) for c in clusters]


def update_cluster(cluster_id, data, user_id=None):
    cluster = db.session.get(LguCluster, cluster_id)
    if not cluster:
        raise LguError('Cluster not found', 404)

    before = _serialize_cluster(cluster)

    if 'name' in data:
        name = _require_text(data['name'], 'Cluster name')
        existing = _cluster_by_name(name, exclude_id=cluster_id)
        if existing:
            raise LguError('Cluster name already exists', 409)
        cluster.name = name
    if 'description' in data:
        cluster.description = _optional_text(data['description'])

    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='update',
            entity_type='lgu_cluster',
            entity_id=cluster.id,
            old_value=before,
            new_value=_serialize_cluster(cluster),
        )

    return cluster


def delete_cluster(cluster_id, user_id=None):
    cluster = db.session.get(LguCluster, cluster_id)
    if not cluster:
        raise LguError('Cluster not found', 404)

    if cluster.lgus.count() > 0:
        raise LguError('Cluster has assigned LGUs and cannot be deleted', 409)
    if cluster.staff_assignments.count() > 0:
        raise LguError('Cluster has user scope assignments and cannot be deleted', 409)

    before = _serialize_cluster(cluster)
    db.session.delete(cluster)
    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='delete',
            entity_type='lgu_cluster',
            entity_id=cluster_id,
            old_value=before,
            new_value=None,
        )

    return {'message': 'Cluster deleted successfully'}


# ── LGU CRUD ──────────────────────────────────────────────────────────────

def create_lgu(name, municipality, province='Laguna', cluster_id=None,
               mayor_name=None, mayor_email=None,
               contact_person=None, contact_email=None, contact_phone=None,
               user_id=None):
    name = _require_text(name, 'LGU name')
    municipality = _require_text(municipality, 'Municipality')
    province = _require_text(province or 'Laguna', 'Province')
    cluster_id = _coerce_optional_int(cluster_id, 'Cluster ID')
    if cluster_id is not None and not db.session.get(LguCluster, cluster_id):
        raise LguError('Cluster not found', 404)

    if _lgu_duplicate(name, municipality, province):
        raise LguError('LGU profile already exists', 409)

    lgu = LguProfile(
        name=name,
        municipality=municipality,
        province=province,
        cluster_id=cluster_id,
        mayor_name=_optional_text(mayor_name),
        mayor_email=_optional_text(mayor_email),
        contact_person=_optional_text(contact_person),
        contact_email=_optional_text(contact_email),
        contact_phone=_optional_text(contact_phone),
    )
    db.session.add(lgu)
    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='create',
            entity_type='lgu_profile',
            entity_id=lgu.id,
            old_value=None,
            new_value=_serialize_lgu(lgu),
        )

    return lgu


def get_lgu(lgu_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_lgu_access(lgu_id, user_id)
    except access_service.AccessError as exc:
        raise LguError(exc.message, exc.status_code)

    lgu = db.session.get(LguProfile, lgu_id)
    if not lgu:
        raise LguError('LGU not found', 404)
    return lgu


def list_lgus(search=None, cluster_id=None, is_active=None, page=1, per_page=20, user_id=None):
    query = LguProfile.query
    if user_id is not None:
        query = access_service.restrict_lgu_query(query, user_id)

    if search:
        search = _collapse_spaces(search)
        query = query.filter(
            db.or_(
                LguProfile.name.ilike(f'%{search}%'),
                LguProfile.municipality.ilike(f'%{search}%'),
            )
        )
    if cluster_id is not None:
        query = query.filter_by(cluster_id=cluster_id)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)

    pagination = query.order_by(LguProfile.name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'lgus': [_serialize_lgu(l) for l in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def update_lgu(lgu_id, data, user_id=None):
    lgu = get_lgu(lgu_id, user_id=user_id)

    before = _serialize_lgu(lgu)

    next_name = _require_text(data['name'], 'LGU name') if 'name' in data else lgu.name
    next_municipality = (
        _require_text(data['municipality'], 'Municipality')
        if 'municipality' in data else lgu.municipality
    )
    next_province = _require_text(data['province'], 'Province') if 'province' in data else lgu.province
    if _lgu_duplicate(next_name, next_municipality, next_province, exclude_id=lgu_id):
        raise LguError('LGU profile already exists', 409)

    if 'name' in data:
        lgu.name = next_name
    if 'municipality' in data:
        lgu.municipality = next_municipality
    if 'province' in data:
        lgu.province = next_province
    if 'cluster_id' in data:
        cluster_id = _coerce_optional_int(data['cluster_id'], 'Cluster ID')
        if cluster_id is not None and not db.session.get(LguCluster, cluster_id):
            raise LguError('Cluster not found', 404)
        lgu.cluster_id = cluster_id
    if 'mayor_name' in data:
        lgu.mayor_name = _optional_text(data['mayor_name'])
    if 'mayor_email' in data:
        lgu.mayor_email = _optional_text(data['mayor_email'])
    if 'contact_person' in data:
        lgu.contact_person = _optional_text(data['contact_person'])
    if 'contact_email' in data:
        lgu.contact_email = _optional_text(data['contact_email'])
    if 'contact_phone' in data:
        lgu.contact_phone = _optional_text(data['contact_phone'])

    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='update',
            entity_type='lgu_profile',
            entity_id=lgu.id,
            old_value=before,
            new_value=_serialize_lgu(lgu),
        )

    return lgu


def toggle_lgu_active(lgu_id, user_id=None, is_active=None):
    lgu = get_lgu(lgu_id, user_id=user_id)

    before = _serialize_lgu(lgu)
    lgu.is_active = not lgu.is_active if is_active is None else bool(is_active)
    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='toggle_active',
            entity_type='lgu_profile',
            entity_id=lgu.id,
            old_value=before,
            new_value=_serialize_lgu(lgu),
        )

    return lgu


# ── Staff Assignments ─────────────────────────────────────────────────────

def assign_staff_to_cluster(user_id, cluster_id, actor_user_id=None):
    user_id = _coerce_required_int(user_id, 'User ID')
    cluster_id = _coerce_required_int(cluster_id, 'Cluster ID')
    user = db.session.get(User, user_id)
    if not user:
        raise LguError('User not found', 404)
    if user.role not in {'admin', 'staff'}:
        raise LguError('Only admin and staff users can be assigned to LGU clusters', 422)

    cluster = db.session.get(LguCluster, cluster_id)
    if not cluster:
        raise LguError('Cluster not found', 404)

    existing = UserScopeAssignment.query.filter_by(
        user_id=user_id, scope_type='cluster', cluster_id=cluster_id
    ).first()
    if existing:
        if existing.is_active:
            raise LguError('User is already assigned to this cluster', 409)
        before = _serialize_assignment(existing)
        existing.is_active = True
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            if _is_scope_assignment_conflict(exc, 'cluster'):
                raise LguError('User is already assigned to this cluster', 409) from exc
            raise

        if actor_user_id is not None:
            audit_service.log_action(
                user_id=actor_user_id,
                action='toggle_active',
                entity_type='user_scope_assignment',
                entity_id=existing.id,
                old_value=before,
                new_value=_serialize_assignment(existing),
            )

        return existing

    assignment = UserScopeAssignment(user_id=user_id, scope_type='cluster', cluster_id=cluster_id)
    db.session.add(assignment)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if _is_scope_assignment_conflict(exc, 'cluster'):
            raise LguError('User is already assigned to this cluster', 409) from exc
        raise

    if actor_user_id is not None:
        audit_service.log_action(
            user_id=actor_user_id,
            action='create',
            entity_type='user_scope_assignment',
            entity_id=assignment.id,
            old_value=None,
            new_value=_serialize_assignment(assignment),
        )

    return assignment


def assign_field_officer_to_lgu(user_id, lgu_id, actor_user_id=None):
    user_id = _coerce_required_int(user_id, 'User ID')
    lgu_id = _coerce_required_int(lgu_id, 'LGU ID')
    user = db.session.get(User, user_id)
    if not user:
        raise LguError('User not found', 404)
    if user.role != 'field_officer':
        raise LguError('Only field officer users can be assigned to specific LGUs', 422)

    lgu = db.session.get(LguProfile, lgu_id)
    if not lgu:
        raise LguError('LGU not found', 404)

    existing = UserScopeAssignment.query.filter_by(
        user_id=user_id, scope_type='lgu', lgu_id=lgu_id
    ).first()
    if existing:
        if existing.is_active:
            raise LguError('User is already assigned to this LGU', 409)
        before = _serialize_assignment(existing)
        existing.is_active = True
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            if _is_scope_assignment_conflict(exc, 'lgu'):
                raise LguError('User is already assigned to this LGU', 409) from exc
            raise

        if actor_user_id is not None:
            audit_service.log_action(
                user_id=actor_user_id,
                action='toggle_active',
                entity_type='user_scope_assignment',
                entity_id=existing.id,
                old_value=before,
                new_value=_serialize_assignment(existing),
            )

        return existing

    assignment = UserScopeAssignment(user_id=user_id, scope_type='lgu', lgu_id=lgu_id)
    db.session.add(assignment)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if _is_scope_assignment_conflict(exc, 'lgu'):
            raise LguError('User is already assigned to this LGU', 409) from exc
        raise

    if actor_user_id is not None:
        audit_service.log_action(
            user_id=actor_user_id,
            action='create',
            entity_type='user_scope_assignment',
            entity_id=assignment.id,
            old_value=None,
            new_value=_serialize_assignment(assignment),
        )

    return assignment


def list_assignments(cluster_id=None, lgu_id=None, user_id=None, is_active=None, scope_type=None):
    query = UserScopeAssignment.query

    if scope_type is not None:
        query = query.filter_by(scope_type=scope_type)
    if cluster_id is not None:
        query = query.filter_by(cluster_id=cluster_id)
    if lgu_id is not None:
        query = query.filter_by(lgu_id=lgu_id)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)

    assignments = query.order_by(UserScopeAssignment.assigned_at.desc()).all()
    return [_serialize_assignment(a) for a in assignments]


def remove_assignment(assignment_id, user_id=None):
    assignment_id = _coerce_required_int(assignment_id, 'Assignment ID')
    assignment = db.session.get(UserScopeAssignment, assignment_id)
    if not assignment:
        raise LguError('Assignment not found', 404)

    before = _serialize_assignment(assignment)
    db.session.delete(assignment)
    db.session.commit()

    if user_id is not None:
        audit_service.log_action(
            user_id=user_id,
            action='delete',
            entity_type='user_scope_assignment',
            entity_id=assignment_id,
            old_value=before,
            new_value=None,
        )

    return {'message': 'Assignment removed successfully'}


# ── Validation Helpers ─────────────────────────────────────────────────────

def _collapse_spaces(value):
    if value is None:
        return None
    return ' '.join(str(value).strip().split())


def _optional_text(value):
    text = _collapse_spaces(value)
    return text or None


def _require_text(value, label):
    text = _collapse_spaces(value)
    if not text:
        raise LguError(f'{label} is required', 422)
    return text


def _normalized_text(value):
    text = _collapse_spaces(value)
    return text.lower() if text else ''


def _coerce_required_int(value, label):
    if value in (None, ''):
        raise LguError(f'{label} is required', 422)
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        raise LguError(f'{label} must be an integer', 422)
    if coerced < 1:
        raise LguError(f'{label} must be a positive integer', 422)
    return coerced


def _coerce_optional_int(value, label):
    if value in (None, ''):
        return None
    return _coerce_required_int(value, label)


def _cluster_by_name(name, exclude_id=None):
    normalized = _normalized_text(name)
    if not normalized:
        return None
    query = LguCluster.query.filter(func.lower(func.trim(LguCluster.name)) == normalized)
    if exclude_id is not None:
        query = query.filter(LguCluster.id != exclude_id)
    return query.first()


def _lgu_duplicate(name, municipality, province, exclude_id=None):
    query = LguProfile.query
    if exclude_id is not None:
        query = query.filter(LguProfile.id != exclude_id)

    name_match = query.filter(
        func.lower(func.trim(LguProfile.name)) == _normalized_text(name)
    ).first()
    if name_match:
        return name_match

    return query.filter(
        func.lower(func.trim(LguProfile.municipality)) == _normalized_text(municipality),
        func.lower(func.trim(LguProfile.province)) == _normalized_text(province or 'Laguna'),
    ).first()


# ── Serializers ────────────────────────────────────────────────────────────

def _serialize_cluster(cluster):
    return {
        'id': cluster.id,
        'name': cluster.name,
        'description': cluster.description,
        'lgus_count': cluster.lgus.count(),
        'created_at': cluster.created_at.isoformat() if cluster.created_at else None,
    }


def _serialize_lgu(lgu):
    return {
        'id': lgu.id,
        'name': lgu.name,
        'municipality': lgu.municipality,
        'province': lgu.province,
        'cluster_id': lgu.cluster_id,
        'cluster_name': lgu.cluster.name if lgu.cluster else None,
        'mayor_name': lgu.mayor_name,
        'mayor_email': lgu.mayor_email,
        'contact_person': lgu.contact_person,
        'contact_email': lgu.contact_email,
        'contact_phone': lgu.contact_phone,
        'is_active': lgu.is_active,
        'created_at': lgu.created_at.isoformat() if lgu.created_at else None,
        'updated_at': lgu.updated_at.isoformat() if lgu.updated_at else None,
    }


def _serialize_assignment(assignment):
    result = {
        'id': assignment.id,
        'user_id': assignment.user_id,
        'scope_type': assignment.scope_type,
        'cluster_id': assignment.cluster_id,
        'lgu_id': assignment.lgu_id,
        'is_active': assignment.is_active,
        'assigned_at': assignment.assigned_at.isoformat() if assignment.assigned_at else None,
    }
    if assignment.user:
        result['user'] = {
            'id': assignment.user.id,
            'email': assignment.user.email,
            'full_name': assignment.user.full_name,
        }
    if assignment.cluster:
        result['cluster'] = {
            'id': assignment.cluster.id,
            'name': assignment.cluster.name,
        }
    if assignment.lgu:
        result['lgu'] = {
            'id': assignment.lgu.id,
            'name': assignment.lgu.name,
            'municipality': assignment.lgu.municipality,
            'province': assignment.lgu.province,
            'cluster_id': assignment.lgu.cluster_id,
            'cluster_name': assignment.lgu.cluster.name if assignment.lgu.cluster else None,
        }
    return result
