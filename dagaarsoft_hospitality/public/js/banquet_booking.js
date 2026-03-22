frappe.ui.form.on("Banquet Booking",{
    refresh(frm){
        frm.set_query("banquet_hall",()=>({filters:frm.doc.property?{property:frm.doc.property,is_active:1}:{}}));
        frm.set_query("banquet_package",()=>({filters:frm.doc.property?{property:frm.doc.property,is_active:1}:{}}));
    },
    property(frm){frm.set_value("banquet_hall","");},
    banquet_package(frm){
        if(frm.doc.banquet_package)
            frappe.db.get_value("Banquet Package",frm.doc.banquet_package,"package_rate",r=>{
                if(r&&r.package_rate)frm.set_value("total_amount",r.package_rate);
            });
    }
});
