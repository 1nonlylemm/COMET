"""
COMET AI Navigation Service: Verified Application Route Catalogue and Navigation Intent Routing.

Provides:
1. Canonical verified frontend route mappings with strict RBAC constraints.
2. Context-aware navigation intent detection (distinguishing page discovery from record retrieval).
3. Conversational multi-turn clarification resolution (e.g., rejecting record lists in favor of UI pages).
4. Clickable Markdown link generation for approved internal destinations.
5. Dynamic app-name injection and role-safe navigation guidance.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple


# Verified Route Catalogue aligned with frontend/src/config/routes.js and App.jsx
NAVIGATION_CATALOGUE: Dict[str, Dict[str, Any]] = {
    'projects': {
        'path': '/dashboard/projects',
        'label': 'Projects page',
        'short_label': 'Projects',
        'description': 'Browse and filter municipal infrastructure, goods, and financial assistance projects',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['project', 'projects', 'proyekto', 'project list', 'list of projects', 'project records'],
        'guidance': {
            'default': (
                "You can view projects on the [Projects page](/dashboard/projects). "
                "Open a project to see its details. Use the available filters to narrow the list to the LGU you handle."
            ),
            'field_officer': (
                "You can view projects on the [Projects page](/dashboard/projects). "
                "Field officers have access to projects within their assigned LGUs. "
                "Open any project to inspect its details and documentary requirements."
            ),
        },
    },
    'lgus': {
        'path': '/dashboard/lgus',
        'label': 'LGUs page',
        'short_label': 'LGUs',
        'description': 'View Local Government Unit profiles and municipal assignments',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['lgu', 'lgus', 'local government', 'municipality', 'municipalities', 'lgu profile', 'lgu information'],
        'guidance': {
            'default': (
                "You can view LGU profiles on the [LGUs page](/dashboard/lgus). "
                "Select an LGU to view its assigned cluster, contact information, and portfolio. "
                "Note: Master data editing is restricted to Administrators."
            ),
            'field_officer': (
                "You can view your assigned municipal profiles on the [LGUs page](/dashboard/lgus). "
                "Field officers have read-only access to their assigned LGUs."
            ),
        },
    },
    'programs': {
        'path': '/dashboard/programs',
        'label': 'Programs page',
        'short_label': 'Programs',
        'description': 'Browse funding programs and program cycles',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['program', 'programs', 'cycle', 'cycles', 'grant program', 'lgsf', 'falgu', 'program cycles'],
        'guidance': {
            'default': (
                "You can browse funding programs and cycles on the [Programs page](/dashboard/programs). "
                "Open a program to inspect its cycles, guidelines, and eligible expenditure kinds."
            ),
        },
    },
    'monitoring': {
        'path': '/dashboard/monitoring',
        'label': 'Monitoring page',
        'short_label': 'Monitoring',
        'description': 'Implementation monitoring, inspections, deliveries, and beneficiary tracking',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['monitoring', 'inspection', 'inspections', 'qaar', 'delivery', 'deliveries', 'beneficiary', 'workbench'],
        'guidance': {
            'default': (
                "You can track project execution on the [Monitoring page](/dashboard/monitoring). "
                "It covers physical progress inspections, non-infra delivery verification, and beneficiary evidence."
            ),
        },
    },
    'requirements': {
        'path': '/dashboard/monitoring',
        'label': 'Monitoring page',
        'short_label': 'Documentary Requirements',
        'description': 'Review documentary requirements and compliance status',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['requirement', 'requirements', 'documentary requirement', 'documentary requirements', 'document', 'documents', 'submitted requirements', 'compliance'],
        'guidance': {
            'default': (
                "You can review submitted requirements and compliance status on the [Monitoring page](/dashboard/monitoring). "
                "To review requirements for a specific project, open the project from the [Projects page](/dashboard/projects) "
                "and navigate to its Requirements tab."
            ),
        },
    },
    'sla': {
        'path': '/dashboard/sla',
        'label': 'Compliance Deadlines page',
        'short_label': 'Compliance Deadlines',
        'description': 'Track SLA deadlines and overdue compliance milestones',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['sla', 'deadline', 'deadlines', 'overdue', 'compliance deadline', 'due dates', 'sla tracker'],
        'guidance': {
            'default': (
                "You can track compliance deadlines and SLA milestones on the [Compliance Deadlines page](/dashboard/sla). "
                "It highlights overdue review windows, active statutory clocks, and pending actions."
            ),
        },
    },
    'escalation': {
        'path': '/dashboard/escalation',
        'label': 'Notices & Follow-Up page',
        'short_label': 'Notices & Follow-Up',
        'description': 'Review escalation notices, Notice of Non-Compliance drafts, and deficiency tracking',
        'roles': {'admin', 'staff'},
        'keywords': ['notice', 'notices', 'escalation', 'nnc', 'deficiency notice', 'follow up'],
        'guidance': {
            'default': (
                "You can review escalation notices and draft statutory communications on the [Notices & Follow-Up page](/dashboard/escalation)."
            ),
        },
    },
    'reports': {
        'path': '/dashboard/reports',
        'label': 'Reports & Analytics page',
        'short_label': 'Reports & Analytics',
        'description': 'Operational analytics, deficiency summaries, and provincial progress charts',
        'roles': {'admin', 'staff'},
        'keywords': ['report', 'reports', 'analytics', 'statistics', 'charts', 'summary report'],
        'guidance': {
            'default': (
                "You can view operational statistics, risk rankings, and deficiency patterns on the [Reports & Analytics page](/dashboard/reports)."
            ),
        },
    },
    'handoff': {
        'path': '/dashboard/handoff',
        'label': 'Regional Handoff page',
        'short_label': 'Regional Handoff',
        'description': 'Regional review queues and endorsed documentary submissions',
        'roles': {'admin', 'staff'},
        'keywords': ['handoff', 'regional handoff', 'endorsement', 'regional queue'],
        'guidance': {
            'default': (
                "You can view documents queued or endorsed for regional review on the [Regional Handoff page](/dashboard/handoff)."
            ),
        },
    },
    'completion': {
        'path': '/dashboard/completion',
        'label': 'Completion page',
        'short_label': 'Completion',
        'description': 'Project completion verification, final documentation, and closeout archives',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['completion', 'closeout', 'final documentation', 'turnover', 'document vault'],
        'guidance': {
            'default': (
                "You can manage project closeout, completion document verification, and turnover records on the [Completion page](/dashboard/completion)."
            ),
        },
    },
    'library': {
        'path': '/dashboard/library',
        'label': 'Reference Library',
        'short_label': 'Reference Library',
        'description': 'Official guidelines, policy manuals, document templates, and statutory checklists',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['library', 'guideline', 'guidelines', 'policy', 'policies', 'manual', 'template', 'templates', 'reference', 'reference library'],
        'guidance': {
            'default': (
                "Official guidelines, policy manuals, and document templates are available in the [Reference Library](/dashboard/library)."
            ),
        },
    },
    'audit': {
        'path': '/dashboard/audit',
        'label': 'Audit Log',
        'short_label': 'Audit Log',
        'description': 'Immutable system audit trail of administrative actions and status transitions',
        'roles': {'admin', 'system_admin'},
        'keywords': ['audit', 'audit log', 'audit trail', 'logs', 'history log'],
        'guidance': {
            'default': (
                "You can inspect the immutable system activity trail on the [Audit Log page](/dashboard/audit). "
                "It records user actions, status changes, and data updates across the workspace."
            ),
        },
    },
    'users': {
        'path': '/dashboard/users',
        'label': 'User Management page',
        'short_label': 'User Management',
        'description': 'Manage user accounts, roles, and cluster assignments',
        'roles': {'admin', 'system_admin'},
        'keywords': ['user', 'users', 'user account', 'accounts', 'user management'],
        'guidance': {
            'default': (
                "You can manage user accounts and role assignments on the [User Management page](/dashboard/users)."
            ),
        },
    },
    'settings': {
        'path': '/dashboard/settings',
        'label': 'Settings page',
        'short_label': 'Settings',
        'description': 'Workspace settings, branding, risk thresholds, and backups',
        'roles': {'admin'},
        'keywords': ['setting', 'settings', 'branding', 'backup', 'backups', 'risk threshold', 'system settings'],
        'guidance': {
            'default': (
                "Workspace settings, branding, and system thresholds are managed on the [Settings page](/dashboard/settings)."
            ),
        },
    },
    'system_admin': {
        'path': '/dashboard/system-admin',
        'label': 'System Administration page',
        'short_label': 'System Administration',
        'description': 'Technical system diagnostics, service readiness, and AI configuration',
        'roles': {'system_admin'},
        'keywords': ['system admin', 'system administration', 'diagnostics', 'technical settings', 'service readiness'],
        'guidance': {
            'default': (
                "System health diagnostics and technical settings are available on the [System Administration page](/dashboard/system-admin)."
            ),
        },
    },
    'intake': {
        'path': '/dashboard/intake',
        'label': 'Documentary Intake page',
        'short_label': 'Documentary Intake',
        'description': 'Upload and triage documentary evidence and initial submissions',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['intake', 'evidence intake', 'documentary intake', 'upload evidence', 'triage'],
        'guidance': {
            'default': (
                "You can upload and triage documentary submissions on the [Documentary Intake page](/dashboard/intake)."
            ),
        },
    },
    'field_work': {
        'path': '/dashboard/field',
        'label': 'My Field Work page',
        'short_label': 'My Field Work',
        'description': 'Field officer dashboard and action items',
        'roles': {'field_officer'},
        'keywords': ['field work', 'field dashboard', 'my field work', 'field officer dashboard'],
        'guidance': {
            'default': (
                "Field officer daily tasks, assigned LGUs, and action items are on the [My Field Work page](/dashboard/field)."
            ),
        },
    },
    'archive': {
        'path': '/dashboard/archive',
        'label': 'Archive & Communications page',
        'short_label': 'Archive & Communications',
        'description': 'Archive communications and historical governance records',
        'roles': {'admin', 'staff', 'field_officer'},
        'keywords': ['archive', 'communications', 'historical records', 'governance records'],
        'guidance': {
            'default': (
                "Historical records and governance memos can be accessed on the [Archive & Communications page](/dashboard/archive)."
            ),
        },
    },
}


# Precompiled regular expressions for navigation intent detection
RE_EXPLICIT_REJECT_LIST = re.compile(
    r'\b(?:i\s+)?(?:don\'?t|do\s+not)\s+want\s+(?:you\s+to\s+)?(?:list|retrieve|search|show\s+a\s+list)\b'
    r'|\b(?:not\s+looking\s+for\s+a\s+list|no\s+need\s+to\s+list|don\'?t\s+list|stop\s+listing)\b'
    r'|\b(?:not\s+(?:the\s+)?(?:results?|data|list))\b',
    re.IGNORECASE,
)

RE_PAGE_DISCOVERY = re.compile(
    r'\b(?:actual|real)\s+page\b'
    r'|\b(?:find|see|view|look\s+up|browse|where\s+is)\s+(?:the\s+)?(?:actual\s+)?page\b'
    r'|\bpage\s+where\s+i\s+can\b'
    r'|\bwhich\s+page\b'
    r'|\bwhat\s+page\b',
    re.IGNORECASE,
)

RE_NAVIGATION_LOCATION = re.compile(
    r'\bwhere\s+(?:can\s+i|do\s+i|to)\s+(?:find|see|view|look\s+up|browse|check|open|manage|track|inspect)\b'
    r'|\bhow\s+(?:can\s+i|do\s+i)\s+(?:open|find|navigate\s+to|access|go\s+to)\s+(?:the\s+)?(?:page|tab|section|log|tracker|workbench|library)\b'
    r'|\bwhere\s+(?:is|are)\s+(?:the\s+)?(?:page|section|tab|workbench|log|tracker|library)\b'
    r'|\bhow\s+(?:can\s+i|do\s+i)\s+find\s+(?:a\s+specific\s+project|the\s+page)\b',
    re.IGNORECASE,
)


def get_navigation_catalogue(user_role: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Return the verified navigation catalogue filtered by user role permissions."""
    if not user_role:
        return dict(NAVIGATION_CATALOGUE)
    return {
        k: v for k, v in NAVIGATION_CATALOGUE.items()
        if user_role in v.get('roles', set())
    }


def is_navigation_query(message: str, conversation: Optional[Any] = None) -> bool:
    """Determine whether the message represents navigation intent rather than data retrieval."""
    if not message:
        return False
    norm = message.strip().lower()

    # 1. Explicit rejection of data listing or request for the actual page
    if RE_EXPLICIT_REJECT_LIST.search(norm) or RE_PAGE_DISCOVERY.search(norm):
        return True

    # 2. Location-based navigation inquiry (where can I find/see/view/open...)
    if RE_NAVIGATION_LOCATION.search(norm):
        # Exclude mutations or specific record inspect
        if re.search(r'\b(?:update|change|edit|modify|delete|remove|restore|create|add)\b', norm):
            return False
        # If user asks where to find reference guidelines/documents without page/navigation keywords, let list_guidelines handle it
        if re.search(r'\b(?:guideline|guidelines|reference\s+guidelines)\b', norm) and not re.search(r'\b(?:page|screen|tab|url|link|route|library\s+page)\b', norm):
            return False
        return True

    # 3. Direct questions like "Which page shows my LGU's projects?"
    if re.search(r'\bwhich\s+page\s+(?:shows|lists|has|contains|displays)\b', norm):
        return False if re.search(r'\b(?:update|delete)\b', norm) else True

    # 4. Phrasing like "How do I open the audit log?"
    if re.search(r'\bhow\s+do\s+i\s+open\b', norm):
        return True

    return False


def _extract_recent_conversation_text(conversation: Optional[Any]) -> str:
    """Extract combined text of recent turns in the conversation for topic context."""
    if not conversation:
        return ''
    texts = []
    # If conversation has messages relation
    messages = getattr(conversation, 'messages', None)
    if messages is not None:
        try:
            # AiMessage query
            recent = messages.order_by(messages.prop.mapper.class_.created_at.desc()).limit(4).all()
            for m in reversed(recent):
                if getattr(m, 'content', None):
                    texts.append(m.content)
        except Exception:
            pass
    # If conversation has context
    ctx = getattr(conversation, 'context', None) or {}
    if ctx.get('pending_clarification'):
        action = ctx['pending_clarification'].get('action', '')
        texts.append(action)
    return ' '.join(texts)


def resolve_navigation_target(
    message: str,
    conversation: Optional[Any] = None,
    user_role: Optional[str] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Resolve the target navigation destination key from query and prior conversational context."""
    norm = (message or '').strip().lower()

    # Check for direct keyword matches in current message (ordered by specificity)
    destination_priority = [
        'audit',
        'settings',
        'system_admin',
        'users',
        'sla',
        'escalation',
        'reports',
        'handoff',
        'completion',
        'library',
        'intake',
        'field_work',
        'archive',
        'monitoring',
        'requirements',
        'programs',
        'lgus',
        'projects',
    ]

    for key in destination_priority:
        target = NAVIGATION_CATALOGUE[key]
        for kw in target['keywords']:
            if re.search(rf'\b{re.escape(kw)}\b', norm):
                return key, target

    # If no direct keyword match, inspect conversation context / previous turn
    recent_text = _extract_recent_conversation_text(conversation).lower()
    if recent_text:
        for key in destination_priority:
            target = NAVIGATION_CATALOGUE[key]
            for kw in target['keywords']:
                if re.search(rf'\b{re.escape(kw)}\b', recent_text):
                    return key, target

    # Default fallback destination if user asked generally about viewing/finding something
    return 'projects', NAVIGATION_CATALOGUE['projects']


def generate_navigation_response(
    message: str,
    conversation: Optional[Any] = None,
    user: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Generate a complete role-aware navigation guidance response with clickable links."""
    if not is_navigation_query(message, conversation):
        return None

    user_role = getattr(user, 'role', 'staff') if user else 'staff'
    resolved = resolve_navigation_target(message, conversation, user_role)
    if not resolved:
        return None

    key, dest = resolved

    # Check role access permission
    allowed_roles = dest.get('roles', set())
    if user_role not in allowed_roles:
        # Honest role restriction guidance: explain restriction without directing to 403
        role_label = user_role.replace('_', ' ').title()
        if user_role == 'field_officer':
            role_label = 'Field Officer'
        elif user_role == 'system_admin':
            role_label = 'System Administrator'

        reply = (
            f"The {dest['short_label']} section is restricted to Administrators "
            f"and is not accessible from your current role ({role_label})."
        )
        return {
            'assistant_reply': reply,
            'tool_calls': [],
            'ai_provider_used': 'local:navigation',
            'ai_model_used': 'rule-based',
            'heuristic_rule_hit': 'navigation_restricted',
            'context_updates': {'pending_clarification': None},
        }

    # Fetch role-specific or default guidance template
    guidance_map = dest.get('guidance', {})
    reply = guidance_map.get(user_role) or guidance_map.get('default')

    return {
        'assistant_reply': reply,
        'tool_calls': [],
        'ai_provider_used': 'local:navigation',
        'ai_model_used': 'rule-based',
        'heuristic_rule_hit': 'navigation_guidance',
        'context_updates': {'pending_clarification': None},
        'destination': key,
        'path': dest['path'],
    }


def linkify_navigation_references(text: str, user_role: Optional[str] = None) -> str:
    """Enrich plain-text page references with verified Markdown links for accessible destinations."""
    if not text:
        return text

    sanitized = text

    # Map of plain text phrases to destination keys
    # Ordered by descending length to avoid partial matches
    plain_phrase_map = [
        ('Projects page', 'projects'),
        ('Projects Page', 'projects'),
        ('LGUs page', 'lgus'),
        ('LGUs Page', 'lgus'),
        ('Programs page', 'programs'),
        ('Programs Page', 'programs'),
        ('Monitoring page', 'monitoring'),
        ('Monitoring Page', 'monitoring'),
        ('Compliance Deadlines page', 'sla'),
        ('Compliance Deadlines', 'sla'),
        ('SLA Tracker', 'sla'),
        ('Notices & Follow-Up page', 'escalation'),
        ('Notices & Follow-Up', 'escalation'),
        ('Reports & Analytics page', 'reports'),
        ('Reports & Analytics', 'reports'),
        ('Completion page', 'completion'),
        ('Reference Library', 'library'),
        ('Audit Log page', 'audit'),
        ('Audit Log', 'audit'),
        ('User Management page', 'users'),
        ('Settings page', 'settings'),
        ('System Administration page', 'system_admin'),
        ('Documentary Intake page', 'intake'),
        ('My Field Work page', 'field_work'),
    ]

    for phrase, dest_key in plain_phrase_map:
        dest = NAVIGATION_CATALOGUE.get(dest_key)
        if not dest:
            continue

        # Role check: default to staff to protect admin-only destinations if user_role is unprovided
        effective_role = user_role or 'staff'
        if effective_role not in dest.get('roles', set()):
            continue

        path = dest['path']
        # Only replace if not already part of a markdown link: [phrase](...) or [something](path)
        if phrase == 'Compliance Deadlines':
            pattern = rf'(?<![Ww]orking-[Dd]ay )(?<![Ww]orking [Dd]ay )(?<!\[)\b{re.escape(phrase)}\b(?!\s*\]|\([^)]*\))'
        else:
            pattern = rf'(?<!\[)\b{re.escape(phrase)}\b(?!\s*\]|\([^)]*\))'
        sanitized = re.sub(pattern, f'[{phrase}]({path})', sanitized)

    return sanitized


def is_verified_destination_path(path: str, user_role: Optional[str] = None) -> bool:
    """Check if an internal path is grounded in the verified navigation catalogue and permitted for the role."""
    if not path or not isinstance(path, str):
        return False
    clean_path = path.strip().split('?')[0].split('#')[0]

    effective_role = user_role or 'staff'

    # Check verified catalogue entries
    for dest in NAVIGATION_CATALOGUE.values():
        dest_path = dest['path']
        if clean_path == dest_path or clean_path.startswith(dest_path + '/'):
            allowed_roles = dest.get('roles', set())
            return effective_role in allowed_roles

    # Also permit standard dashboard home and guidelines
    if clean_path in ('/dashboard', '/dashboard/', '/dashboard/guidelines', '/guidelines', '/dashboard/sla-tracker'):
        return True

    return False


def sanitize_markdown_links(text: str, user_role: Optional[str] = None) -> str:
    """
    Validate all Markdown links [label](url).
    1. Removes executable / unsafe URL schemes (e.g. javascript:, data:, vbscript:) and protocol-relative (//).
    2. Verifies internal paths against NAVIGATION_CATALOGUE and user RBAC permissions.
       Unverified or unauthorized internal links are stripped down to their plain label.
    """
    if not text or not isinstance(text, str):
        return text

    def _replace_link(match):
        label = match.group(1)
        url = match.group(2).strip()

        # Reject unsafe schemes and protocol-relative URLs
        if re.match(r'^(javascript|data|vbscript):', url, re.IGNORECASE) or url.startswith('//'):
            return label

        # Check internal paths
        if url.startswith('/'):
            if not is_verified_destination_path(url, user_role=user_role):
                return label

        return match.group(0)

    # Match standard markdown link [label](url)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _replace_link, text)

