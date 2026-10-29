# Personal email and API access

CRM Sales Users, Sales Managers and System Managers can open **Settings → Profile** to manage their own mailbox and API credentials. No extra role is required. These controls do not grant access to other people's leads, deals or settings.

## Connect your Google mailbox

1. Open **Personal mailbox → Connect mailbox**. The email address comes from your signed-in account and cannot be changed here.
2. Enable two-step verification for your Google account and create a Google app password, if your Google Workspace policy allows it. Use the link in the page for Google's instructions.
3. Enter the app password directly into CRM and select **Connect mailbox**. Do not send it to another person or paste it into a chat.
4. CRM validates the connection and adds your mailbox to your profile's sending accounts. Use **Emails & Signature → Configure** to set your signature. Refresh CRM if an already-open email editor has not updated.

The connector uses Google's IMAP and SMTP services. It syncs unread messages, leaves site-wide defaults unchanged, and does not automatically create contacts or leads. If the Google account does not support app passwords, an administrator needs to configure a supported OAuth connection separately; this page does not set up an OAuth provider.

You can update an account created through this personal page. Existing administrator-managed accounts, shared accounts, global defaults and OAuth accounts remain administrator-managed. You can continue to use your provisioned mailbox without being able to overwrite its configuration.

## Personal API credentials

1. Open **API access → Manage API credentials**.
2. Select **Generate API credentials**. The API key and secret are masked by default.
3. Use **Reveal credentials** or the individual Copy buttons, then save the credentials in your password manager. The page clears the returned credentials when you leave it; CRM does not provide a way to retrieve the stored secret through this page.
4. To replace an existing secret, select the replacement confirmation and choose **Replace API secret**. The API key stays the same. Existing integrations must use the new secret.

The credentials authenticate as your user and retain your existing permissions. A Sales User's API token does not become an administrator token.

## Implementation notes

The personal endpoints accept no API target user, bind mailbox identity to the authenticated User, and return allowlisted connection metadata. Both writes are POST-only and rate limited. User-row locks serialize personal settings updates. Role permissions are unchanged.

Native Frappe Email Account validation queries administrator-only Property Setter metadata. The personal mailbox save therefore temporarily runs under a server service context only after identity, ownership, shared-account and default-account checks. It assigns a new mailbox back to the authenticated owner and restores the complete caller session and the request state reset by `frappe.set_user`, including on errors. Tests cover this behavior. Recheck that saved state list when upgrading Frappe.

The connector does not change other users' sender routing, global incoming/outgoing defaults, or automatic-linking configuration. A duplicate address configuration requires administrator review rather than choosing one mailbox arbitrarily.
