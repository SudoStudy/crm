# Scheduled email implementation plan

Goal: implement the approved customer email workspace and verify it without production mutations.
Architecture: CRM-owned pending records, server-authorized APIs, conservative dispatch and native Communication logging; Vue workspace integrated with customer composer.

- [x] Ground latest origin/main, existing personal mailbox integration, native send path, current drafts and permissions.
- [x] Backend: schema, controller permissions, authorized APIs, sender/file validation, timezone conversion, sequence enrollment, reply suppression, durable dispatcher, integration tests.
- [x] Frontend: customer workspace, complete draft editor, schedule/timezone controls, status list, edit/cancel/delete, reusable sequence builder/enrollment, component and utility tests.
- [x] Integration: inspect API contract and transaction boundaries; verify local native Framework compatibility; run meaningful frontend and Python checks; run real isolated-site tests in CI.
- [x] Independent review: inspect authorization, queue retries and cancellation races; repair accepted findings; rerun invalidated checks.
- [ ] Delivery: coherent commits, draft PR against SudoStudy/crm main, attach PR, verify current-head checks. No merge or deployment.

API contract lives in docs/superpowers/specs/2026-10-30-scheduled-email-api.md and is shared by backend/frontend workers. Workers own disjoint files. Root owns hooks integration, CI, documentation and final review. Record completed checks and remaining limitations here as work progresses.

## Verified locally

- Fresh frontend suite: 355 tests across30 files pass. Production build succeeds. ESLint has zero errors; nine warnings are in unchanged files. Scoped Prettier passes.
- Fresh native Framework16.34.0/MariaDB10.6 suite:32 scheduled-email tests pass, including native queue/header/attachment behavior and two-connection concurrency. Personal-settings baseline20 passed separately.
- Existing offline performance suite:96 tests pass with one optional Twilio SDK test skipped. Targeted Python compile/Ruff checks pass.
- Independent reviews produced fixes for Reply-To routing, inbound locking, UTC DST folds, nonzero sequence offsets, upload races, unsaved templates, and pausing before editing.
- Framework15 compatibility and hosted CI are not yet verified. No live email was sent; no production schema or permissions were modified.
