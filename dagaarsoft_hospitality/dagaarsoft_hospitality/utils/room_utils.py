import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def get_billing_info_for_room(room):
    if not room:
        frappe.throw(_("Room is required."))
    room_doc = frappe.db.get_value("Room", room,
        ["room_status", "current_stay", "current_guest", "property"], as_dict=True)
    if not room_doc:
        frappe.throw(_("Room {0} not found.").format(room))
    if room_doc.room_status != "Occupied" or not room_doc.current_stay:
        frappe.throw(_("Room {0} is {1} — no active guest.").format(
            room, room_doc.room_status))
    stay = frappe.db.get_value("Guest Stay", room_doc.current_stay,
        ["name", "customer", "guest_name", "guest_folio", "billing_customer",
         "billing_instruction", "stay_status", "arrival_date", "departure_date",
         "nightly_rate"], as_dict=True)
    if not stay:
        frappe.throw(_("Guest Stay not found for Room {0}.").format(room))
    if stay.stay_status != "Checked In":
        frappe.throw(_("Guest in Room {0} is not checked in (status: {1}).").format(
            room, stay.stay_status))
    balance_due = 0
    if stay.guest_folio:
        balance_due = flt(frappe.db.get_value(
            "Guest Folio", stay.guest_folio, "balance_due") or 0)
    return {
        "guest_stay":          stay.name,
        "guest_folio":         stay.guest_folio,
        "customer":            stay.billing_customer or stay.customer,
        "guest_customer":      stay.customer,
        "guest_name":          stay.guest_name or room_doc.current_guest,
        "billing_customer":    stay.billing_customer,
        "billing_instruction": stay.billing_instruction,
        "room_status":         room_doc.room_status,
        "property":            room_doc.property,
        "arrival_date":        str(stay.arrival_date or ""),
        "departure_date":      str(stay.departure_date or ""),
        "nightly_rate":        flt(stay.nightly_rate),
        "balance_due":         balance_due,
    }

@frappe.whitelist()
def get_room_billing_info(room):
    return get_billing_info_for_room(room)


@frappe.whitelist()
def get_all_occupied_rooms(property_name=None):
    """FIX 13: Return occupied rooms with guest info for POSA selector."""
    filters = {"room_status": "Occupied"}
    if property_name:
        filters["property"] = property_name
    rooms = frappe.db.get_all("Room", filters=filters,
        fields=["name", "room_type", "current_guest", "current_stay", "floor", "property"])
    result = []
    for r in rooms:
        if not r.current_stay:
            continue
        stay = frappe.db.get_value("Guest Stay", r.current_stay,
            ["guest_name", "stay_status", "guest_folio"], as_dict=True)
        if not stay or stay.stay_status != "Checked In":
            continue
        result.append({
            "name": r.name,
            "label": "Room {0} — {1}".format(r.name, stay.guest_name or r.current_guest or ""),
            "room_type": r.room_type or "",
            "current_guest": stay.guest_name or r.current_guest or "",
            "floor": r.floor or "",
            "property": r.property or "",
            "guest_folio": stay.guest_folio or "",
            "guest_stay": r.current_stay or "",
        })
    return result
