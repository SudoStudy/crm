# Personal CRM settings implementation plan

> **For agentic workers:** Use executing-plans inline to implement this approved design task by task.

**Goal:** Let Sales Users connect their own Google mailbox and generate their own CRM API credentials.

**Architecture:** Add authenticated, session-bound endpoints in crm/api/personal_settings.py and profile pages that use only those endpoints. Do not change role permissions or the framework's administrator APIs. Serialize writes by locking the current User row, preserve existing global defaults, and expose newly generated API credentials only in the response to the generation action.

**Tech Stack:** Frappe Python, MariaDB, Vue 3, frappe-ui, Vitest, FrappeTestCase.

## Stage 1 — server boundary

Files: crm/api/personal_settings.py, crm/api/test_personal_settings.py.

- [x] Implement `get_personal_settings()`, `connect_personal_mailbox(password, email_id=None)` and `generate_personal_api_keys(confirm_replace=False)`.
- [x] Require an enabled System User with an allowed CRM role. Reject another mailbox address. Never accept a target API user. Return a fixed allowlist of mailbox status fields and API configured boolean.
- [x] For API credentials, lock the current User, require confirmation on replacement, generate a 32-character secret and keep any existing API key. Set no-store headers; return credentials only on generation. Rate-limit both writes.
- [x] For Gmail, create a non-default account using fixed Google servers, validated credentials, IMAP INBOX, no automatic Contact/Lead creation. Refuse to overwrite an administrator/shared/default/OAuth-managed account. Add only this account to the current user's outgoing accounts.
- [x] Add native Frappe integration tests with test users and real User/Email Account documents, patching only external mail-server validation. Cover guest/non-CRM/cross-user denial, safe responses, credential rotation, defaults, uniqueness and idempotent reconnection.

Verification: `bench --site <isolated-site> run-tests --module crm.api.test_personal_settings`; no production resources in tests.

## Stage 2 — profile experience

Files: frontend/src/components/Settings/Profile/{ProfilePage,ProfileSettings,UserEmailSettings,PersonalMailboxSettings,PersonalAPISettings}.vue; frontend/tests/unit/personalSettings.test.js.

- [x] Add Connect mailbox and API access profile actions available to Sales Users.
- [x] Provide a readonly signed-in address, Gmail app-password input, clear connection status and actionable Workspace-policy guidance. Clear password on success/unmount; keep other user's account management inaccessible.
- [x] Generate keys only on an explicit button action; confirm before rotation. Mask new credentials and allow explicit reveal/copy. Clear them on navigation; never persist them.
- [x] Use the personal status endpoint for Sales User email selection, preserving existing manager behavior.
- [x] Add Vue component interaction tests for rendering, masked secrets, generation/confirmation, clipboard and clearing input.

Verification: `cd frontend && yarn test:run`, then `yarn build` using the matching Frappe UI dependency.

## Stage 3 — review and handoff

- [x] Run formatting/lint, native integration tests and frontend tests/build.
- [x] Review server identity binding, secret handling, existing-account conflicts, concurrent writes and cross-user cases against the approved design.
- [x] Add setup instructions in docs and record verification results and limitations.
- [x] Commit coherent changes and preserve the reviewable branch. Do not merge or deploy.

## Verification log

- Baseline: 298 frontend tests passed.
- Current: 307 frontend tests passed, frontend build passed, ESLint and Ruff passed.
- Native Frappe 16.34.0: 20 integration tests passed on isolated MariaDB/Redis containers.
- Review findings fixed: API Back action emits correctly; reconnection explicitly disables the CRM automatic-lead flag; native account creation preserves the authenticated owner after the scoped service save.
- Native Frappe 15: 20 integration tests passed on a separate isolated test site.

Final review found no remaining actionable issues. The changes are complete on codex/personal-email-api-settings; production roles, keys and mailbox configuration remain unchanged.
