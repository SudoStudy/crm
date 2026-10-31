import frappe
from frappe import _
from frappe.model.document import Document


class CRMEmailDraft(Document):
	def validate(self):
		if not frappe.flags.get("crm_email_workspace_write"):
			frappe.throw(_("Use the customer email workspace to change drafts."), frappe.PermissionError)

	def on_trash(self):
		if not frappe.flags.get("crm_email_workspace_write") or self.status not in ("Draft", "Canceled"):
			frappe.throw(
				_("Only drafts and canceled emails can be deleted in the email workspace."),
				frappe.PermissionError,
			)


def on_doctype_update():
	frappe.db.add_index("CRM Email Draft", ["status", "send_at"])
	frappe.db.add_index("CRM Email Draft", ["owner", "reference_doctype", "reference_name"])
	frappe.db.add_index("CRM Email Draft", ["communication"])
	frappe.db.add_index("CRM Email Draft", ["sender", "status"])
