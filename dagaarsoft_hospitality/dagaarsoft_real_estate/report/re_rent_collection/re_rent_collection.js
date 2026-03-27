// Copyright (c) 2024, DagaarSoft and contributors
// For license information, please see license.txt

frappe.query_reports["RE Rent Collection"] = {
	"filters": [
		{
			"fieldname": "property",
			"label": __("Property"),
			"fieldtype": "Link",
			"options": "RE Property"
		},
		{
			"fieldname": "tenant",
			"label": __("Tenant"),
			"fieldtype": "Link",
			"options": "RE Tenant"
		},
		{
			"fieldname": "status",
			"label": __("Line Status"),
			"fieldtype": "Select",
			"options": "\nPending\nInvoiced\nPaid\nOverdue"
		},
		{
			"fieldname": "from_date",
			"label": __("Due From"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": __("Due To"),
			"fieldtype": "Date"
		}
	]
};
