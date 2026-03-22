// Sales Invoice - Hotel Room auto-populate
frappe.ui.form.on("Sales Invoice", {
    hotel_room(frm) {
        if (!frm.doc.hotel_room) {
            frm.set_value("hotel_stay",""); frm.set_value("hotel_folio",""); frm.set_value("hotel_guest_name",""); return;
        }
        frappe.call({
            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.get_room_billing_info",
            args: {room: frm.doc.hotel_room},
            callback(r) {
                if (!r.message) return;
                const info = r.message;
                frm.set_value("customer", info.customer);
                frm.set_value("hotel_stay", info.guest_stay);
                frm.set_value("hotel_folio", info.guest_folio);
                frm.set_value("hotel_guest_name", info.guest_name);
                let note = "Guest: " + info.guest_name;
                if (info.billing_customer && info.billing_customer !== info.guest_customer) note += " | Bill To: " + info.billing_customer;
                if (parseFloat(info.balance_due||0) > 0) note += " | Balance: " + parseFloat(info.balance_due).toLocaleString("en",{minimumFractionDigits:2});
                frappe.show_alert({message:note, indicator:"green"});
            },
            error() {
                frm.set_value("hotel_stay",""); frm.set_value("hotel_folio",""); frm.set_value("hotel_guest_name","");
                frappe.show_alert({message:__("Room has no active checked-in guest."), indicator:"red"});
            }
        });
    },
    refresh(frm) {
        if (frm.doc.hotel_room) frm.dashboard.add_indicator(
            "Room " + frm.doc.hotel_room + (frm.doc.hotel_guest_name ? " - " + frm.doc.hotel_guest_name : ""), "blue");
        if (frm.doc.hotel_folio && frm.doc.docstatus===1) frm.add_custom_button(__("View Guest Folio"),
            () => frappe.set_route("Form","Guest Folio",frm.doc.hotel_folio), __("Hotel"));
        if (frm.doc.hotel_stay) frm.add_custom_button(__("View Guest Stay"),
            () => frappe.set_route("Form","Guest Stay",frm.doc.hotel_stay), __("Hotel"));
    }
});
