// Copyright (c) 2024, DagaarSoft and contributors
// For license information, please see license.txt

frappe.query_reports["RE Lease History"] = {
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
			"fieldname": "unit",
			"label": __("Unit"),
			"fieldtype": "Link",
			"options": "RE Unit"
		},
		{
			"fieldname": "lease_status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nActive\nExpiring Soon\nExpired\nTerminated\nRenewed"
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
		}
	]
};
