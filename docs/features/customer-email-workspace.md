# Drafts, scheduled emails and follow-up sequences

Open a lead or deal and expand **Drafts & scheduled emails** below its communication area. The workspace belongs to the signed-in salesperson and the selected customer.

## Saved drafts

Choose **New saved draft**, then fill in the sender, recipients, subject and message. CC, BCC and uploaded attachments are saved too. **Save draft** stores the complete draft on the server so you can reopen it from another device. Save explicitly before leaving; the editor warns about unsaved changes. This workspace is separate from the existing immediate Reply composer and its browser-local draft.

You can save an incomplete draft before connecting a mailbox. Sending requires an enabled outgoing mailbox linked to your own user and permission to email the customer. Connect your own mailbox under Settings > Profile; the workspace never silently sends through the global default account.

## Sending later

Choose a date/time and an explicit IANA timezone, such as Europe/London. **Schedule email** saves the draft and schedules it. The displayed sending time includes its timezone. Times that do not exist or occur twice during daylight-saving changes are rejected so you can choose an unambiguous time.

Pending emails show their status on the customer's workspace. **Edit email** first pauses a scheduled send and returns it to Draft before opening the editor. Schedule it again to confirm its new time. **Cancel email** stops an unsent pending email. Drafts and canceled unsent items may be deleted. Sending and Sent messages cannot be recalled.

**Send now** uses the same authorized dispatcher as scheduled email. Scheduled delivery begins when the background scheduler/worker next runs; it is not a guarantee of delivery at the exact second selected.

## Follow-up sequences

Create a reusable sequence with a title and between one and twenty steps. Each step has a subject, message and increasing day offset, for example 0, 3 and 7. Choose the customer, receiving address, your sending mailbox, start date/time and timezone, then review the preview before enrolling.

Each enrollment saves its own copy of the steps. Editing the reusable template does not rewrite emails already scheduled for customers. The same sender/customer/recipient cannot have overlapping active sequence enrollments. **Cancel remaining sequence** stops its pending steps; messages already sending or sent cannot be recalled.

## Replies and delivery outcomes

**Cancel if this customer replies before sending** is enabled by default. A matching reply cancels pending follow-ups. A reply with a new subject can match by prospect address and the receiving salesperson mailbox even if it is not linked to the CRM record. Unrelated contacts and other salespeople's inboxes do not stop your emails. Out-of-office replies are treated conservatively as replies. A delivery report linked to the original customer message also suppresses follow-ups.

The CRM can only react after it imports the incoming message. Messages already accepted by an email provider cannot be recalled. Keep incoming mailbox sync and background workers running.

If an interrupted delivery has an uncertain outcome, the email shows **Error** and is not retried automatically. Check the provider's sent mailbox before creating a replacement. This avoids a blind retry sending the customer a duplicate. **Sent** means accepted by the sending system, not guaranteed recipient inbox placement.

## Access and deployment

Drafts and sequence templates are private to their owner. Access also requires continued permission to the lead/deal. Disabled users, disconnected mailboxes and inaccessible attachments stop dispatch rather than changing sender or exposing files.

Deploy the CRM schema with `bench migrate` before enabling workers on the new code. CRM must remain the active Email Queue controller for the reply-aware guard; dispatch refuses to proceed if another installed app replaces it without inheriting the guard. Existing non-workspace mail follows its normal delivery path.

Tests use an isolated site and mocked provider transport. No production customer email is required to verify the workflow.
