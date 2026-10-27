"""Source-backed document definitions and bounded evidence selection for matching.

Profiles describe document identity, not whether it is mandatory or compliant.
The project's existing eligible candidates remain the authorization boundary.
"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'reference_data/matcher_requirement_profiles.json'


@lru_cache(maxsize=1)
def _catalog():
    data = CATALOG_PATH.read_bytes()
    catalog = json.loads(data)
    return catalog, hashlib.sha256(data).hexdigest()


def catalog_metadata():
    catalog, digest = _catalog()
    return {'version': catalog['version'], 'sha256': digest, 'sources': catalog['sources']}


def requirement_profile(candidate):
    """Match descriptive titles, never an unqualified annex letter alone."""
    catalog, _ = _catalog()
    name = str(candidate.get('requirement_name') or '')
    for profile in catalog['profiles']:
        if any(re.search(pattern, name, re.I) for pattern in profile['name_patterns']):
            return {key: profile[key] for key in ('id', 'definition', 'distinguishing_evidence', 'contrasts', 'sources')}
    return None


EVIDENCE_PATTERNS = (
    (13, r'\bfor\s+payment\s+of\s*:?\s*(?:\d+(?:\.\d+)?\s*%\s*)?(?:progress|final|contractor)\s+billing\b'),
    # Select the operative distinction even when repeated generic references occur earlier.
    (12, r'\b(?:transferred|transfer|recorded|credited).{0,180}\btrust\s+(?:fund|account)\b'),
    (11, r'\btrust\s+(?:fund|account)\b'),
    (10, r'\bnotice\s+of\s+authority\s+to\s+debit\s+account\s+issued\b'),
    (10, r'\b(?:resolved|resolves|hereby\s+authoriz\w*|authoriz\w*\s+the\s+(?:implementation|mayor|governor))\b'),
    (9, r'\b(?:certificate\s+of\s+(?:final\s+acceptance|completion)|statement\s+of\s+(?:work\s+accomplished|receipts\s+and\s+disbursements))\b'),
    (9, r'\b(?:invitation\s+to\s+bid|bid\s+notice\s+abstract|notice\s+to\s+(?:implement|proceed)|notice\s+of\s+award)\b'),
    (8, r'\b(?:local\s+development\s+investment\s+program|annual\s+investment\s+program|detailed\s+engineering\s+design|program\s+of\s+works?)\b'),
    (8, r'\b(?:confirm\w*|certify|acknowledg\w*).{0,110}\b(?:received|receipt)\b'),
    (7, r'\b(?:classification\s*:?\s*goods|proof\s+of\s+return|not\s+funded\s+(?:by|from)|no\s+other\s+source)\b'),
)


def select_document_evidence(redacted_text, limit=1800):
    """Keep the text budget fixed, with ranges in the redacted document.

    Page numbers are emitted only when explicit form-feed boundaries exist.
    Offsets refer to redacted text, never to the original unredacted document.
    """
    text = str(redacted_text or '')
    if not text.strip():
        return {'excerpt': '', 'segments': [], 'text_truncated': False, 'text_available': False}
    spans = [(0, min(len(text), 450), 100)]
    for priority, pattern in EVIDENCE_PATTERNS:
        matches = list(re.finditer(pattern, text, re.I | re.S))
        # Two occurrences can distinguish a cover letter from its enclosed notice.
        for match in matches[:2]:
            spans.append((max(0, match.start()-100), min(len(text), match.end()+170), priority))
    spans.append((max(0, len(text)-220), len(text), 1))
    chosen, budget = [], max(0, limit-100)
    for start, end, priority in sorted(spans, key=lambda s: (-s[2], s[0])):
        uncovered = [(start, end)]
        for lo, hi in chosen:
            remaining = []
            for a, b in uncovered:
                if b <= lo or a >= hi:
                    remaining.append((a, b))
                else:
                    if a < lo:
                        remaining.append((a, lo))
                    if b > hi:
                        remaining.append((hi, b))
            uncovered = remaining
        for a, b in uncovered:
            if budget <= 0:
                break
            b = min(b, a+budget)
            chosen.append((a, b))
            budget -= b-a
    # Short documents should be supplied completely, including non-pattern text.
    if len(text) <= limit:
        chosen = [(0, len(text))]
    chosen.sort()
    merged = []
    for a, b in chosen:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    segments = []
    remaining = max(0, limit)
    for a, b in merged:
        start = a
        for part in text[a:b].split('\f'):
            separator_cost = 5 if segments else 0
            available = max(0, remaining-separator_cost)
            end = start+min(len(part), available)
            if end > start:
                segments.append({'start': start, 'end': end, 'text': text[start:end],
                                 'page': text[:start].count('\f')+1 if '\f' in text else None})
                remaining -= separator_cost+end-start
            start += len(part)+1
    return {'excerpt': '\n[…]\n'.join(s['text'] for s in segments), 'segments': segments,
            'text_truncated': sum(s['end']-s['start'] for s in segments) < len(text.replace('\f','')), 'text_available': True}
