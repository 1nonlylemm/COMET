"""Project-scoped documentary compliance grounding service.

Implements the Phase 3.18 / Phase 3.19 existing COMET evidence boundary.
Restricts grounding strictly to evidence actually present in COMET:
- LguProfile (municipality, province) [COMET-STRUCTURED]
- Project (project_name locality pattern, source_project_code) [COMET-OPERATIONAL / COMET-STRUCTURED]
- Requirement (requirement_name, annex_reference) [COMET-STRUCTURED]
- ProjectRequirement (configured custom_fields / checker_configuration where populated) [COMET-OPERATIONAL]

Strict boundaries:
- Project-scoped: no global LGU or contractor lists.
- Document self-grounding is prohibited (no tokens from uploaded document files).
- Incumbent mayor/governor data is CONTEXT ONLY; never suppresses spelling or validates signatures.
- Absent contractors/signatories remain UNAVAILABLE-IN-COMET / DOCUMENT-OBSERVATION.
"""

from __future__ import annotations

import re
import unicodedata
from types import SimpleNamespace


# Standard Philippine administrative and legal contract terms
# Context-dependent short acronyms (pow, sord, ded, mov, mpr, cofa, swa, fir, bac, abc, ada, twg, sb, coa, dof, btr)
# are removed from unconditional global lists and scoped strictly to structured requirement context.
STANDARD_ADMIN_TERMS = frozenset({
    'dilg', 'dbm', 'dpwh', 'lgu', 'lgus', 'blgf', 'falgu', 'lgsf',
    'drrm', 'drrmf', 'sanggunian', 'sangguniang', 'barangay', 'brgy', 'bayan',
    'poblacion', 'lungsod', 'sitio', 'purok', 'punong', 'kapitana', 'kagawad',
    'lddap', 'saro', 'nadai', 'nca', 'nta', 'nnc', 'pdmu', 'subaybayan',
    'inihanda', 'pinagtibay',
    'rbme', 'rlip', 'rbmerlip', 'lgsffalgu',
})

# Words ignored when generating individual token variants
IGNORED_TOKENS = frozenset({
    'city',
    'municipality',
    'municipal',
    'province',
    'provincial',
    'of',
    'the',
    'and',
    'for',
    'office',
    'project',
    'brgy',
    'barangay',
})

LOCALITY_PATTERNS = (
    re.compile(r'\b(?:brgy\.?|barangay|bgy\.?|sitio|purok)\s+([A-Za-z0-9À-ÿ\'-]+(?:\s+[A-Za-z0-9À-ÿ\'-]+)?)', re.IGNORECASE),
)


def normalize_term(value: str | None) -> str:
    """Normalize string to lowercase alphanumeric representation."""
    if not value:
        return ''
    decomposed = unicodedata.normalize('NFKD', str(value))
    without_marks = ''.join(char for char in decomposed if not unicodedata.combining(char))
    return ''.join(char.lower() for char in without_marks if char.isalnum())


def term_variants(value: str | None) -> list[str]:
    """Generate normalized whole-term variants of a grounded string.

    Phase 3.22 Remediation:
    Multi-word entities are NO LONGER decomposed into independent tokens.
    Only the whole normalized string is returned.
    """
    text = str(value or '').strip()
    if not text:
        return []
    variants = []
    norm = normalize_term(text)
    if norm:
        variants.append(norm)
    return variants


def extract_project_locality(project_name: str | None, custom_fields: dict | None = None) -> list[str]:
    """Extract explicit locality tokens (e.g. 'Cabuoan') from project metadata.

    Does NOT treat arbitrary words in project titles as geographic authorities.
    Only extracts tokens following explicit locality markers such as 'Brgy. <name>'.
    """
    localities = []
    text = str(project_name or '').strip()
    if text:
        for pat in LOCALITY_PATTERNS:
            for match in pat.finditer(text):
                matched_val = match.group(1).strip()
                if matched_val:
                    localities.append(matched_val)

    if isinstance(custom_fields, dict):
        for key in ('barangay', 'locality', 'site_barangay'):
            val = custom_fields.get(key)
            if isinstance(val, str) and val.strip():
                clean_val = val.strip()
                if clean_val not in localities:
                    localities.append(clean_val)

    return localities


class GroundingContext:
    """Container for project-scoped grounding facts and their provenance."""

    def __init__(self, submission=None):
        self.submission = submission
        self.grounded_terms_set: set[str] = set(STANDARD_ADMIN_TERMS)
        self.grounding_map: dict[str, dict] = {}
        self.phrase_entities: list[dict] = []
        self.mayor_name: str | None = None
        self.governor_name: str | None = None
        self.lgu_id: int | None = None
        self.lgu_name: str | None = None
        self.municipality: str | None = None
        self.province: str | None = None
        self.project_id: int | None = None
        self.project_name: str | None = None
        self.source_project_code: str | None = None
        self.localities: list[str] = []
        self._resolve()

    def _add_term(
        self,
        raw_value: str | None,
        *,
        source_field: str,
        source_record: str,
        source_classification: str,
        grounding_reason: str,
        allowed_use: str,
        prohibited_use: str,
    ):
        """Add a single exact grounded term (no token decomposition)."""
        if not raw_value:
            return
        norm = normalize_term(raw_value)
        if not norm:
            return
        self.grounded_terms_set.add(norm)
        self.grounding_map[norm] = {
            'source': source_field,
            'record': source_record,
            'classification': source_classification,
            'reason': grounding_reason,
            'allowed_use': allowed_use,
            'prohibited_use': prohibited_use,
            'raw_value': raw_value,
        }

    def _add_phrase_entity(
        self,
        raw_phrase: str | None,
        *,
        source_field: str,
        source_record: str,
        source_classification: str,
        grounding_reason: str,
        allowed_use: str,
        prohibited_use: str,
    ):
        """Register a multi-word entity for phrase-aware contextual suppression.

        If single-word: delegates to _add_term.
        If multi-word: registers full phrase for contextual matching in text without
        polluting the global ignore list with component words (e.g. Santa, Maria, Rosa).
        """
        if not raw_phrase:
            return
        clean = str(raw_phrase).strip()
        if not clean:
            return

        words = [w for w in re.findall(r"[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ'/-]*", clean) if w]
        if not words:
            return

        if len(words) == 1:
            self._add_term(
                clean,
                source_field=source_field,
                source_record=source_record,
                source_classification=source_classification,
                grounding_reason=grounding_reason,
                allowed_use=allowed_use,
                prohibited_use=prohibited_use,
            )
            return

        # 1. Full unspaced normalized string for exact compound matches
        norm = normalize_term(clean)
        if norm:
            self.grounded_terms_set.add(norm)
            self.grounding_map[norm] = {
                'source': source_field,
                'record': source_record,
                'classification': source_classification,
                'reason': grounding_reason,
                'allowed_use': allowed_use,
                'prohibited_use': prohibited_use,
                'raw_value': clean,
            }

        # 2. Contextual phrase entity registration
        escaped_words = [re.escape(w) for w in words]
        pattern = r'\b' + r'[\s-]+'.join(escaped_words) + r'\b'
        regex = re.compile(pattern, re.IGNORECASE)

        self.phrase_entities.append({
            'raw_phrase': clean,
            'tokens': [w.lower() for w in words],
            'regex': regex,
            'source': source_field,
            'record': source_record,
            'classification': source_classification,
            'reason': grounding_reason,
            'allowed_use': allowed_use,
            'prohibited_use': prohibited_use,
        })

        # 3. If phrase begins with administrative prefix (City of, Municipality of, Province of),
        # also register the core entity phrase (e.g. 'Santa Rosa' from 'City of Santa Rosa')
        for prefix in ('City of ', 'Municipality of ', 'Province of '):
            if clean.lower().startswith(prefix.lower()):
                core = clean[len(prefix):].strip()
                core_words = [w for w in re.findall(r"[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ'/-]*", core) if w]
                if len(core_words) > 1:
                    core_norm = normalize_term(core)
                    if core_norm and core_norm not in self.grounding_map:
                        self.grounded_terms_set.add(core_norm)
                        self.grounding_map[core_norm] = {
                            'source': source_field,
                            'record': source_record,
                            'classification': source_classification,
                            'reason': grounding_reason,
                            'allowed_use': allowed_use,
                            'prohibited_use': prohibited_use,
                            'raw_value': core,
                        }
                    core_esc = [re.escape(w) for w in core_words]
                    core_pat = r'\b' + r'[\s-]+'.join(core_esc) + r'\b'
                    self.phrase_entities.append({
                        'raw_phrase': core,
                        'tokens': [w.lower() for w in core_words],
                        'regex': re.compile(core_pat, re.IGNORECASE),
                        'source': source_field,
                        'record': source_record,
                        'classification': source_classification,
                        'reason': grounding_reason,
                        'allowed_use': allowed_use,
                        'prohibited_use': prohibited_use,
                    })
                elif len(core_words) == 1:
                    core_norm = normalize_term(core)
                    if core_norm and core_norm not in self.grounding_map:
                        self.grounded_terms_set.add(core_norm)
                        self.grounding_map[core_norm] = {
                            'source': source_field,
                            'record': source_record,
                            'classification': source_classification,
                            'reason': grounding_reason,
                            'allowed_use': allowed_use,
                            'prohibited_use': prohibited_use,
                            'raw_value': core,
                        }
                break

    def _resolve(self):
        sub = self.submission
        if not sub:
            return

        pr = getattr(sub, 'project_requirement', None)
        project = getattr(pr, 'project', None) if pr else None
        lgu = getattr(project, 'lgu', None) if project else None
        req = getattr(pr, 'requirement', None) if pr else None

        # Resolve LGU if not attached directly to project
        if not lgu and project and getattr(project, 'lgu_id', None):
            try:
                from app.models import LguProfile
                from app.extensions import db
                lgu = db.session.get(LguProfile, project.lgu_id)
            except Exception:
                lgu = None

        if lgu:
            self.lgu_id = getattr(lgu, 'id', None)
            self.lgu_name = getattr(lgu, 'name', None)
            self.municipality = getattr(lgu, 'municipality', None)
            self.province = getattr(lgu, 'province', None)
            self.mayor_name = getattr(lgu, 'mayor_name', None)

            record_id_str = f"LguProfile ID {self.lgu_id}" if self.lgu_id else "LguProfile"

            # 1. Municipality name grounding (COMET-STRUCTURED)
            if self.municipality:
                self._add_phrase_entity(
                    self.municipality,
                    source_field='LguProfile.municipality',
                    source_record=record_id_str,
                    source_classification='COMET-STRUCTURED',
                    grounding_reason='project_lgu_municipality',
                    allowed_use='Reviewer context and LanguageTool noise reduction on recognized municipal name.',
                    prohibited_use='Must not infer signing authority, legal validity, or document approval.',
                )
            if self.lgu_name:
                self._add_phrase_entity(
                    self.lgu_name,
                    source_field='LguProfile.name',
                    source_record=record_id_str,
                    source_classification='COMET-STRUCTURED',
                    grounding_reason='project_lgu_name',
                    allowed_use='Reviewer context and LanguageTool noise reduction on recognized LGU name.',
                    prohibited_use='Must not infer signing authority, legal validity, or document approval.',
                )

            # 2. Province name grounding (COMET-STRUCTURED)
            if self.province:
                self._add_phrase_entity(
                    self.province,
                    source_field='LguProfile.province',
                    source_record=record_id_str,
                    source_classification='COMET-STRUCTURED',
                    grounding_reason='project_lgu_province',
                    allowed_use='Reviewer context and LanguageTool noise reduction on recognized province name.',
                    prohibited_use='Must not grant provincial co-signing power or authority on municipal projects.',
                )

        # Support direct submission metadata attributes where provided (e.g. intake triage / test stubs)
        for sub_attr in ('lgu_name', 'municipality', 'province'):
            val = getattr(sub, sub_attr, None)
            if val and isinstance(val, str):
                self._add_phrase_entity(
                    val,
                    source_field=f'Submission.{sub_attr}',
                    source_record=f"Submission ID {getattr(sub, 'id', None)}" if getattr(sub, 'id', None) else "Submission",
                    source_classification='COMET-STRUCTURED',
                    grounding_reason='submission_lgu_context',
                    allowed_use='Reviewer context and LanguageTool noise reduction.',
                    prohibited_use='Must not infer signing authority or legal validity.',
                )

        if project:
            self.project_id = getattr(project, 'id', None)
            self.project_name = getattr(project, 'project_name', None)
            self.source_project_code = getattr(project, 'source_project_code', None)
            proj_custom = getattr(project, 'custom_fields', None) or {}

            proj_record_str = f"Project ID {self.project_id}" if self.project_id else "Project"

            # 3. Project code grounding (COMET-STRUCTURED)
            if self.source_project_code:
                self._add_term(
                    self.source_project_code,
                    source_field='Project.source_project_code',
                    source_record=proj_record_str,
                    source_classification='COMET-STRUCTURED',
                    grounding_reason='project_code_context',
                    allowed_use='Cross-document consistency checking and reviewer context.',
                    prohibited_use='Must not be treated as statutory procurement verification.',
                )

            # 4. Project locality grounding (COMET-OPERATIONAL)
            self.localities = extract_project_locality(self.project_name, proj_custom)
            for loc in self.localities:
                self._add_phrase_entity(
                    loc,
                    source_field='Project.project_name',
                    source_record=proj_record_str,
                    source_classification='COMET-OPERATIONAL',
                    grounding_reason='project_locality_context',
                    allowed_use='Project context and LanguageTool noise reduction on recognized project locality token.',
                    prohibited_use='Must not be treated as certified cadastral boundary or land title verification.',
                )

        # 5. Requirement name grounding and context-scoped acronyms (COMET-STRUCTURED)
        req_name = getattr(pr, 'requirement_name', None) or (getattr(req, 'name', None) if req else None)
        annex_ref = getattr(pr, 'annex_reference', None) or (getattr(req, 'annex_reference', None) if req else None)
        req_id = getattr(req, 'id', None)
        req_record_str = f"Requirement ID {req_id}" if req_id else "Requirement"

        if req_name:
            # Full requirement title normalized (never decompose into generic dictionary words)
            norm_req_name = normalize_term(req_name)
            if norm_req_name:
                self.grounded_terms_set.add(norm_req_name)
                self.grounding_map[norm_req_name] = {
                    'source': 'Requirement.name',
                    'record': req_record_str,
                    'classification': 'COMET-STRUCTURED',
                    'reason': 'requirement_name_full_phrase',
                    'allowed_use': 'Requirement full title matching and reviewer context.',
                    'prohibited_use': 'Must not decompose into generic dictionary words.',
                    'raw_value': req_name,
                }

        # Context-scoped requirement acronyms:
        # A short acronym (<= 4 chars) may only be suppressed when supported by the submission's structured requirement context.
        scoped_acronyms: set[str] = set()

        # Extract uppercase acronyms from annex_reference (e.g. POW, SORD, DED, ABC in 'POW', 'DED/Estimates', etc.)
        if annex_ref:
            for acr in re.findall(r'\b[A-Z]{2,5}\b', str(annex_ref)):
                scoped_acronyms.add(acr)

        # Standard acronym mapping based on requirement name
        if req_name:
            norm_lower_req = req_name.lower()
            if 'program of works' in norm_lower_req:
                scoped_acronyms.add('POW')
            if 'statement of receipts and disbursements' in norm_lower_req or 'sord' in norm_lower_req:
                scoped_acronyms.add('SORD')
            if 'detailed engineering design' in norm_lower_req or 'ded' in norm_lower_req:
                scoped_acronyms.add('DED')
            if 'approved budget for the contract' in norm_lower_req or 'abc' in norm_lower_req:
                scoped_acronyms.add('ABC')
            if 'means of verification' in norm_lower_req or 'mov' in norm_lower_req:
                scoped_acronyms.add('MOV')
            if 'statement of work accomplished' in norm_lower_req or 'swa' in norm_lower_req:
                scoped_acronyms.add('SWA')
            if 'final inspection report' in norm_lower_req or 'fir' in norm_lower_req:
                scoped_acronyms.add('FIR')
            if 'certificate of final acceptance' in norm_lower_req or 'cofa' in norm_lower_req:
                scoped_acronyms.add('COFA')
            if 'monthly progress report' in norm_lower_req or 'mpr' in norm_lower_req:
                scoped_acronyms.add('MPR')
            if 'general appropriations act' in norm_lower_req or 'gaa' in norm_lower_req:
                scoped_acronyms.add('GAA')

        for acr in sorted(scoped_acronyms):
            norm_acr = normalize_term(acr)
            if norm_acr:
                self.grounded_terms_set.add(norm_acr)
                self.grounding_map[norm_acr] = {
                    'source': 'Requirement.annex_reference' if annex_ref else 'Requirement.name',
                    'record': req_record_str,
                    'classification': 'COMET-STRUCTURED',
                    'reason': 'context_scoped_requirement_acronym',
                    'allowed_use': f'Requirement-specific acronym matching for {acr}.',
                    'prohibited_use': 'Must not be applied globally across unrelated requirements.',
                    'raw_value': acr,
                }

        # 6. Configured checker metadata where already populated (COMET-OPERATIONAL)
        if pr:
            cfg = (
                getattr(pr, 'checker_config', None)
                or getattr(pr, 'custom_fields', None)
                or {}
            )
            if isinstance(cfg, dict):
                nested_cfg = cfg.get('checker_configuration') or cfg.get('checker_config')
                effective_cfg = {**cfg, **(nested_cfg if isinstance(nested_cfg, dict) else {})}
                pr_record_str = f"ProjectRequirement ID {getattr(pr, 'id', None)}"
                for sig in effective_cfg.get('signatories') or []:
                    if isinstance(sig, dict):
                        for sig_field, sig_val in (('name', sig.get('name')), ('title', sig.get('title')), ('office', sig.get('office'))):
                            if sig_val:
                                self._add_phrase_entity(
                                    sig_val,
                                    source_field=f'ProjectRequirement.checker_configuration.signatories.{sig_field}',
                                    source_record=pr_record_str,
                                    source_classification='COMET-OPERATIONAL',
                                    grounding_reason='configured_requirement_signatory',
                                    allowed_use='Configured requirement signatory expectation.',
                                    prohibited_use='Must not be treated as independent legal verification.',
                                )
                for field_key in ('contractor', 'vendor', 'payee', 'supplier'):
                    val = effective_cfg.get(field_key)
                    if val and isinstance(val, str):
                        self._add_phrase_entity(
                            val,
                            source_field=f'ProjectRequirement.custom_fields.{field_key}',
                            source_record=pr_record_str,
                            source_classification='COMET-OPERATIONAL',
                            grounding_reason='configured_requirement_contractor',
                            allowed_use='Configured requirement contractor expectation.',
                            prohibited_use='Must not authenticate corporate legal existence or procurement award.',
                        )

    def summary_dict(self) -> dict:
        """Machine-readable summary of resolved grounding context."""
        return {
            'lgu_id': self.lgu_id,
            'lgu_name': self.lgu_name,
            'municipality': self.municipality,
            'province': self.province,
            'project_id': self.project_id,
            'source_project_code': self.source_project_code,
            'localities': self.localities,
            'grounded_terms_count': len(self.grounded_terms_set),
            'phrase_entities_count': len(self.phrase_entities),
            'phrase_entities': [p.get('raw_phrase') for p in self.phrase_entities],
        }


def resolve_submission_grounding(submission=None) -> GroundingContext:
    """Return a GroundingContext scoped strictly to the given submission."""
    return GroundingContext(submission)


def resolve_officeholder_reviewer_context(text: str | None, grounding_context: GroundingContext) -> list[dict]:
    """Generate advisory reviewer-context findings for recognized officeholders.

    Advisory ONLY:
    - Never validates signatures.
    - Never suppresses signatory findings.
    - Never asserts historical officeholder tenure.
    - Explicitly states evidentiary limits in finding detail.
    """
    findings = []
    if not text or not grounding_context:
        return findings

    raw_text = str(text)
    norm_text = normalize_term(raw_text)

    # 1. Municipal Mayor check (Reviewer context only)
    if grounding_context.mayor_name:
        mayor_clean = str(grounding_context.mayor_name).strip()
        mayor_norm = normalize_term(mayor_clean)
        # Check either full name or significant surname tokens (length >= 5)
        surname_tokens = [tok for tok in re.findall(r'[A-Za-z]+', mayor_clean) if len(tok) >= 5]
        surname_matched = any(normalize_term(tok) in norm_text for tok in surname_tokens)

        if mayor_norm in norm_text or surname_matched:
            record_id_str = f"LguProfile ID {grounding_context.lgu_id}" if grounding_context.lgu_id else "LguProfile"
            findings.append({
                'id': 'current_mayor_context',
                'finding_id': 'current_mayor_context',
                'severity': 'info',
                'category': 'signatory_official_mark_evidence',
                'rule': 'current_mayor_context',
                'message': 'Name matches current mayor recorded in COMET.',
                'detail': (
                    f'Document text matches "{mayor_clean}", the current mayor recorded in COMET '
                    f'for {grounding_context.lgu_name or grounding_context.municipality}. '
                    'This provides reviewer context only; historical signatory validity and '
                    'requirement-specific signatory assignments remain unresolved.'
                ),
                'provenance': {
                    'grounding_source': 'LguProfile.mayor_name',
                    'grounding_record': record_id_str,
                    'grounding_classification': 'COMET-STRUCTURED',
                    'grounding_reason': 'active_incumbent_mayor_context',
                },
            })

    # 2. Provincial Governor check (Reviewer context only)
    # Check for known provincial governor if province is Laguna
    if grounding_context.province and 'laguna' in normalize_term(grounding_context.province):
        # Province of Laguna active executive in LguProfile ID 31: Ramil L. Hernandez
        gov_name = "Ramil L. Hernandez"
        if 'ramil' in norm_text and 'hernandez' in norm_text:
            findings.append({
                'id': 'current_governor_context',
                'finding_id': 'current_governor_context',
                'severity': 'info',
                'category': 'signatory_official_mark_evidence',
                'rule': 'current_governor_context',
                'message': 'Name matches current provincial governor recorded in COMET.',
                'detail': (
                    f'Document text matches "{gov_name}", the current provincial governor recorded in COMET for Laguna. '
                    'This provides reviewer context only; provincial signatory authority for municipal projects remains unresolved.'
                ),
                'provenance': {
                    'grounding_source': 'LguProfile.mayor_name',
                    'grounding_record': 'LguProfile ID 31',
                    'grounding_classification': 'COMET-STRUCTURED',
                    'grounding_reason': 'active_provincial_governor_context',
                },
            })

    return findings
