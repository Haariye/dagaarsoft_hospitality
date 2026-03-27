frappe.ui.form.on("RE Tenant", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Active Leases"), () =>
                frappe.set_route("List", "RE Lease", {
                    tenant: frm.doc.name,
                    lease_status: ["in", ["Active","Expiring Soon"]]
                }));
            frm.add_custom_button(__("All History"), () =>
                frappe.set_route("query-report", "Guest Account History", {customer: frm.doc.customer}),
                __("Reports"));
        }
        if (!frm.doc.customer) {
            frm.dashboard.add_indicator(__("⚠ No ERPNext Customer linked"), "red");
            frm.add_custom_button(__("Create Customer"), () => {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.reports.create_tenant_customer",
                    args: {tenant_name: frm.doc.name},
                    callback(r) { if (r.message) { frm.set_value("customer", r.message); frm.save(); }}
                });
            }).addClass("btn-warning");
        }
    }
});
