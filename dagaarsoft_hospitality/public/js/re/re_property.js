frappe.ui.form.on("RE Property", {
    refresh(frm) {
        if (frm.doc.latitude && frm.doc.longitude && !frm.doc.location_map_url) {
            frm.set_value("location_map_url",
                `https://www.google.com/maps?q=${frm.doc.latitude},${frm.doc.longitude}`);
        }
        if (!frm.is_new()) {
            frm.add_custom_button(__("View Units"), () =>
                frappe.set_route("List", "RE Unit", {property: frm.doc.name}));
            frm.add_custom_button(__("Active Leases"), () =>
                frappe.set_route("List", "RE Lease", {property: frm.doc.name, lease_status: "Active"}));
            frm.add_custom_button(__("Vacancies"), () =>
                frappe.set_route("List", "RE Unit", {property: frm.doc.name, status: "Available"}));
            if (frm.doc.location_map_url) {
                frm.add_custom_button(__("Open Map"), () =>
                    window.open(frm.doc.location_map_url, "_blank"), __("Links"));
            }
            _re_property_dashboard(frm);
        }
    },
    latitude(frm) { _update_map_url(frm); },
    longitude(frm) { _update_map_url(frm); },
});

function _update_map_url(frm) {
    if (frm.doc.latitude && frm.doc.longitude) {
        frm.set_value("location_map_url",
            `https://www.google.com/maps?q=${frm.doc.latitude},${frm.doc.longitude}`);
    }
}

function _re_property_dashboard(frm) {
    frappe.db.count("RE Unit", {property: frm.doc.name, status: "Occupied"})
        .then(n => frm.dashboard.add_indicator(__("{0} Occupied", [n]), "blue"));
    frappe.db.count("RE Unit", {property: frm.doc.name, status: "Available"})
        .then(n => frm.dashboard.add_indicator(__("{0} Available", [n]), "green"));
    frappe.db.count("RE Maintenance Request",
        {property: frm.doc.name, status: ["in", ["Open","In Progress"]]})
        .then(n => { if (n) frm.dashboard.add_indicator(__("{0} Open Maintenance", [n]), "orange"); });
}
