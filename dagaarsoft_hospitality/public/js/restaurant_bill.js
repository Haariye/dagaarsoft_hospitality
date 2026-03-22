frappe.ui.form.on("Restaurant Bill",{
    refresh(frm){
        frm.set_query("outlet",()=>({filters:frm.doc.property?{property:frm.doc.property,is_active:1}:{}}));
        if(frm.doc.charge_to_room)
            frm.set_query("guest_stay",()=>({filters:{stay_status:"Checked In",
                ...(frm.doc.property?{property:frm.doc.property}:{})}}));
        if(frm.doc.docstatus===1&&frm.doc.guest_stay&&frm.doc.charge_to_room)
            frm.add_custom_button(__("Create Room Service POS Order"),()=>{
                frappe.call({
                    method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_bill.restaurant_bill.create_room_service_pos_draft",
                    args:{guest_stay_name:frm.doc.guest_stay,outlet_name:frm.doc.outlet},
                    callback(r){
                        if(r.message)
                            frappe.set_route("Form","POS Invoice",r.message);
                    }
                });
            },__("POS"));
    },
    charge_to_room(frm){
        if(frm.doc.charge_to_room)
            frm.set_query("guest_stay",()=>({filters:{stay_status:"Checked In"}}));
    }
});
