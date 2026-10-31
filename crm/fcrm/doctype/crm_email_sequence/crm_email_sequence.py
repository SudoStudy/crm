import frappe
from frappe import _
from frappe.model.document import Document


class CRMEmailSequence(Document):
	def validate(self):
		if not frappe.flags.get("crm_email_workspace_write"):
			frappe.throw(_("Use the email workspace to change sequences."), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(_("Keep sequence templates to preserve customer email history."), frappe.PermissionError)
