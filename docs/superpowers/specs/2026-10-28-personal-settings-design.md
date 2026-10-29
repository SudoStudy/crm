# Richard's personal CRM email and API settings

Status: approved by the user on 28 October 2026. Implementation is scoped to personal settings; no production deployment is authorized.

## Confirmed cause

The live Email Account metadata grants management to System Manager. The CRM settings menu separately hides Email configuration behind isManager(). Profile → Emails & Signature selects already-connected outbound accounts; it does not connect a mailbox. Frappe's User API credentials are at permission level 1, and the framework generate_keys method explicitly requires System Manager. Making the menu visible alone would not fix the server restriction.

## Recommended change

Add personal Email connection and API access under the CRM profile for Sales Users, including Richard. Keep Richard's role as Sales User. A personal API token retains the same CRM record permissions as that user.

Personal email:

- Bind every request to the signed-in user's email, initially richard@sudostudy.com for Richard. The server rejects requests to configure another address or account, regardless of submitted input.
- Provide a Google/GMail setup form using the existing provider support. Richard enters an app password himself if permitted by Workspace policy; the agent never reads or transfers it. OAuth requires a separately configured provider and is not assumed available.
- Only show safe connection status and the signed-in user's account. Existing account credentials are never returned.
- Connect incoming/outgoing mail using his account; preserve site-wide default accounts and other users' routing. Add his own outbound account to his profile.
- Do not enable automatic contact/lead creation as part of personal mailbox connection. This prevents connection from silently adding unrelated inbox senders to CRM contacts.

Personal API access:

- Add a profile page for generating/replacing that signed-in user's API credentials. No target-user input is accepted.
- Show newly generated credentials to the user in their own browser only, with explicit reveal/copy actions. Do not return stored secrets or save credentials in browser storage, logs, reports or the repository.
- Require a confirmation before replacing an existing API secret because existing integrations will need the replacement. Rate-limit generation.
- Do not broaden User or Email Account role permissions and do not grant Sales Manager or System Manager.

## Alternatives

1. Recommended: the scoped self-service change above. Richard can manage his own connection and personal API credentials without waiting for an administrator.
2. Existing administration flow: an administrator provisions his mailbox and generates his personal API credentials. This needs no application feature, but Richard cannot independently manage those settings.

## Current setup steps before the change

An administrator can add the mailbox from Settings → Email → Email Accounts, choose GMail, use Richard's address, and configure incoming/outgoing. Richard then uses Settings → Profile → Emails & Signature → Configure to select his connected outgoing account and set his signature. Google's app-password requirement depends on two-step verification and Workspace policy. Richard should enter credentials himself.

An administrator can open the User record for richard@sudostudy.com in Desk, then API Access → Generate Keys. The credentials belong to Richard and use his permissions, but the stock generation action is restricted to administrators. No credentials have been generated in this task.

Official email setup documentation: https://docs.frappe.io/crm/email-communication

## Verification before delivery

Use an isolated Frappe test site and build the frontend with its matching Frappe UI dependency. Test Sales User self-access, rejection of another user's address/API target, guest rejection, own-account list filtering, preserved global defaults, no automatic contact creation, and masked/new-secret-only behavior. Test key replacement without logging secrets. Do not use production for these tests.

Implementation will be prepared on an isolated branch and reviewed before deployment. Any production changes require approval for the exact target and operation. No PR may be merged without explicit approval for that PR.
