import frappe
from frappe import _
from frappe.utils import flt, today

def execute(filters=None):
    if not filters: filters = {}
    columns = [
        {"label":_("Date"),       "fieldname":"posting_date", "fieldtype":"Date",    "width":100},
        {"label":_("Category"),   "fieldname":"charge_category","fieldtype":"Data",  "width":140},
        {"label":_("Description"),"fieldname":"description",  "fieldtype":"Data",   "width":220},
        {"label":_("Room"),       "fieldname":"room",         "fieldtype":"Link","options":"Room","width":80},
        {"label":_("Guest"),      "fieldname":"guest_name",   "fieldtype":"Data",   "width":150},
        {"label":_("Qty"),        "fieldname":"qty",          "fieldtype":"Float",  "width":60},
        {"label":_("Rate"),       "fieldname":"rate",         "fieldtype":"Currency","width":110},
        {"label":_("Amount"),     "fieldname":"amount",       "fieldtype":"Currency","width":120},
    ]
    cond = ["fcl.is_void=0","gf.docstatus=1"]
    vals = {}
    from_date = filters.get("from_date") or today()
    to_date   = filters.get("to_date")   or today()
    cond.append("fcl.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    vals["from_date"] = from_date; vals["to_date"] = to_date
    if filters.get("property"):
        cond.append("gf.property=%(property)s"); vals["property"] = filters["property"]
    where = "WHERE " + " AND ".join(cond)
    rows = frappe.db.sql(f"""
        SELECT fcl.posting_date, fcl.charge_category, fcl.description,
               gf.room, gs.guest_name, fcl.qty, fcl.rate, fcl.amount
        FROM `tabFolio Charge Line` fcl
        JOIN `tabGuest Folio` gf ON gf.name=fcl.parent
        LEFT JOIN `tabGuest Stay` gs ON gs.name=fcl.guest_stay
        {where}
        ORDER BY fcl.posting_date, fcl.charge_category
    """, vals, as_dict=True)
    data = []; cat_totals = {}
    for r in rows:
        row = {k:(v if v is not None else (0 if k in ("qty","rate","amount") else ""))
               for k,v in r.items()}
        data.append(row)
        cat = str(row.get("charge_category","") or "Misc")
        cat_totals[cat] = cat_totals.get(cat,0) + flt(row.get("amount",0))
    if data:
        data.append({})
        for cat,total in sorted(cat_totals.items()):
            data.append({"charge_category":f"{cat} Subtotal","amount":total,
                         "posting_date":None,"description":"","room":"","guest_name":"","qty":None,"rate":None})
        data.append({"charge_category":"GRAND TOTAL","amount":sum(cat_totals.values()),
                     "posting_date":None,"description":"","room":"","guest_name":"","qty":None,"rate":None})
    return columns, data
