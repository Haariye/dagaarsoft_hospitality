frappe.listview_settings["Guest Stay"]={get_indicator(doc){
    const m={"Expected":["Expected","orange"],"Checked In":["Checked In","green"],
        "Checked Out":["Checked Out","grey"],"Cancelled":["Cancelled","red"],"No Show":["No Show","red"]};
    return m[doc.stay_status]||[doc.stay_status||"","grey"];,
    onload(listview) {
        if (typeof dh_get_session_property === 'function') {
            const sess = dh_get_session_property();
            if (sess && sess.property) {
                listview.filter_area.add([[listview.doctype, 'property', '=', sess.property]]);
            }
        }
    }
};
