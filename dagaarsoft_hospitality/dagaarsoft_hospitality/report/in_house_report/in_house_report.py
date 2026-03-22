import frappe
from frappe import _
from frappe.utils import today as get_today

def execute(filters=None):
    if not filters: filters = {}
    date = filters.get("date") or get_today()
    prop = filters.get("property") or None
    columns = [
        {"label":_("Stay"),"fieldname":"name","fieldtype":"Link","options":"Guest Stay","width":140},
        {"label":_("Room"),"fieldname":"room","fieldtype":"Data","width":80},
        {"label":_("Guest"),"fieldname":"guest_name","fieldtype":"Data","width":160},
        {"label":_("Arrival"),"fieldname":"arrival_date","fieldtype":"Date","width":100},
        {"label":_("Departure"),"fieldname":"departure_date","fieldtype":"Date","width":100},
        {"label":_("Nights"),"fieldname":"num_nights","fieldtype":"Int","width":70},
        {"label":_("Balance"),"fieldname":"balance_due","fieldtype":"Currency","width":120},
        {"label":_("Invoice"),"fieldname":"sales_invoice","fieldtype":"Data","width":120},
        {"label":_("VIP"),"fieldname":"vip_status","fieldtype":"Data","width":80},
    ]
    conditions = "gs.stay_status='Checked In' AND gs.arrival_date<=%s AND gs.departure_date>%s"
    values = [date, date]
    if prop:
        conditions += " AND gs.property=%s"
        values.append(prop)
    stays = frappe.db.sql("""
        SELECT gs.name, gs.room, gs.guest_name, gs.arrival_date, gs.departure_date,
               gs.num_nights, gs.vip_status, gs.guest_folio
        FROM `tabGuest Stay` gs
        WHERE {cond}
        ORDER BY gs.room
    """.format(cond=conditions), values, as_dict=True)
    for s in stays:
        s["balance_due"] = 0.0
        s["sales_invoice"] = ""
        if s.get("guest_folio"):
            row = frappe.db.get_value("Guest Folio", s["guest_folio"],
                ["balance_due","sales_invoice"], as_dict=True)
            if row:
                s["balance_due"] = float(row.get("balance_due") or 0)
                s["sales_invoice"] = row.get("sales_invoice") or ""
    return columns, stays
