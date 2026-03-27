frappe.ui.form.on("RE Maintenance Request", {
    refresh(frm) {
        const colors = {"Open":"red","In Progress":"orange","Pending Parts":"yellow",
                        "Completed":"green","Cancelled":"grey"};
        frm.page.set_indicator(__(frm.doc.status||"Open"), colors[frm.doc.status]||"grey");
        if (frm.doc.docstatus===1 && frm.doc.status !== "Completed") {
            frm.add_custom_button(__("Mark Complete"), () => {
                frappe.prompt({fieldname:"resolution",fieldtype:"Text Editor",
                    label:__("Resolution Notes"),reqd:1}, v => {
                    frappe.db.set_value("RE Maintenance Request", frm.doc.name, {
                        "status": "Completed",
                        "resolution_notes": v.resolution,
                        "completion_date": frappe.datetime.get_today()
                    }).then(() => frm.reload_doc());
                }, __("Complete Request"), __("Save"));
            }).addClass("btn-success");
            frm.add_custom_button(__("Assign"), () => {
                frappe.prompt({fieldname:"user",fieldtype:"Link","options":"User",
                    label:__("Assign To"),reqd:1}, v => {
                    frm.set_value("assigned_to", v.user);
                    frm.set_value("status", "In Progress");
                    frm.save();
                }, __("Assign Technician"), __("Assign"));
            }, __("Actions"));
        }
        if (frm.doc.chargeable_to_tenant && frm.doc.actual_cost && !frm.doc.tenant_invoice) {
            frm.add_custom_button(__("Invoice Tenant"), () => {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.reports.create_maintenance_invoice",
                    args: {maintenance_name: frm.doc.name},
                    callback(r) { if(r.message) { frm.set_value("tenant_invoice",r.message); frm.save(); }}
                });
            }, __("Billing")).addClass("btn-warning");
        }
    }
});
