// RE Unit Form
frappe.ui.form.on("RE Unit", {
    refresh(frm) {
        _re_set_status_indicator(frm);
        _re_unit_filters(frm);

        if (frm.doc.docstatus === 0 || frm.doc.name) {
            // Show active lease if exists
            if (frm.doc.current_lease) {
                frm.add_custom_button(__("View Lease"), () =>
                    frappe.set_route("Form", "RE Lease", frm.doc.current_lease), __("Links"));
            }
            // New Lease button if Available
            if (frm.doc.status === "Available" && !frm.doc.current_lease) {
                frm.add_custom_button(__("Create Lease"), () => {
                    frappe.new_doc("RE Lease", {
                        unit: frm.doc.name,
                        property: frm.doc.property,
                        monthly_rent: frm.doc.monthly_rent,
                        security_deposit: frm.doc.security_deposit_amount,
                        rent_includes_utility: frm.doc.rent_includes_utility,
                    });
                }).addClass("btn-primary");
            }
            // Maintenance
            frm.add_custom_button(__("Maintenance Request"), () => {
                frappe.new_doc("RE Maintenance Request", {
                    unit: frm.doc.name,
                    property: frm.doc.property,
                    request_date: frappe.datetime.get_today(),
                });
            }, __("Actions"));
            // Schedule Viewing
            frm.add_custom_button(__("Schedule Viewing"), () => {
                frappe.new_doc("RE Viewing Schedule", {
                    unit: frm.doc.name,
                    property: frm.doc.property,
                });
            }, __("Actions"));
            // Inspection
            frm.add_custom_button(__("New Inspection"), () => {
                frappe.new_doc("RE Inspection Report", {
                    unit: frm.doc.name,
                    property: frm.doc.property,
                    inspection_date: frappe.datetime.get_today(),
                });
            }, __("Actions"));
        }

        // Unit summary dashboard
        if (frm.doc.name && !frm.is_new()) {
            _re_unit_dashboard(frm);
        }
    },
    property(frm) { _re_unit_filters(frm); },
    unit_type(frm) {
        if (frm.doc.unit_type) {
            frappe.db.get_value("RE Unit Type", frm.doc.unit_type,
                ["default_rent","default_deposit_months","furnishing","size_sqm"], r => {
                if (!r) return;
                if (!frm.doc.monthly_rent && r.default_rent)
                    frm.set_value("monthly_rent", r.default_rent);
                if (!frm.doc.furnishing && r.furnishing)
                    frm.set_value("furnishing", r.furnishing);
                if (!frm.doc.size_sqm && r.size_sqm)
                    frm.set_value("size_sqm", r.size_sqm);
                if (!frm.doc.deposit_months && r.default_deposit_months)
                    frm.set_value("deposit_months", r.default_deposit_months);
            });
        }
    },
    monthly_rent(frm) {
        if (frm.doc.monthly_rent && frm.doc.deposit_months) {
            frm.set_value("security_deposit_amount",
                flt(frm.doc.monthly_rent) * int(frm.doc.deposit_months));
        }
    },
    deposit_months(frm) { frm.trigger("monthly_rent"); },
    location_map_url(frm) {
        if (frm.doc.location_map_url) {
            frm.set_df_property("location_map_url", "description",
                `<a href="${frm.doc.location_map_url}" target="_blank">Open in Google Maps</a>`);
        }
    }
});

function _re_unit_filters(frm) {
    if (frm.doc.property) {
        frm.set_query("unit_type", () => ({ filters: {} }));
    }
}

function _re_set_status_indicator(frm) {
    const colors = {
        "Available": "green", "Occupied": "blue",
        "Reserved": "orange", "Under Maintenance": "red",
        "Vacant - Cleaning": "yellow", "Out of Service": "grey"
    };
    frm.page.set_indicator(__(frm.doc.status || "Unknown"),
        colors[frm.doc.status] || "grey");
    if (frm.doc.current_tenant) {
        frm.dashboard.add_indicator(
            __("Tenant: {0}", [frm.doc.current_tenant]), "blue");
    }
    if (frm.doc.furnishing) {
        frm.dashboard.add_indicator(__(frm.doc.furnishing),
            frm.doc.furnishing === "Furnished" ? "green" : "grey");
    }
    if (frm.doc.rent_includes_utility) {
        frm.dashboard.add_indicator(__("Utilities Included"), "green");
    }
}

function _re_unit_dashboard(frm) {
    frappe.db.count("RE Lease", {unit: frm.doc.name, docstatus: 1})
        .then(cnt => {
            if (cnt > 0) {
                frm.dashboard.add_indicator(
                    __("{0} Lease(s)", [cnt]), "blue");
            }
        });
    frappe.db.count("RE Maintenance Request",
        {unit: frm.doc.name, status: ["in", ["Open","In Progress"]]})
        .then(cnt => {
            if (cnt > 0) {
                frm.dashboard.add_indicator(
                    __("{0} Open Maintenance", [cnt]), "orange");
            }
        });
}

function flt(v) { return parseFloat(v||0); }
function int(v) { return parseInt(v||0); }
