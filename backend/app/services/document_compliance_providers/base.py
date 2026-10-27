"""Base classes for AWS documentary compliance provider adapters.

Adapters wrap AWS Textract and AWS Rekognition behind a uniform interface so
the checker can call them without leaking provider-specific details into the
rule engine. See §10A of
``references/DOCUMENTARY_COMPLIANCE_CHECKER.md`` for the policy contract.

Real adapters are not shipped in this spec; this module only sets the seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


class ProviderError(Exception):
    """Raised by adapters when a remote provider call fails.

    The checker translates this into a ``review_required`` outcome with a
    descriptive finding rather than failing the intake upload.
    """


@dataclass
class ProviderResult:
    """Result envelope returned by adapters.

    Attributes:
        name: Adapter name (for example ``'aws-textract'`` or ``'aws-rekognition'``).
        version: Provider model or API version (e.g. ``'2024-09-30'``).
        region: Provider region when applicable. May be ``None``.
        confidence: 0.0–1.0 confidence reported by the provider, when known.
        errors: Sequence of human-readable error strings (empty on success).
        payload: Provider-specific structured output. Treated as advisory by
            the checker; the rule engine never trusts it as proof of
            compliance.
    """

    name: str
    version: str = ''
    region: str | None = None
    confidence: float | None = None
    errors: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class BaseProviderAdapter:
    """Optional methods are exposed by individual adapters as needed.

    Subclasses MUST set ``name``. ``version`` and ``region`` are optional and
    surface in ``ProviderResult`` for audit. All four data-extraction methods
    raise :class:`NotImplementedError` by default so subclasses opt into the
    capabilities they actually support.
    """

    name: str = ''
    version: str = ''
    region: str | None = None

    def extract_text(self, file_path):
        raise NotImplementedError(f'{self.__class__.__name__}.extract_text is not implemented')

    def analyze_document(self, file_path):
        raise NotImplementedError(f'{self.__class__.__name__}.analyze_document is not implemented')

    def analyze_expense(self, file_path):
        raise NotImplementedError(f'{self.__class__.__name__}.analyze_expense is not implemented')

    def detect_objects(self, image_path):
        raise NotImplementedError(f'{self.__class__.__name__}.detect_objects is not implemented')


__all__ = ['BaseProviderAdapter', 'ProviderError', 'ProviderResult']
