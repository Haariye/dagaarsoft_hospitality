frappe.listview_settings["Guest Stay"]={get_indicator(doc){
    const m={"Expected":["Expected","orange"],"Checked In":["Checked In","green"],
        "Checked Out":["Checked Out","grey"],"Cancelled":["Cancelled","red"],"No Show":["No Show","red"]};
    return m[doc.stay_status]||[doc.stay_status||"","grey"];
}};