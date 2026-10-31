# Email workspace API contract

Module: crm.api.scheduled_email. Mutations POST only. Data objects are dicts or JSON strings accepted safely. API returns allowlisted public fields and JSON attachment arrays (File names). The new send_at field stores UTC-naive Datetime values internally, with explicit UTC comparisons; public send_at values are ISO-8601 UTC with Z. Native creation/modified timestamps retain Framework conventions. Browser submits an offset-bearing ISO timestamp and IANA timezone. UI converts using a tested helper; no implicit browser/server timezone coercion.

- get_workspace(reference_doctype, reference_name) -> {drafts: [...], sequences: [...], senders: [{email, label}], timezone: IANA string}. Only own records. Includes sequence template steps for editing.
- save_draft(data) -> draft. data contains optional name/modified and reference_doctype, reference_name, sender, recipients, cc, bcc (comma-separated strings), subject, content, attachments (File name strings), stop_on_reply (boolean). Saving an existing Scheduled item returns it to Draft and removes its old send time. Terminal/dispatching drafts cannot be edited.
- schedule_draft(name, send_at, timezone, modified) -> draft. Must be future; optimistic modified token required for mutations on existing rows.
- send_draft_now(name, modified) -> draft. An authorized complete Draft becomes due now and dispatch is enqueued only after commit. Delivery status updates through the same conservative worker as scheduled mail.
- unschedule_draft(name, modified) -> draft. Pauses a Scheduled email immediately, clears its send time, and returns Draft before the editor opens.
- cancel_enrollment(enrollment_id) -> {canceled_count, already_sending}. Cancels all owned pending steps after reference authorization; never recalls in-flight mail.
- cancel_email(name, modified) -> draft. Only pending Scheduled/Draft/Error; no recall during Sending or Sent. Idempotent canceled requests may return current state.
- delete_draft(name, modified) -> {deleted:true}. Draft/Canceled only; generic delete follows same restrictions.
- save_sequence(data) -> sequence. {name?,modified?,title,steps:[{day_offset:integer>=0,subject,content}]}. At least one step, strictly increasing offsets, max 20; private to owner. Saving cannot rewrite existing enrollment snapshots.
- enroll_sequence(reference_doctype, reference_name, sequence_name, start_at, timezone, sender, recipients) -> {drafts:[...]}. Snapshot steps, schedule relative to chosen local wall-clock start and offsets, immutable enrollment marker. Prevent duplicate active enrollment for same owner/customer/recipient. All steps stop_on_reply=true.

Draft public fields: name, modified, reference_doctype, reference_name, sender, recipients, cc, bcc, subject, content, attachments, stop_on_reply, status, send_at, timezone, sequence_name, enrollment_id, communication, last_error. Status: Draft, Scheduled, Sending, Sent, Canceled, Error. Error after ambiguous send is never automatically retried; UI requires verification rather than allowing blind reschedule.
