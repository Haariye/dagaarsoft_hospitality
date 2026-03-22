// Room Move JS v5 - all billing auto-calculated
frappe.ui.form.on("Room Move", {
    refresh(frm) {
        ["from_room","old_nightly_rate","new_nightly_rate","old_room_type","new_room_type",
         "rate_difference","remaining_nights","total_billing_adjustment","adjustment_type",
         "billing_posted","move_time"].forEach(f => frm.set_df_property(f, "read_only", 1));
        const p = frm.doc.property;
        frm.set_query("to_room", () => ({filters: {
            ...(p ? {property: p} : {}), is_out_of_order: 0,
            room_status: ["in", ["Vacant Clean","Vacant Dirty","Inspection"]]}}));
        if (frm.doc.docstatus === 1 && frm.doc.billing_posted)
            frm.dashboard.add_indicator(__("Billing Posted to Folio"), "green");
    },
    guest_stay(frm) {
        if (!frm.doc.guest_stay) return;
        frappe.db.get_value("Guest Stay", frm.doc.guest_stay, ["room","property"], r => {
            if (!r) return;
            frm.set_value("from_room", r.room);
            if (!frm.doc.property && r.property) frm.set_value("property", r.property);
            if (frm.doc.to_room) _preview(frm);
        });
    },
    to_room(frm)   { _preview(frm); },
    move_date(frm) { _preview(frm); }
});
function _preview(frm) {
    if (!frm.doc.guest_stay || !frm.doc.to_room) return;
    frappe.call({
        method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.room_move.room_move.get_room_move_preview",
        args: {guest_stay_name: frm.doc.guest_stay, to_room: frm.doc.to_room},
        callback(r) {
            if (!r.message) return;
            const p = r.message;
            frm.set_value("from_room", p.from_room);
            frm.set_value("old_nightly_rate", p.old_rate);
            frm.set_value("new_nightly_rate", p.new_rate);
            frm.set_value("old_room_type", p.old_room_type);
            frm.set_value("new_room_type", p.new_room_type);
            frm.set_value("rate_difference", p.rate_difference);
            frm.set_value("remaining_nights", p.remaining_nights);
            frm.set_value("total_billing_adjustment", p.total_adjustment);
            frm.set_value("adjustment_type", p.adjustment_type);
            const color = p.rate_difference > 0 ? "orange" : p.rate_difference < 0 ? "red" : "blue";
            frm.dashboard.add_indicator(p.adjustment_type, color);
        }
    });
}
