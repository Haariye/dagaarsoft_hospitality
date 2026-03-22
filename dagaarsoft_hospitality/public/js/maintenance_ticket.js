frappe.ui.form.on("Maintenance Ticket",{
    refresh(frm){
        frm.set_query("room",()=>({filters:frm.doc.property?{property:frm.doc.property}:{}}));
        if(frm.doc.room){
            frappe.db.get_value("Room",frm.doc.room,"room_status",r=>{
                if(r) frm.dashboard.add_indicator("Room Status: "+r.room_status,
                    r.room_status==="Out of Order"?"red":"green");
            });
        }
    },
    property(frm){frm.set_value("room","");}
});
