frappe.listview_settings["Reservation"]={get_indicator(doc){
    const m={"Provisional":["Provisional","orange"],"Confirmed":["Confirmed","blue"],
        "Checked In":["Checked In","green"],"Checked Out":["Checked Out","grey"],
        "Cancelled":["Cancelled","red"],"No Show":["No Show","red"]};
    return m[doc.reservation_status]||[doc.reservation_status||"","grey"];,
    onload(listview) {
        if (typeof dh_get_session_property === 'function') {
            const sess = dh_get_session_property();
            if (sess && sess.property) {
                listview.filter_area.add([[listview.doctype, 'property', '=', sess.property]]);
            }
        }
    }
};
