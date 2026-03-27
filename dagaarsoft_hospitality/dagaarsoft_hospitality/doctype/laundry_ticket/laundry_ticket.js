// Copyright (c) 2026, DagaarSoft and contributors
// For license information, please see license.txt

frappe.ui.form.on("Laundry Ticket", {
	guest_room: function(frm) {
		if (!frm.doc.guest_room) {
			frm.set_value("guest_stay", "");
			return;
		}

		frappe.db.get_value(
			"Guest Stay",
			{
				room: frm.doc.guest_room,
				stay_status: "Checked In"
			},
			"name"
		).then((r) => {
			frm.set_value("guest_stay", (r.message && r.message.name) || "");
		});
	}
});
