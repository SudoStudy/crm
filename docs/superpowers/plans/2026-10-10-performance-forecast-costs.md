# Performance forecast and call costs Implementation Plan

> **For agentic workers:** use executing-plans and test-driven-development. Work on codex/performance-forecast-call-costs, never main.

**Goal:** period-correct editable forecasts and auditable platform Twilio voice costs.

**Architecture:** existing performance API and metrics; server-side billed-leg reconciliation with persisted call metadata; native Vue controls and reusable call-cost display. Existing target permissions remain intact.

**Tech Stack:** Frappe Python, Decimal, Twilio SDK, Vue, Vitest.

## Stage 1 — forecast inputs
- [x] Add failing tests in crm/performance/tests/test_metrics.py for date bounds, quarters, missing dates and zero probability.
- [x] Update crm/performance/metrics.py and crm/fcrm/doctype/crm_deal/crm_deal.py; preserve explicit 0%.
- [x] Add permission/validation tests and POST update_forecast in crm/api/performance.py, limited to expected_deal_value, probability and expected_closure_date with stale-write protection.
- [x] Verify offline performance suite and extend native integration coverage.

## Stage 2 — call charges
- [x] Write failing tests for parent/child SID deduplication, negative prices, nulls, currencies and platform-only inclusion.
- [x] Add crm/performance/call_costs.py and stored readonly call metadata via an idempotent patch; use existing Twilio server credentials only.
- [x] Add bounded scheduled reconciliation and permission-checked detail/shared aggregate endpoints. Do not place calls or modify telephony routing.
- [x] Verify billing and privacy tests; errors expose no provider payload or credentials.

## Stage 3 — native UI and release verification
- [x] Add failing Vue tests for editable forecast dialog, closing month and shared-cost/pending displays.
- [x] Update frontend/src/pages/Performance.vue and reusable display in recording/detail components.
- [x] Update CI paths/migration checks for new modules.
- [x] Run backend suite, frontend suite/build and formatting; perform spec then security/quality review.
- [ ] Create a PR against SudoStudy/crm main; attach it to this chat. Do not merge without PR-specific approval. Report whether changes are local, in PR, or deployed.

## Verification record

96 offline Python tests pass with the pinned Twilio 8.5.0 SDK; the real SDK contract test failed before correcting its caller property and passed afterward. All 298 frontend tests and the production frontend build pass. Formatting, compilation and whitespace checks pass. Forecast and billing spec/quality reviews found no remaining actionable blockers; the final automated P0 review was clean. Native database integration tests are added but remain pending isolated CI execution. No PR, merge, deployment or production data write has occurred.

The separate read-only lead audit is saved outside Git in `/Users/arslan/.codex/outputs/crm-lead-quality-audit-2026-10-10.md`. No lead statuses were inferred or changed automatically.
