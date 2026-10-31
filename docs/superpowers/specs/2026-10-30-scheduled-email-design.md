# Customer email workspace

The user approved the full proposed scope: durable per-customer drafts, scheduling with timezone, a visible editable/cancelable pending list, stop-on-reply, and reusable multi-step follow-up sequences. Implement within the existing CRM fork and existing authenticated mailbox integration. Do not upgrade unrelated Framework code or deploy/send live email during development.

## User experience

A customer Email workspace appears alongside the existing lead/deal composer. It stores complete drafts including sender, recipients, CC/BCC, subject, HTML and attachments on the server. Reopening restores the full draft across devices. Schedule shows an explicit timezone; drafts can be edited, scheduled, canceled and deleted if still drafts. Status and errors are visible. Existing immediate sending remains available. A sequence editor stores reusable steps with day offsets; enrollment previews/creates the individual pending emails and stops remaining steps on a matching inbound reply.

## State and ownership

Use CRM Email Draft, CRM Email Sequence and CRM Email Sequence Step DocTypes. Pending sends remain in CRM until due. Every API requires a signed-in enabled CRM user, reference read/email permission, and ownership of the draft/template. Sender must be an enabled outgoing mailbox linked to that user; never silently fall back to a global mailbox. File attachments require permissions and valid association. Optimistic modified checks prevent overwriting another tab. Generic document APIs must not bypass these rules.

## Dispatch and suppression

A scheduler finds due rows and serializes claims with database locks. Recheck user, customer, sender, attachments, reply state and sequence suppression at dispatch. Use durable dispatch markers and native Communication logging. Never automatically retry an ambiguous transport outcome. Cancel pending mail when an inbound Communication is linked to the same customer and its sender matches an intended recipient, including CC recipients as appropriate. Ignore unrelated contacts. Conservatively stop on auto-replies; bounces/unsubscribe require suppression rather than further follow-ups. Replies outside CRM or mail already accepted by the provider cannot be recalled. Multi-step sequence cancellation must stop every remaining matching step. Native queue retries must not bypass cancellation or create duplicate sends.

## Verification

Behavior tests for durable draft fields, permissions, sender/attachment isolation, timezone conversion and DST, scheduling validation, concurrent claims/edits, cancellation on new-thread reply, unrelated replies, auto-replies/bounces, duplicate enrollment, recipient changes, retries/unknown outcomes and sequence progression. Run frontend tests/build/lint and isolated Frappe integration tests. Add CI coverage for real permissions, schema sync and database transactions on supported Framework branches. No test may deliver external email.
