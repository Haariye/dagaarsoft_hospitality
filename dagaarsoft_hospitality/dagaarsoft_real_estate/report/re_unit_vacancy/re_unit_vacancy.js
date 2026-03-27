// Copyright (c) 2024, DagaarSoft and contributors
// For license information, please see license.txt

frappe.query_reports["RE Unit Vacancy"] = {
	"filters": [
		{
			"fieldname": "property",
			"label": __("Property"),
			"fieldtype": "Link",
			"options": "RE Property"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nAvailable\nOccupied\nUnder Maintenance\nVacant - Cleaning"
		},
		{
			"fieldname": "furnishing",
			"label": __("Furnishing"),
			"fieldtype": "Select",
			"options": "\nFurnished\nUnfurnished\nSemi-Furnished"
		}
	]
};
