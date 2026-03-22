import frappe
from frappe import _
from frappe.utils import today as get_today

def execute(filters=None):
    if not filters: filters = {}
    date = filters.get("date") or get_today()
    prop = filters.get("property") or None
    columns = [
        {"label":_("Stay"),"fieldname":"name","fieldtype":"Data","width":140},
        {"label":_("Guest"),"fieldname":"guest_name","fieldtype":"Data","width":160},
        {"label":_("Room"),"fieldname":"room","fieldtype":"Data","width":80},
        {"label":_("Status"),"fieldname":"stay_status","fieldtype":"Data","width":110},
        {"label":_("Balance Due"),"fieldname":"balance_due","fieldtype":"Currency","width":130},
        {"label":_("Invoice Status"),"fieldname":"invoice_status","fieldtype":"Data","width":120},
    ]
    f = {"departure_date": date, "stay_status": ["in",["Checked In","Expected"]]}
    if prop: f["property"] = prop
    stays = frappe.db.get_all("Guest Stay", filters=f,
        fields=["name","guest_name","room","stay_status","guest_folio"])
    data = []
    for s in stays:
        row = dict(s)
        row["balance_due"] = 0.0
        row["invoice_status"] = ""
        if s.get("guest_folio"):
            fd = frappe.db.get_value("Guest Folio", s["guest_folio"],
                ["balance_due","sales_invoice"], as_dict=True)
            if fd:
                row["balance_due"] = float(fd.get("balance_due") or 0)
                si = fd.get("sales_invoice")
                if si:
                    row["invoice_status"] = frappe.db.get_value("Sales Invoice", si, "status") or ""
        for k in row:
            if row[k] is None: row[k] = ""
        data.append(row)
    return columns, data
