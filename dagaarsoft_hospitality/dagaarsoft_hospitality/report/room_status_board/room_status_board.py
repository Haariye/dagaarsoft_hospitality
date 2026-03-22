import frappe
from frappe import _

def execute(filters=None):
    if not filters: filters = {}
    prop  = filters.get("property") or None
    floor = filters.get("floor") or None
    columns = [
        {"label":_("Room"),"fieldname":"room_number","fieldtype":"Data","width":90},
        {"label":_("Type"),"fieldname":"room_type","fieldtype":"Data","width":110},
        {"label":_("Floor"),"fieldname":"floor","fieldtype":"Data","width":70},
        {"label":_("Room Status"),"fieldname":"room_status","fieldtype":"Data","width":120},
        {"label":_("HK Status"),"fieldname":"housekeeping_status","fieldtype":"Data","width":110},
        {"label":_("Current Guest"),"fieldname":"current_guest","fieldtype":"Data","width":150},
        {"label":_("OOO"),"fieldname":"is_out_of_order","fieldtype":"Check","width":60},
    ]
    f = {"is_active": 1}
    if prop:  f["property"] = prop
    if floor: f["floor"] = floor
    data = frappe.db.get_all("Room", filters=f,
        fields=["room_number","room_type","floor","room_status","housekeeping_status","current_guest","is_out_of_order"],
        order_by="floor asc, room_number asc")
    for row in data:
        for k in row:
            if row[k] is None: row[k] = ""
    return columns, data
