frappe.listview_settings["Room"]={
    add_fields:["room_status","housekeeping_status","current_guest"],
    get_indicator(doc){
        const m={"Vacant Clean":["Vacant Clean","green"],"Vacant Dirty":["Vacant Dirty","yellow"],
            "Occupied":["Occupied","blue"],"Out of Order":["Out of Order","red"],
            "Out of Service":["Out of Service","red"],"On Change":["On Change","purple"]};
        return m[doc.room_status]||[doc.room_status||"","grey"];
    }
};