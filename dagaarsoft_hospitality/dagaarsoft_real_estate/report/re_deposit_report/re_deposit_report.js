// Copyright (c) 2024, DagaarSoft and contributors
// For license information, please see license.txt

frappe.query_reports["RE Deposit Report"] = {
	"filters": [
		{
			"fieldname": "property",
			"label": __("Property"),
			"fieldtype": "Link",
			"options": "RE Property"
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "deposit_status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nHeld\nPartially Refunded\nRefunded\nForfeited"
		}
	]
};
