SYSTEM_ADMIN = 'system_admin'
# NOTE: 'admin' is COMET's existing province-wide operational authority role.
# It already matches the "Provincial Admin" responsibilities described in the
# Phase 1 workflow spec (manage users, manage LGUs, global approve/return),
# so the shared workflow reuses this role instead of introducing a new one.
OPERATIONAL_ADMIN = 'admin'
PROVINCIAL_ADMIN = OPERATIONAL_ADMIN
STAFF = 'staff'
FIELD_OFFICER = 'field_officer'

INTERNAL_USER_ROLES = (
    SYSTEM_ADMIN,
    OPERATIONAL_ADMIN,
    STAFF,
    FIELD_OFFICER,
)

OPERATIONAL_ACCOUNT_ROLES = (
    OPERATIONAL_ADMIN,
    STAFF,
    FIELD_OFFICER,
)

# Roles with global (province-wide) operational authority over the shared
# document workflow (Provincial Admin approval/return stage).
WORKFLOW_GLOBAL_APPROVER_ROLES = (
    OPERATIONAL_ADMIN,
)

SYSTEM_ADMIN_MANAGED_ROLES = INTERNAL_USER_ROLES
OPERATIONAL_ADMIN_MANAGED_ROLES = OPERATIONAL_ACCOUNT_ROLES
