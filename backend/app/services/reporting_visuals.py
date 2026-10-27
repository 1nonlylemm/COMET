"""Dependency-free, print-safe SVG charts for the reporting template."""

from html import escape
from math import cos, sin, pi


# Keep in sync with frontend/src/lib/projectStatus.js
STATUS_COLORS = {
    'not_yet_started': '#f59e0b',
    'ongoing': '#3b82f6',
    'completed': '#10b981',
    'cancelled': '#ef4444',
}
DOCUMENT_SEGMENTS = (
    ('pending', 'Pending', '#f59e0b'),
    ('under_review', 'Under Review', '#3b82f6'),
    ('non_compliant', 'Non-Compliant', '#f43f5e'),
    ('compliant', 'Compliant', '#10b981'),
    ('waived', 'Waived', '#64748b'),
)


def status_pie_svg(items):
    """Render actual counts, including full-circle and empty-cohort cases."""
    total = sum(item.get('count', 0) or 0 for item in items)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 220" '
             'width="170" height="170" role="img" aria-label="Project implementation status distribution">']
    angle = -pi / 2
    if not total:
        parts.append('<circle cx="110" cy="110" r="100" fill="#e2e8f0"/>')
    for item in items:
        count = item.get('count', 0) or 0
        if count <= 0:
            continue
        color = STATUS_COLORS.get(item.get('key'), '#64748b')
        title = escape(f"{item.get('label', '')}: {count} ({count / total * 100:.1f}%)")
        if count == total:
            parts.append(f'<circle cx="110" cy="110" r="100" fill="{color}"><title>{title}</title></circle>')
        else:
            end = angle + 2 * pi * count / total
            x1, y1 = 110 + 100 * cos(angle), 110 + 100 * sin(angle)
            x2, y2 = 110 + 100 * cos(end), 110 + 100 * sin(end)
            path = f'M110,110 L{x1:.5f},{y1:.5f} A100,100 0 {int(count / total > .5)},1 {x2:.5f},{y2:.5f} Z'
            parts.append(f'<path d="{path}" fill="{color}"><title>{title}</title></path>')
        angle += 2 * pi * count / total
    parts.append('</svg>')
    return ''.join(parts)


def documentary_breakdown(summary):
    """Waived remains applicable but never counts as compliant; N/A is separate."""
    segments = [dict(key=key, label=label, color=color, count=summary.get(key, 0) or 0)
                for key, label, color in DOCUMENT_SEGMENTS]
    applicable = summary.get('applicable')
    if applicable is None:
        applicable = sum(segment['count'] for segment in segments)
    compliant = summary.get('compliant', 0) or 0
    open_count = sum(summary.get(key, 0) or 0 for key in ('pending', 'under_review', 'non_compliant'))
    for segment in segments:
        segment['percentage'] = segment['count'] / applicable * 100 if applicable else 0
    return dict(segments=segments, applicable=applicable, compliant=compliant,
                open=open_count, not_applicable=summary.get('not_applicable', 0) or 0,
                rate=round(compliant / applicable * 100, 1) if applicable else None)
