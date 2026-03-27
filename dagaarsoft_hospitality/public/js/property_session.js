/**
 * Property Session Utility — dagaarsoft_hospitality
 * 
 * Auto-fills the `property` field on every hospitality form based on:
 *   1. User Permission for "Property" (if set) — locks the field
 *   2. Global default from Hospitality Settings — pre-fills but allows change
 * 
 * Usage in any form JS:
 *   frappe.require('/assets/dagaarsoft_hospitality/js/property_session.js');
 *   // OR — just call: dh_apply_property(frm);
 * 
 * All forms call this automatically via the doctype_js event hooks.
 */

window.dh_get_session_property = function() {
    const d = frappe.boot && frappe.boot.hospitality_defaults;
    return {
        property:       (d && d.property)        || "",
        locked:         (d && d.property_locked) || false,
        user_property:  (d && d.user_property)   || "",
    };
};

/**
 * Apply property to a form:
 * - If user has a permission-locked property: set + make read_only
 * - If global default only: set if empty, keep editable
 */
window.dh_apply_property = function(frm) {
    if (!frm.fields_dict || !frm.fields_dict.property) return;
    if (frm.doc.docstatus > 0) return; // don't touch submitted docs

    const sess = dh_get_session_property();
    if (!sess.property) return;

    // Set the value if field is empty
    if (!frm.doc.property) {
        frm.set_value("property", sess.property);
    }

    // If user permission locks property — make field read_only
    if (sess.locked) {
        frm.set_df_property("property", "read_only", 1);
        frm.set_df_property("property", "description",
            __("Auto-set from your User Permission"));
    }
};

/**
 * Set filters on property-dependent fields.
 * Call this in refresh() after dh_apply_property().
 */
window.dh_set_property_filters = function(frm, field_list) {
    const prop = frm.doc.property || dh_get_session_property().property;
    if (!prop) return;
    (field_list || []).forEach(function(fn) {
        if (frm.fields_dict[fn]) {
            frm.set_query(fn, function() {
                return { filters: { property: prop } };
            });
        }
    });
};
