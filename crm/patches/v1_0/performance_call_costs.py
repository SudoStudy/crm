"""Idempotent schema only; never fetch credentials or reconcile during migration."""


def cost_fields():
	definitions = [
		(
			"voice_cost_status",
			"Voice Cost Status",
			"Select",
			"\nPending\nPartial\nComplete\nError\nUnsupported Currency",
		),
		("voice_cost_currency", "Voice Cost Currency", "Data", None),
		("voice_cost_amount", "Known Voice Cost", "Currency", "voice_cost_currency"),
		("voice_cost_leg_count", "Voice Cost Legs", "Int", None),
		("voice_cost_pending_legs", "Voice Cost Pending Legs", "Int", None),
		("voice_cost_checked_at", "Voice Cost Checked At", "Datetime", None),
		("voice_cost_error", "Voice Cost Error", "Data", None),
	]
	return [
		{
			"fieldname": name,
			"label": label,
			"fieldtype": fieldtype,
			"options": options,
			"read_only": 1,
			"no_copy": 1,
			"hidden": 1,
			**({"precision": "6"} if name == "voice_cost_amount" else {}),
		}
		for name, label, fieldtype, options in definitions
	]


def execute():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({"CRM Call Log": cost_fields()}, update=True)
