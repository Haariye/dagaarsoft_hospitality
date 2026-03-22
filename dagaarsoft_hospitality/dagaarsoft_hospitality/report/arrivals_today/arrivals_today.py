import frappe
from frappe import _
from frappe.utils import today as get_today

def execute(filters=None):
    if not filters: filters = {}
    date = filters.get("date") or get_today()
    prop = filters.get("property") or None
    columns = [
        {"label":_("Reservation"),"fieldname":"reservation","fieldtype":"Data","width":140},
        {"label":_("Guest"),"fieldname":"guest_name","fieldtype":"Data","width":160},
        {"label":_("Room Type"),"fieldname":"room_type","fieldtype":"Data","width":120},
        {"label":_("Room"),"fieldname":"room","fieldtype":"Data","width":80},
        {"label":_("Status"),"fieldname":"stay_status","fieldtype":"Data","width":110},
        {"label":_("Nights"),"fieldname":"num_nights","fieldtype":"Int","width":70},
        {"label":_("VIP"),"fieldname":"vip_status","fieldtype":"Data","width":80},
    ]
    f = {"arrival_date": date, "stay_status": ["in",["Expected","Checked In"]]}
    if prop: f["property"] = prop
    data = frappe.db.get_all("Guest Stay", filters=f,
        fields=["reservation","guest_name","room_type","room","stay_status","num_nights","vip_status"])
    for row in data:
        for k in row:
            if row[k] is None: row[k] = ""
    return columns, data
