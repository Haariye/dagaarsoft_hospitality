import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    if not filters: filters = {}
    columns = [
        {"label":_("Folio"),         "fieldname":"folio",      "fieldtype":"Link","options":"Guest Folio","width":140},
        {"label":_("Guest"),         "fieldname":"guest_name", "fieldtype":"Data","width":160},
        {"label":_("Room"),          "fieldname":"room",       "fieldtype":"Link","options":"Room","width":80},
        {"label":_("Check-In"),      "fieldname":"arrival",    "fieldtype":"Date","width":100},
        {"label":_("Invoice"),       "fieldname":"invoice",    "fieldtype":"Link","options":"Sales Invoice","width":140},
        {"label":_("Inv Status"),    "fieldname":"inv_status", "fieldtype":"Data","width":120},
        {"label":_("Outstanding"),   "fieldname":"outstanding","fieldtype":"Currency","width":120},
        {"label":_("0-7 Days"),      "fieldname":"b0_7",       "fieldtype":"Currency","width":110},
        {"label":_("8-30 Days"),     "fieldname":"b8_30",      "fieldtype":"Currency","width":110},
        {"label":_("31-60 Days"),    "fieldname":"b31_60",     "fieldtype":"Currency","width":110},
        {"label":_("60+ Days"),      "fieldname":"b60",        "fieldtype":"Currency","width":110},
    ]
    cond = ["gf.folio_status='Open'","gf.docstatus=1","gf.balance_due>0.01"]
    vals = {}
    if filters.get("from_date"):
        cond.append("gs.arrival_date>=%(from_date)s"); vals["from_date"]=filters["from_date"]
    if filters.get("to_date"):
        cond.append("gs.arrival_date<=%(to_date)s"); vals["to_date"]=filters["to_date"]
    if filters.get("property"):
        cond.append("gf.property=%(property)s"); vals["property"]=filters["property"]
    where = "WHERE " + " AND ".join(cond)
    rows = frappe.db.sql(f"""
        SELECT gf.name folio, gs.guest_name, gf.room, gs.arrival_date arrival,
               gf.sales_invoice invoice, gf.sales_invoice_status inv_status,
               gf.balance_due outstanding, gf.property,
               DATEDIFF(CURDATE(), IFNULL(gs.arrival_date,CURDATE())) age_days
        FROM `tabGuest Folio` gf
        LEFT JOIN `tabGuest Stay` gs ON gs.name=gf.guest_stay
        {where} ORDER BY outstanding DESC
    """, vals, as_dict=True)
    data = []
    for r in rows:
        age=int(r.age_days or 0); ost=flt(r.outstanding)
        row=dict(r)
        row["b0_7"]  =ost if age<=7    else 0
        row["b8_30"] =ost if 8<=age<=30 else 0
        row["b31_60"]=ost if 31<=age<=60 else 0
        row["b60"]   =ost if age>60    else 0
        data.append(row)
    if data:
        data.append({"folio":"TOTAL","guest_name":"","room":"","arrival":None,
            "invoice":"","inv_status":"",
            "outstanding":sum(flt(r.get("outstanding",0)) for r in data),
            "b0_7": sum(flt(r.get("b0_7",0))   for r in data),
            "b8_30":sum(flt(r.get("b8_30",0))  for r in data),
            "b31_60":sum(flt(r.get("b31_60",0))for r in data),
            "b60":  sum(flt(r.get("b60",0))    for r in data),
        })
    return columns, data
