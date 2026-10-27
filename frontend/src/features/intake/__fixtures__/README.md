# Intake Test Fixtures Provenance

## `productionCompliancePayloads.json`

### Provenance Classification:
**Serialized snapshots produced by live `document_compliance_service.run_submission_check()`**

### Purpose:
This fixture provides frozen, serialized outputs of the COMET Document Checker pipeline execution against the 6 physical benchmark PDF variants (`BENCH_01_ARITHMETIC` through `BENCH_06_MISSING_SIGNATORY`). It is consumed by frontend integration tests (e.g. `ReviewerEvidencePreview.integration.test.jsx`) to verify that reviewer UI components render deterministic findings, bounding box overlays, and AI plain-language explanations correctly.

### Explicit Non-Claims:
This dataset is **NOT**:
- A live API response (tests consume this file statically from disk, not over an HTTP socket).
- A browser E2E fixture (tests execute in Vitest + JSDOM, not an actual browser).
- A general production dataset.
- A checker accuracy dataset.

### Sensitive Data Audit:
- Contains zero API keys, passwords, bearer tokens, or provider secrets.
- All benchmark variants and file hashes correspond to the synthetic/controlled test corpus in `backend/tests/fixtures/phase3_4_variants/`.
