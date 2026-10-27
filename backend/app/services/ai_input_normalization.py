"""Tolerate small command typos without rewriting user data or confirmations."""
import re


ENTITIES = {
    'project', 'projects', 'program', 'programs', 'cluster', 'clusters',
    'requirement', 'requirements', 'deadline', 'deadlines', 'notice', 'notices',
    'report', 'reports', 'document', 'documents', 'inspection', 'inspections',
    'monitoring', 'compliance', 'available', 'current', 'fiscal',
}
ACTIONS = {'create', 'update', 'edit', 'rename', 'assign', 'show', 'list', 'find', 'change'}
KNOWN = ENTITIES | ACTIONS
ALIASES = {'programme': 'program', 'programmes': 'programs'}

# Quoted names, structured payloads, identifiers and field values are literal
# data. A misspelling in a project name must survive a create/update request.
PROTECTED = re.compile(
    r'"[^"\n]*"|(?<!\w)\x27[^\x27\n]*\x27|`[^`]*`|\{[\s\S]*\}'
    r'|https?://\S+|[\w.+-]+@[\w.-]+'
    r'|\b[a-zA-Z0-9]+(?:[-_/][a-zA-Z0-9]+)+\b'
)
NAMED_VALUE = re.compile(
    r'\b(?:named|called|titled|name\s+it(?:\s+as)?)\s+(.+?)'
    r'(?=\s+(?:under|for|in|with|fy|fiscal\s+year)\b|[,;\n]|$)', re.I
)
FIELD_VALUE = re.compile(
    r'\b(?:name|code|description|notes|remarks|email|phone)\s*(?::|=|\bto\b|\bis\b)\s*([^\n]+)', re.I
)


def _one_edit(left, right):
    """One insertion, deletion, substitution or adjacent transposition."""
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        if len(differences) == 1:
            return True
        return (len(differences) == 2 and differences[1] == differences[0] + 1
                and left[differences[0]] == right[differences[1]]
                and left[differences[1]] == right[differences[0]])
    short, long = sorted((left, right), key=len)
    for index in range(len(long)):
        if long[:index] + long[index + 1:] == short:
            return True
    return False


def normalize_routing_text(message):
    """Return a routing copy and its corrections; callers store the original."""
    text = message or ''
    spans = [match.span() for match in PROTECTED.finditer(text)]
    spans += [match.span(1) for pattern in (NAMED_VALUE, FIELD_VALUE) for match in pattern.finditer(text)]
    corrections = []

    def replace(match):
        original = match.group()
        word = original.casefold()
        if any(start <= match.start() < end for start, end in spans):
            return original
        replacement = ALIASES.get(word)
        if word not in KNOWN and replacement is None and len(word) >= 4:
            prefix = text[:match.start()].strip().casefold()
            action_position = bool(re.fullmatch(r'(?:(?:please|can|could|would|you|i|want|need|to)\s*)*', prefix))
            choices = [candidate for candidate in ENTITIES | (ACTIONS if action_position else set())
                       if _one_edit(word, candidate)]
            if len(choices) == 1:
                replacement = choices[0]
        # "Create a projects" names one record; retain true plural requests
        # such as "show all projects" and "update all projects".
        candidate = replacement or word
        if candidate.endswith('s') and candidate[:-1] in ENTITIES and re.search(r'\b(?:a|an|one|single)\s+$', text[:match.start()], re.I):
            replacement = candidate[:-1]
        if not replacement or replacement == word:
            return original
        if original.isupper():
            replacement = replacement.upper()
        elif original.istitle():
            replacement = replacement.title()
        corrections.append({'original': original, 'normalized': replacement})
        return replacement

    return re.sub(r'\b[a-zA-Z]+\b', replace, text), corrections
