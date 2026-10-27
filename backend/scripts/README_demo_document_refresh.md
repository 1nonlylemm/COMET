# Generated demo submission documents

`documentary_seed_document_generator.generate_seed_document()` now uses the shared
`document_fixture_generator` A4 layout through `demo_seed_rendering`. Both the
original demo seeder and its 2026 expansion supply the actual requirement, project,
LGU, fiscal year, allocation and document date. PDF pages visibly identify themselves
as synthetic, unsigned samples. Sidecars are advisory, require review and are not
eligible as an adjudicated accuracy benchmark.

The adapter distinguishes procurement, award, contract, inspection, financial,
beneficiary, photo-register and other requirements rather than presenting every
requirement as the same generic certification. Photo and engineering documents are
illustrative registers; they are not actual site photographs or certified drawings.
Linux uses the backend's existing WeasyPrint dependency; Windows uses Chromium.
Future Docker builds copy the fixture package alongside the backend.

## Existing demo databases

Use `refresh_demo_documents.py`, never the resetting `seed_demo.py` entry point.
Load the intended database and object-storage settings through the approved local
environment mechanism. For protected demo databases the central safety guard also
requires `COMET_SEED_TARGET_MODE=demo` and the correct
`COMET_DEMO_DATABASE_NAME`. No reset opt-in is needed or used.

1. `plan --plan <plan.json>` inventories complete, seed-owned submission histories.
   Unmarked uploads are excluded. Legacy expansion documents require matching known
   project codes, exact intake descriptions, deterministic filenames, per-submission
   paths, linked versions/files and recorded hashes. Ambiguous histories are skipped.
2. Back up the database and retain the referenced object-store objects.
3. `stage --plan <plan.json> --directory <persistent-directory>` generates PDFs and
   their checksum manifest without changing attachment links.
4. Review coverage and representative rendered PDFs.
5. `apply --plan <plan.json> --directory <persistent-directory> --journal <journal.json>`
   rechecks the plan and every PDF checksum, locks affected rows, uploads new objects,
   journals the previous links, then commits all link changes atomically.
6. `verify --plan <plan.json> --journal <journal.json>` reads the stored objects back,
   verifies their hashes and PDF context, and checks that submission/requirement
   records and primary flags have not changed.

Old objects remain available. The script changes attachment content links, sizes and
hashes, while retaining submission IDs, version numbers, upload dates, primary flags,
review history and workflow states. It neither submits pending requirements nor
reruns AI classification. Existing scan history remains historical demo data.
Repeating a successful plan excludes documents with the current generator version.
Bump `GENERATOR_VERSION` when publishing a new generated-document revision.

For rollback, use `rollback --plan <plan.json> --journal <journal.json>`. It restores
previous links only while the refreshed links still match the journal. Neither old
nor new objects are deleted by rollback. Keep the journal and backup protected on
the host; do not publish credentials or database dumps as evidence.

## Empty local initialization

`seed_demo.py --initialize-empty` refuses populated application tables and skips
database resets and the separate destructive notice-template refresher. The only
existing rows it permits are the two risk-threshold defaults created by migrations.
Initialize and validate the schema first. The ordinary `seed_demo.py` mode retains
its existing destructive reset behavior and must not be used for production refresh.
