frappe.ui.form.on("RE Inspection Report", {
    refresh(frm) {
        const colors = {"Excellent":"green","Good":"blue","Fair":"orange","Poor":"red"};
        if (frm.doc.overall_condition)
            frm.page.set_indicator(__(frm.doc.overall_condition),
                colors[frm.doc.overall_condition]||"grey");
        if (frm.doc.total_repair_cost > 0) {
            frm.dashboard.add_indicator(
                __("Repair Est: {0}", [parseFloat(frm.doc.total_repair_cost).toLocaleString("en",{minimumFractionDigits:2})]),
                "orange");
        }
    }
});
