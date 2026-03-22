frappe.ui.form.on("POS Invoice",{
    refresh(frm){
        if(frm.doc.charge_to_room)_show(frm);
        if(frm.doc.docstatus===0&&!frm.doc.charge_to_room)
            frm.add_custom_button(__("Charge to Room"),()=>{frm.set_value("charge_to_room",1);_show(frm);},__("Hotel"));
        if(frm.doc.docstatus===1&&frm.doc.hotel_charge_posted)
            frm.add_custom_button(__("View Folio"),()=>
                frappe.set_route("Form","Guest Folio",frm.doc.hotel_charge_ref),__("Hotel"));
    },
    charge_to_room(frm){
        if(frm.doc.charge_to_room)_show(frm);
        else["room_number","guest_stay_ref","guest_folio_ref"].forEach(f=>frm.set_value(f,""));
    },
    room_number(frm){
        if(!frm.doc.room_number)return;
        frappe.call({
            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.pos_bridge.pos_bridge.get_active_stay_for_room",
            args:{room_number:frm.doc.room_number},
            callback(r){
                if(r.message){
                    const s=r.message;
                    frm.set_value("guest_stay_ref",s.name);
                    frm.set_value("guest_folio_ref",s.guest_folio);
                    frappe.show_alert({message:"Guest: "+s.guest_name+" | Folio: "+(s.folio_status||""),
                        indicator:s.folio_status==="Open"?"green":"red"});
                    if(s.folio_status!=="Open")
                        frappe.msgprint(__("Warning: Folio is not Open. Room charge will be blocked."));
                }
            },
            error(){frappe.msgprint(__("No active checked-in guest for this room."));frm.set_value("room_number","");}
        });
    }
});
function _show(frm){
    ["room_number","guest_stay_ref","guest_folio_ref"].forEach(f=>frm.toggle_display(f,true));
    frm.toggle_reqd("room_number",true);frm.toggle_reqd("guest_stay_ref",true);
}
