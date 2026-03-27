// Room JS v3 — Quick actions, status update
frappe.ui.form.on("Room", {
    refresh(frm) {
        const rs_color = {
            "Vacant Clean": "green", "Vacant Dirty": "orange",
            "Occupied": "red", "Out of Order": "gray",
            "Reserved": "blue", "Maintenance": "yellow"
        };
        frm.page.set_indicator(
            frm.doc.room_status + (frm.doc.housekeeping_status ? " / " + frm.doc.housekeeping_status : ""),
            rs_color[frm.doc.room_status] || "gray"
        );

        if (frm.doc.current_stay) {
            frm.add_custom_button(__("View Current Stay"), () =>
                frappe.set_route("Form", "Guest Stay", frm.doc.current_stay), __("Links"));
        }

        // Quick status change
        if (frm.doc.room_status !== "Out of Order") {
            frm.add_custom_button(__("🔧 Mark Out of Order"), () => {
                frappe.prompt([
                    { fieldname: "reason", fieldtype: "Data", label: __("Reason"), reqd: 1 }
                ], v => {
                    frappe.db.set_value("Room", frm.doc.name, {
                        room_status: "Out of Order", is_out_of_order: 1, oo_reason: v.reason
                    });
                    frm.reload_doc();
                }, __("Out of Order"), __("Confirm"));
            }, __("Status"));
        } else {
            frm.add_custom_button(__("✅ Return to Service"), () => {
                frappe.db.set_value("Room", frm.doc.name, { room_status: "Vacant Dirty", is_out_of_order: 0 });
                frm.reload_doc();
            }, __("Status"));
        }
    }
});
