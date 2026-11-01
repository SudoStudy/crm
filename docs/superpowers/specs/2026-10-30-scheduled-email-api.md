# Email workspace API contract

Module: crm.api.scheduled_email. Mutations POST only. Data objects are dicts or JSON strings accepted safely. API returns allowlisted public fields and JSON attachment arrays (File names). The new send_at field stores UTC-naive Datetime values internally, with explicit UTC comparisons; public send_at values are ISO-8601 UTC with Z. Native creation/modified timestamps retain Framework conventions. Browser submits an offset-bearing ISO timestamp and IANA timezone. UI converts using a tested helper; no implicit browser/server timezone coercion.

- get_workspace(reference_doctype, reference_name) -> {drafts: [...], sequences: [...], senders: [{email, label}], timezone: IANA string}. Only own records. Includes sequence template steps for editing.
- save_draft(data) -> draft. data contains optional name/modified and reference_doctype, reference_name, sender, recipients, cc, bcc (comma-separated strings), subject, content, attachments (File name strings), stop_on_reply (boolean). Saving an existing Scheduled item returns it to Draft and removes its old send time. Terminal/dispatching drafts cannot be edited.
- schedule_email(data, send_at, timezone, request_id) -> draft. Creates and schedules one new email atomically. Use the same data fields as save_draft, without name/modified. request_id is required, nonblank and at most 128 characters. Repeating the same request ID with the same accepted payload returns the current email without rescheduling, including after its scheduled time or cancellation. A different payload with the same ID fails. IDs are scoped to the authenticated owner. Draft creation rolls back if scheduling fails. IDs/fingerprints are internal and excluded from responses.
- schedule_draft(name, send_at, timezone, modified) -> draft. Must be future; optimistic modified token required for mutations on existing rows.
- send_draft_now(name, modified) -> draft. An authorized complete Draft becomes due now and dispatch is enqueued only after commit. Delivery status updates through the same conservative worker as scheduled mail.
- unschedule_draft(name, modified) -> draft. Pauses a Scheduled email immediately, clears its send time, and returns Draft before the editor opens.
- cancel_enrollment(enrollment_id) -> {canceled_count, already_sending}. Cancels all owned pending steps after reference authorization; never recalls in-flight mail.
- cancel_email(name, modified) -> draft. Only pending Scheduled/Draft/Error; no recall during Sending or Sent. Idempotent canceled requests may return current state.
- delete_draft(name, modified) -> {deleted:true}. Draft/Canceled only; generic delete follows same restrictions.
- save_sequence(data) -> sequence. {name?,modified?,title,steps:[{day_offset:integer>=0,subject,content}]}. At least one step, strictly increasing offsets, max 20; private to owner. Saving cannot rewrite existing enrollment snapshots.
- enroll_sequence(reference_doctype, reference_name, sequence_name, start_at, timezone, sender, recipients) -> {drafts:[...]}. Snapshot steps, schedule relative to chosen local wall-clock start and offsets, immutable enrollment marker. Prevent duplicate active enrollment for same owner/customer/recipient. All steps stop_on_reply=true.

Draft public fields: name, modified, reference_doctype, reference_name, sender, recipients, cc, bcc, subject, content, attachments, stop_on_reply, status, send_at, timezone, sequence_name, enrollment_id, communication, last_error. Status: Draft, Scheduled, Sending, Sent, Canceled, Error. Error after ambiguous send is never automatically retried; UI requires verification rather than allowing blind reschedule.

## Scheduling one email from an agent

Use the normal authenticated Frappe API identity for the salesperson whose linked mailbox should send the email. Existing customer, sender, attachment and unsubscribe checks apply. Agents can maintain their own sequence logic and call this endpoint once per individual email.

POST `/api/method/crm.api.scheduled_email.schedule_email` with JSON:

```json
{
  "data": {
    "reference_doctype": "CRM Lead",
    "reference_name": "LEAD_RECORD_NAME",
    "sender": "rep@example.com",
    "recipients": "customer@example.com",
    "subject": "Following up",
    "content": "<p>Hello, just following up on our conversation.</p>",
    "attachments": [],
    "stop_on_reply": true
  },
  "send_at": "2030-01-15T15:00:00Z",
  "timezone": "Europe/London",
  "request_id": "agent-followup-UNIQUE_ID"
}
```

Generate the ID once for that email and reuse the exact payload and ID when retrying a timeout. Use a new ID when changing the email or its sending time. Save the returned `message.name` and `message.modified` to inspect or cancel the scheduled email later with `get_workspace` / `cancel_email`. Retrying a canceled, sent, or failed email returns its current state; it does not reactivate it. Idempotency applies while the email record is retained. An explicit deletion removes its request record, so do not retry deleted emails.

`stop_on_reply` defaults to true. A matching incoming email from an intended recipient to that salesperson's mailbox cancels the pending email, even if the incoming message has a new subject or is not linked to the customer. The feature cannot recall an email after sending starts. Incoming mailbox synchronization must be configured and running so CRM can observe the message.

The endpoint creates a scheduled CRM item, not a provider-side scheduled email. The existing scheduler and guarded sender handle delivery when due. It does not accept arbitrary sender identities, other users' files, or updates to existing drafts.
