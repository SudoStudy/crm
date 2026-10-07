# Native Performance Implementation Plan

> For agentic workers: use subagent-driven-development for implementation, then independent spec
> and code-quality reviews. User has approved implementation and production rollout, not merging
> a new PR. Baseline `dc541e8b` includes the tested keypad.

**Goal:** Ship the approved compact Performance page inside CRM with accurate targets and activity.

**Architecture:** Small CRM-native Python services behind permission-checked whitelisted APIs;
reuse the existing custom target doctype with an idempotent schema patch and a separate recurring
rule doctype if persistence needs it. Vue page uses frappe-ui and existing semantic tokens.

**Tech stack:** Frappe v16, Python, Vue 3, frappe-ui, Vitest and Python unittest.

## Task 1: Native services and page (one integrated implementation)

Files: `crm/api/performance.py`, `crm/performance/{metrics,activity,targets}.py`,
`crm/patches/v1_0/native_performance_targets.py`, `crm/patches.txt`,
`frontend/src/pages/Performance.vue`, small components/utilities under `Performance/`,
`frontend/src/router.js`, `frontend/src/components/Layouts/AppSidebar.vue`, backend/frontend tests.

- [ ] Read the existing API, permissions, call/task/note/status schemas and HTML design.
- [ ] Add failing calculation tests: quarter sum, zero actual MRR, latest Won transition/reopening,
  probability clamp, mixed currencies, missing month, coverage denominator, no Won history fallback.
- [ ] Implement pure calculations and permission-aware paginated record loading. GET APIs do not write.
- [ ] Add failing API tests: Guest rejection, rep cannot inspect another rep/team or edit targets,
  manager selection; scoped record permissions; activity pagination and call actor attribution.
- [ ] Implement normalized activity with strict source types and chronological stable pagination;
  unknown/missing histories are explained, not invented. All source reads respect parent permissions.
- [ ] Preserve target schema/data in idempotent migration. Store recurring effective-month rules,
  use missing-month resolution without mutating old targets on dashboard read.
- [ ] Add manager-only validated target writes, USD, nonnegative finite amount, first-of-month,
  uniqueness and locking against duplicate monthly targets. Existing historical rows remain intact.
- [ ] Implement `/performance` route, native sidebar, selected salesperson/month/quarter,
  summary, progress, warnings, linked paginated contributing deals, seven-day activity, target dialog,
  loading/error/empty states. Persist filters in route query; keep current identity safe defaults.
- [ ] Add frontend tests for period changes, stale-request protection, error/empty states and manager
  edit visibility. Use real pure calculations and mocked server transport only.
- [ ] Run `python3 -m unittest discover -s crm/performance/tests -v`, `cd frontend && yarn test:run`,
  targeted ESLint and production `yarn build`. Self-review all diff against the approved spec.

## Task 2: Review and production rollout (controller)

- [ ] Spec reviewer compares every approved requirement to the actual code. Fix gaps and re-review.
- [ ] Quality reviewer checks permissions, SQL/filter injection, datetimes, target concurrency,
  query bounds/pagination, migration idempotence and frontend stale results; fix and re-review.
- [ ] Commit coherent scoped files; push `codex/native-performance`; create and attach a PR.
  Do not merge it unless user authorizes that exact PR.
- [ ] Confirm live target count/values and installed apps using direct root `.env` credentials only.
- [ ] Backup production site. Switch only CRM app source to reviewed branch; deploy + update site;
  leave every other app pinned and no skipped patches.
- [ ] Verify deployed SHA, route/assets, real API totals against independent reads, rep boundaries,
  and preserved target rows. Report accessible URL and any remaining requirement needing input.

## Deferred deliberately

No calling enhancements; no upstream version bump; no unrelated CI/CD or standalone app removal
before the native page is proven. These can follow this page-first rollout.
