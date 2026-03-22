import frappe
from frappe import _
from frappe.utils import today as get_today

def execute(filters=None):
    if not filters: filters = {}
    date     = filters.get("date") or get_today()
    prop     = filters.get("property") or None
    assigned = filters.get("assigned_to") or None
    columns = [
        {"label":_("Task"),"fieldname":"name","fieldtype":"Data","width":130},
        {"label":_("Room"),"fieldname":"room","fieldtype":"Data","width":90},
        {"label":_("Floor"),"fieldname":"floor","fieldtype":"Data","width":70},
        {"label":_("Task Type"),"fieldname":"task_type","fieldtype":"Data","width":110},
        {"label":_("Status"),"fieldname":"task_status","fieldtype":"Data","width":110},
        {"label":_("Priority"),"fieldname":"priority","fieldtype":"Data","width":80},
        {"label":_("Assigned To"),"fieldname":"assigned_to","fieldtype":"Data","width":130},
        {"label":_("Completed At"),"fieldname":"completed_at","fieldtype":"Datetime","width":140},
    ]
    f = {"task_date": date, "docstatus": ["!=", 2]}
    if prop:     f["property"] = prop
    if assigned: f["assigned_to"] = assigned
    tasks = frappe.db.get_all("Housekeeping Task", filters=f,
        fields=["name","room","task_type","task_status","priority","assigned_to","completed_at"],
        order_by="priority desc, room asc")
    for t in tasks:
        floor = frappe.db.get_value("Room", t.get("room"), "floor") if t.get("room") else ""
        t["floor"] = floor or ""
        for k in t:
            if t[k] is None: t[k] = ""
    return columns, tasks
