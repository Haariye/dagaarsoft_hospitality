// Housekeeping Task JS v3 — Mobile-friendly, one-tap updates
frappe.ui.form.on("Housekeeping Task", {
    refresh(frm) {
        const colors = {
            "Pending": "orange", "In Progress": "blue",
            "Completed": "green", "Skipped": "gray", "Blocked": "red"
        };
        frm.page.set_indicator(frm.doc.task_status || "Pending", colors[frm.doc.task_status] || "gray");

        if (frm.doc.docstatus !== 1) return;

        let s = frm.doc.task_status;
        if (s === "Pending" || s === "In Progress") {
            // One-tap status buttons
            if (s === "Pending") {
                frm.add_custom_button(__("▶ Start Cleaning"), () => {
                    _quick_status(frm, "In Progress");
                }).css("background", "#4299e1").css("color", "white");
            }
            frm.add_custom_button(__("✅ Mark Complete"), () => {
                frappe.confirm(
                    __("Mark Room {0} cleaning as complete?", [frm.doc.room]),
                    () => _quick_status(frm, "Completed")
                );
            }).css("background", "#48bb78").css("color", "white").css("font-weight", "bold");

            frm.add_custom_button(__("⛔ Mark Blocked"), () => {
                frappe.prompt([
                    { fieldname: "reason", fieldtype: "Data", label: __("Reason"), reqd: 1 }
                ], v => {
                    frm.doc.notes = v.reason;
                    _quick_status(frm, "Blocked");
                }, __("Block Task"), __("Confirm"));
            }, __("Actions"));
        }

        if (s === "Completed") {
            let room_status = frappe.db.get_value("Room", frm.doc.room, "room_status");
            frm.dashboard.add_indicator(__("Room cleaned ✓"), "green");
        }
    }
});

function _quick_status(frm, status) {
    frappe.call({
        method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.housekeeping_task.housekeeping_task.quick_update_status",
        args: { task_name: frm.doc.name, new_status: status },
        callback(r) {
            frm.reload_doc();
            frappe.show_alert({
                message: __("Room {0}: Status → {1}", [frm.doc.room, status]),
                indicator: status === "Completed" ? "green" : "blue"
            });
        }
    });
}
