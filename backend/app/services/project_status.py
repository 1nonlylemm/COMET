CANONICAL_PROJECT_STATUSES = ('not_yet_started', 'ongoing', 'completed', 'cancelled')

PROJECT_STATUS_LABELS = {
    'not_yet_started': 'Not Yet Started',
    'ongoing': 'Ongoing',
    'completed': 'Completed',
    'cancelled': 'Cancelled',
}

PROJECT_STATUS_ALIASES = {
    'active': 'ongoing',
    'on going': 'ongoing',
    'on-going': 'ongoing',
    'ongoing': 'ongoing',
    'in progress': 'ongoing',
    'implemented': 'ongoing',
    'implementation': 'ongoing',
    'not started': 'not_yet_started',
    'not yet started': 'not_yet_started',
    'not yet completed': 'not_yet_started',
    'not_yet_started': 'not_yet_started',
    'n a': 'not_yet_started',
    'na': 'not_yet_started',
    'n/a': 'not_yet_started',
    'draft': 'not_yet_started',
    'drafted': 'not_yet_started',
    'no nadai released': 'not_yet_started',
    'no nadai released yet': 'not_yet_started',
    'for submission': 'not_yet_started',
    'completed': 'completed',
    'complete': 'completed',
    'done': 'completed',
    '100': 'completed',
    'cancelled': 'cancelled',
    'canceled': 'cancelled',
    'cancel': 'cancelled',
    'terminated': 'cancelled',
    'suspended': 'cancelled',
}

LEGACY_PROJECT_STATUS_MIGRATION = {
    'active': 'ongoing',
    'suspended': 'cancelled',
    'terminated': 'cancelled',
    'completed': 'completed',
    'archived': 'completed',
}


def normalize_status_text(value):
    if value is None:
        return ''
    text = str(value).strip().lower()
    text = text.replace('&', ' and ')
    text = text.replace('_', ' ')
    text = text.replace('-', ' ')
    return ' '.join(text.split())


def normalize_project_status(value, default=None):
    normalized = normalize_status_text(value)
    if not normalized:
        return default
    if normalized in CANONICAL_PROJECT_STATUSES:
        return normalized
    if normalized in PROJECT_STATUS_ALIASES:
        return PROJECT_STATUS_ALIASES[normalized]
    if normalized.startswith('ongoing') or normalized.startswith('on going'):
        return 'ongoing'
    if 'not yet started' in normalized or 'not started' in normalized:
        return 'not_yet_started'
    if 'cancel' in normalized or 'terminat' in normalized:
        return 'cancelled'
    if 'suspend' in normalized:
        return 'cancelled'
    if 'complete' in normalized and 'not yet' not in normalized:
        return 'completed'
    if 'draft' in normalized or 'nadai' in normalized or 'pre imple' in normalized:
        return 'not_yet_started'
    return default


def project_status_label(value):
    return PROJECT_STATUS_LABELS.get(value, str(value or '').replace('_', ' ').title())


ACTION_BUCKETS = (
    {
        'key': 'monthly_accomplishment',
        'label': 'Monthly Accomplishment',
        'short_label': 'Monthly',
        'keywords': ('monthly accomplishment', 'encode monthly', 'update monthly', 'encode/update'),
    },
    {
        'key': 'rpmes_form_2',
        'label': 'RPMES Form 2',
        'short_label': 'Form 2',
        'keywords': ('rpmes form 2', 'form 2'),
    },
    {
        'key': 'form_4_coc',
        'label': 'RPMES Form 4 / COC',
        'short_label': 'Form 4 / COC',
        'keywords': ('rpmes form 4', 'form 4', 'coc'),
    },
    {
        'key': 'pre_implementation_docs',
        'label': 'Pre-Implementation Docs',
        'short_label': 'Pre-imple',
        'keywords': ('pre imple', 'pre-imple', 'pre implementation', 'pre-implementation'),
    },
    {
        'key': 'nadai_pending',
        'label': 'NADAI Pending',
        'short_label': 'NADAI',
        'keywords': ('nadai',),
    },
    {
        'key': 'subaybayan_comment',
        'label': 'SubayBAYAN Comments',
        'short_label': 'Comments',
        'keywords': ('comment in subaybayan', 'comment of ro/co', 'ro/co', 'subaybayan comment'),
    },
    {
        'key': 'fund_return_proof',
        'label': 'Fund Return Proof',
        'short_label': 'Fund return',
        'keywords': ('proof of fund return', 'fund return'),
    },
)


def classify_monitoring_action(text):
    normalized = normalize_status_text(text)
    if not normalized:
        return None
    for bucket in ACTION_BUCKETS:
        if any(keyword in normalized for keyword in bucket['keywords']):
            return bucket['key']
    return None

