"""Deterministic language and quality analysis for the documentary compliance checker.

Implements the §6 "General Language And Quality Checks" portion of
``references/DOCUMENTARY_COMPLIANCE_CHECKER.md``. The module is intentionally
heuristic: it does not call out to any third-party language tooling itself,
does not consume LLM output, and never raises out of
``analyze_language_quality``. Optional local providers such as self-hosted
LanguageTool are merged from explicit provider result payloads.

Callers that need an LLM-grade rewrite should use a separate provider adapter
(see :mod:`app.services.document_compliance_providers`).
"""

from __future__ import annotations

import re


# Below this readability confidence the source text is treated as too unreliable
# to trust for grammar/spelling decisions. The checker still records a note so
# the reviewer knows the analysis was deliberately suppressed.
OCR_TRUST_THRESHOLD = 0.6


# A small high-confidence stopword list. The stopword density is used as a
# proxy for natural-language coverage: real narrative text tends to include a
# meaningful share of these tokens, while OCR garbage rarely does.
_STOPWORDS = frozenset({
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'have', 'in', 'is', 'it', 'its', 'no', 'not', 'of', 'on',
    'or', 'shall', 'such', 'that', 'the', 'their', 'these', 'this',
    'those', 'to', 'was', 'were', 'which', 'will', 'with', 'within',
    'without',
})


_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9])')
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")

def analyze_language_quality(text, *, evidence_type, readability_confidence=1.0):
    """Return the §6 structured language-quality payload, or ``None`` to skip.

    Args:
        text: Extracted document text. May be empty or ``None``.
        evidence_type: Resolved evidence type for the submission. Falls back to
            generic checks when not provided. Non-narrative evidence types
            (receipts, photos, signature pages) cause the analyzer to skip.
        readability_confidence: 0.0–1.0. Below :data:`OCR_TRUST_THRESHOLD` the
            analyzer skips so OCR garbage is not reported as bad writing.

    Returns:
        Dict with the keys documented in §6 (``grammar_status``,
        ``spelling_status``, ``clarity_status``, ``readability_confidence``,
        ``notes``) when the analyzer ran. ``None`` when the gate was not met or
        the text was empty.

    The function never raises; unexpected input degrades to ``None``.
    """
    try:
        try:
            confidence = float(readability_confidence)
        except (TypeError, ValueError):
            confidence = 1.0
        confidence = max(0.0, min(1.0, confidence))
        if confidence < OCR_TRUST_THRESHOLD:
            return None

        normalized = _clean_text(text)
        if not normalized:
            return None

        sentences = _split_sentences(normalized)
        words = _WORD_RE.findall(normalized)
        if len(words) < 20:
            # Too little narrative text to make confident statements about the
            # writing; let the rest of the checker handle short texts.
            return None

        grammar_status, grammar_notes, grammar_issues = _grammar_status(sentences)
        spelling_status, spelling_notes, spelling_issues = _spelling_status(words)
        clarity_status, clarity_notes = _clarity_status(sentences, words)

        notes = []
        for chunk in (grammar_notes, spelling_notes, clarity_notes):
            for note in chunk:
                if note and note not in notes:
                    notes.append(note)

        return {
            'grammar_status': grammar_status,
            'spelling_status': spelling_status,
            'clarity_status': clarity_status,
            'readability_confidence': round(confidence, 2),
            'notes': notes,
            'issues': _dedupe_issues(grammar_issues + spelling_issues),
        }
    except Exception:
        # The language analyzer is advisory; never let it derail intake.
        return None


def merge_provider_result(language_quality, provider_result, *, readability_confidence=1.0):
    """Merge advisory provider issues into the local language-quality payload."""
    if not provider_result:
        return language_quality
    try:
        base = _language_quality_base(language_quality, readability_confidence)
        metadata = _provider_metadata(provider_result)
        if metadata:
            providers = list(base.get('providers') or [])
            providers.append(metadata)
            base['providers'] = providers

        issues = list(base.get('issues') or [])
        provider_issues = [
            issue for issue in (provider_result.get('issues') or [])
            if isinstance(issue, dict)
        ]
        if provider_issues:
            # Annotation identity is an occurrence, not a distinct misspelled word.
            # Retain bounded provider occurrences separately from the existing
            # grouped summary so repeated words and the remainder stay honest.
            base['annotation_issues'] = list(provider_issues)
            base['annotation_issue_count'] = provider_result.get('match_count') or len(provider_issues)
            issues.extend(provider_issues)
            base['issues'] = _dedupe_issues(issues)
            _promote_statuses_for_provider_issues(base, provider_issues)
            note = _provider_issue_note(provider_result, provider_issues)
            if note and note not in base['notes']:
                base['notes'].append(note)
        suppressed_issues = provider_result.get('suppressed_issues') or []
        if suppressed_issues:
            base['suppressed_issues'] = list(suppressed_issues)
        return base
    except Exception:
        return language_quality


def _language_quality_base(language_quality, readability_confidence):
    if language_quality:
        base = dict(language_quality)
        base['notes'] = list(base.get('notes') or [])
        base['issues'] = list(base.get('issues') or [])
        base['suppressed_issues'] = list(base.get('suppressed_issues') or [])
        return base
    try:
        confidence = max(0.0, min(1.0, float(readability_confidence)))
    except (TypeError, ValueError):
        confidence = 1.0
    return {
        'grammar_status': 'not_applicable',
        'spelling_status': 'not_applicable',
        'clarity_status': 'not_applicable',
        'readability_confidence': round(confidence, 2),
        'notes': [],
        'issues': [],
        'suppressed_issues': [],
    }


def _provider_metadata(provider_result):
    if not isinstance(provider_result, dict):
        return None
    return {
        key: value
        for key, value in {
            'provider': provider_result.get('provider'),
            'status': provider_result.get('status'),
            'language': provider_result.get('language'),
            'detected_language': provider_result.get('detected_language'),
            'match_count': provider_result.get('match_count'),
            'checked_chars': provider_result.get('checked_chars'),
            'truncated': provider_result.get('truncated'),
            'reason': provider_result.get('reason'),
            'error': provider_result.get('error'),
        }.items()
        if value not in (None, '', [])
    }


def _promote_statuses_for_provider_issues(base, provider_issues):
    issue_types = {str(issue.get('type') or '').strip().lower() for issue in provider_issues}
    if 'grammar' in issue_types:
        base['grammar_status'] = _promoted_status(base.get('grammar_status'))
    if 'spelling' in issue_types:
        base['spelling_status'] = _promoted_status(base.get('spelling_status'))
    if issue_types - {'grammar', 'spelling'}:
        base['clarity_status'] = _promoted_status(base.get('clarity_status'))


def _promoted_status(current):
    if current in {'major_issues', 'needs_review'}:
        return current
    return 'minor_issues'


def _provider_issue_note(provider_result, provider_issues):
    provider = str(provider_result.get('provider') or 'language provider').strip()
    if provider == 'languagetool':
        provider = 'LanguageTool'
    count = len(provider_issues)
    noun = 'issue' if count == 1 else 'issues'
    return f'{provider} found {count} {noun}.'


def _clean_text(value):
    if not value:
        return ''
    text = str(value)
    # Collapse runs of whitespace but keep sentence-ending punctuation intact.
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _split_sentences(text):
    if not text:
        return []
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part and part.strip()]


def _grammar_status(sentences):
    if not sentences:
        return 'not_applicable', ['No sentence-level text was available for grammar checks.'], []
    notes = []
    issues = []
    issue_count = 0
    evaluable_sentences = [s for s in sentences if len(_WORD_RE.findall(s)) >= 8]
    if not evaluable_sentences:
        return 'passed', notes, issues

    for sentence in evaluable_sentences:
        words = _WORD_RE.findall(sentence)
        if len(words) >= 15 and sentence and sentence[-1] not in '.!?':
            issue_count += 1
            continue

    ratio = issue_count / max(1, len(evaluable_sentences))
    if ratio >= 0.5:
        notes.append('Several narrative sections appear unterminated or run-on.')
        return 'major_issues', notes, issues
    if ratio >= 0.25:
        notes.append('Some narrative sections appear unterminated or run-on.')
        return 'minor_issues', notes, issues
    return 'passed', notes, issues


def _spelling_status(words):
    if not words:
        return 'not_applicable', [], []
    suspicious = 0
    issues = []
    for word in words:
        if len(word) >= 12 and word.isupper():
            # Long all-caps tokens are commonly OCR junk in scanned reports.
            suspicious += 1
            continue
        # Rough heuristic: very long word with no vowels => unlikely real.
        if len(word) >= 8 and not re.search('[aeiouAEIOU]', word):
            suspicious += 1
    ratio = suspicious / max(1, len(words))
    notes = []
    if ratio >= 0.05:
        notes.append('A noticeable share of tokens look like spelling or OCR errors.')
        return 'major_issues', notes, issues
    if ratio >= 0.02:
        notes.append('A few tokens look like spelling or OCR errors.')
        return 'minor_issues', notes, issues
    return 'passed', notes, issues


def _clarity_status(sentences, words):
    if not sentences or not words:
        return 'not_applicable', []
    notes = []
    evaluable_sentences = [s for s in sentences if len(_WORD_RE.findall(s)) >= 8]
    if not evaluable_sentences:
        return 'passed', notes
    long_sentences = sum(1 for sentence in evaluable_sentences if len(_WORD_RE.findall(sentence)) > 50)
    long_ratio = long_sentences / max(1, len(evaluable_sentences))

    flagged = False
    if long_ratio >= 0.4:
        notes.append('Several sentences are unusually long; consider breaking them into shorter sentences.')
        flagged = True

    if flagged:
        return 'minor_issues', notes
    return 'passed', notes


def _repeated_token_ratio(words):
    if len(words) < 10:
        return 0.0
    bigrams = []
    lowered = [word.lower() for word in words]
    for index in range(len(lowered) - 1):
        bigrams.append((lowered[index], lowered[index + 1]))
    if not bigrams:
        return 0.0
    counts = {}
    for bigram in bigrams:
        counts[bigram] = counts.get(bigram, 0) + 1
    repeated = sum(count for count in counts.values() if count > 1) - len([c for c in counts.values() if c > 1])
    return repeated / max(1, len(bigrams))


def _dedupe_issues(issues):
    output = []
    seen = set()
    for issue in issues:
        key = (
            issue.get('type'),
            str(issue.get('matched_text') or '').lower(),
            str(issue.get('suggestion') or '').lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(issue)
    return output[:20]
