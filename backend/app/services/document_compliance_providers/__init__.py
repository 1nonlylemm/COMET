"""AWS provider adapter registry for the documentary compliance checker.

The registry is intentionally empty by default. No real providers ship in this
spec; this module establishes the seam so future AWS Textract / Rekognition
adapters can be wired in without rewriting the rule engine. See §10A of
``references/DOCUMENTARY_COMPLIANCE_CHECKER.md`` for the policy contract.

Usage::

    from app.services.document_compliance_providers import registry

    adapter = registry.get('aws-textract')
    if adapter is not None:
        result = adapter.analyze_document(file_path)

The checker MUST treat provider output as advisory and MUST persist provider
metadata into ``score_details['provider_metadata']`` whenever an adapter
actually produced output. Failures degrade to ``review_required`` per §10A.
"""

from __future__ import annotations

from .base import BaseProviderAdapter, ProviderError, ProviderResult


class ProviderRegistry:
    """In-memory AWS provider adapter registry.

    Adapters are keyed by a short AWS provider name such as ``'aws-textract'``
    or ``'aws-rekognition'``. The registry never auto-registers anything;
    callers must opt in via :meth:`register`.
    """

    SUPPORTED_NAMES = frozenset({
        'aws-textract',
        'aws-textract-analyze-expense',
        'aws-rekognition',
    })

    def __init__(self):
        self._adapters: dict[str, BaseProviderAdapter] = {}

    def register(self, name, adapter):
        """Register ``adapter`` under ``name``.

        Raises:
            TypeError: when ``adapter`` is not a :class:`BaseProviderAdapter`.
            ValueError: when ``name`` is empty.
        """
        if not isinstance(adapter, BaseProviderAdapter):
            raise TypeError('adapter must subclass BaseProviderAdapter')
        normalized = str(name or '').strip().lower()
        if not normalized:
            raise ValueError('Provider name must be a non-empty string.')
        if normalized not in self.SUPPORTED_NAMES:
            supported = ', '.join(sorted(self.SUPPORTED_NAMES))
            raise ValueError(f'Unsupported document compliance provider. Use one of: {supported}.')
        self._adapters[normalized] = adapter

    def unregister(self, name):
        """Remove ``name`` from the registry. Idempotent."""
        self._adapters.pop(str(name or '').strip().lower(), None)

    def get(self, name):
        """Return the adapter registered for ``name`` or ``None``."""
        return self._adapters.get(str(name or '').strip().lower())

    def names(self):
        """Return the registered adapter names as a tuple."""
        return tuple(sorted(self._adapters))

    def clear(self):
        """Drop every registered adapter. Useful for tests."""
        self._adapters.clear()


registry = ProviderRegistry()


def collect_provider_metadata(results):
    """Aggregate :class:`ProviderResult` objects into a list payload.

    Returns the input as a list of dicts ready for inclusion in
    ``score_details['provider_metadata']``. ``None`` entries are skipped so the
    service can pass through a mixed list without filtering first.
    """
    payload = []
    for item in results or ():
        if item is None:
            continue
        if isinstance(item, ProviderResult):
            payload.append(item.to_dict())
        elif isinstance(item, dict):
            payload.append(dict(item))
    return payload


__all__ = [
    'BaseProviderAdapter',
    'ProviderError',
    'ProviderRegistry',
    'ProviderResult',
    'collect_provider_metadata',
    'registry',
]
