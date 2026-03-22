frappe.listview_settings["Housekeeping Task"]={
    add_fields:["task_status","priority","room"],
    get_indicator(doc){
        const m={"Pending":["Pending","orange"],"In Progress":["In Progress","blue"],
            "Completed":["Completed","green"],"Skipped":["Skipped","grey"],
            "Do Not Disturb":["DND","red"]};
        return m[doc.task_status]||[doc.task_status||"","grey"];
    },
    onload(lv){
        // Add bulk action buttons for housekeeper board
        lv.page.add_action_item(__("Mark Selected Clean"),()=>{
            const names=lv.get_checked_items().map(d=>d.name);
            if(!names.length){frappe.msgprint("Select tasks first.");return;}
            frappe.call({
                method:"frappe.client.get_list",
                args:{doctype:"Housekeeping Task",filters:[["name","in",names]],fields:["name"]},
                callback(){
                    names.forEach(n=>{
                        frappe.call({method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.housekeeping_task.housekeeping_task.quick_update_status",
                            args:{task_name:n,new_status:"Completed"}});
                    });
                    setTimeout(()=>lv.refresh(),1500);
                }
            });
        });
    }
};