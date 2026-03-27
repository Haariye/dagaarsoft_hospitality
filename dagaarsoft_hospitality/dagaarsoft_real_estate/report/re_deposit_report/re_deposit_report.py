import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    filters = filters or {}
    columns = [
        {"label":_("Deposit"),       "fieldname":"name",          "fieldtype":"Link",    "options":"RE Deposit",      "width":160},
        {"label":_("Date"),          "fieldname":"deposit_date",  "fieldtype":"Date",                                 "width":100},
        {"label":_("Lease"),         "fieldname":"lease",         "fieldtype":"Link",    "options":"RE Lease",        "width":160},
        {"label":_("Tenant"),        "fieldname":"tenant_name",   "fieldtype":"Data",                                 "width":160},
        {"label":_("Unit"),          "fieldname":"unit",          "fieldtype":"Link",    "options":"RE Unit",         "width":120},
        {"label":_("Type"),          "fieldname":"deposit_type",  "fieldtype":"Data",                                 "width":120},
        {"label":_("Amount"),        "fieldname":"amount",        "fieldtype":"Currency",                             "width":120},
        {"label":_("Status"),        "fieldname":"deposit_status","fieldtype":"Data",                                 "width":110},
        {"label":_("Payment Entry"), "fieldname":"payment_entry", "fieldtype":"Link",    "options":"Payment Entry",   "width":160},
        {"label":_("Refund Amount"), "fieldname":"refund_amount", "fieldtype":"Currency",                             "width":120},
        {"label":_("Deductions"),    "fieldname":"deductions",    "fieldtype":"Currency",                             "width":110},
        {"label":_("GL Verified"),   "fieldname":"gl_verified",   "fieldtype":"Data",                                 "width":100},
    ]

    cond = ["rd.docstatus = 1"]
    vals = {}
    if filters.get("from_date"):
        cond.append("rd.deposit_date >= %(from_date)s"); vals["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        cond.append("rd.deposit_date <= %(to_date)s"); vals["to_date"] = filters["to_date"]
    if filters.get("deposit_status"):
        cond.append("rd.deposit_status = %(deposit_status)s"); vals["deposit_status"] = filters["deposit_status"]
    if filters.get("property"):
        cond.append("rl.property = %(property)s"); vals["property"] = filters["property"]

    deposits = frappe.db.sql("""
        SELECT rd.name, rd.deposit_date, rd.lease, rd.unit, rd.deposit_type,
               rd.amount, rd.deposit_status, rd.payment_entry,
               rd.refund_amount, rd.deductions,
               rt.tenant_name
        FROM `tabRE Deposit` rd
        LEFT JOIN `tabRE Lease` rl ON rl.name = rd.lease
        LEFT JOIN `tabRE Tenant` rt ON rt.name = rl.tenant
        WHERE {0}
        ORDER BY rd.deposit_date DESC
    """.format(" AND ".join(cond)), vals, as_dict=True)

    data = []
    totals = {"amount":0,"refund_amount":0,"deductions":0}
    for d in deposits:
        gl_cnt = 0
        if d.payment_entry:
            gl_cnt = frappe.db.sql(
                "SELECT COUNT(*) FROM `tabGL Entry` WHERE voucher_type='Payment Entry' AND voucher_no=%s AND is_cancelled=0",
                d.payment_entry)[0][0]
        row = {
            "name":           d.name,
            "deposit_date":   d.deposit_date,
            "lease":          d.lease or "",
            "tenant_name":    d.tenant_name or "",
            "unit":           d.unit or "",
            "deposit_type":   d.deposit_type or "",
            "amount":         flt(d.amount),
            "deposit_status": d.deposit_status or "",
            "payment_entry":  d.payment_entry or "",
            "refund_amount":  flt(d.refund_amount),
            "deductions":     flt(d.deductions),
            "gl_verified":    "\u2713 {0} GL".format(gl_cnt) if gl_cnt else "\u2717 No GL",
        }
        data.append(row)
        for k in ["amount","refund_amount","deductions"]:
            totals[k] += flt(row[k])

    report_summary = [
        {"value":len(data),             "label":_("Deposits"),       "datatype":"Int",      "indicator":"blue"},
        {"value":totals["amount"],      "label":_("Total Collected"), "datatype":"Currency", "indicator":"blue"},
        {"value":totals["refund_amount"],"label":_("Refunded"),      "datatype":"Currency", "indicator":"orange"},
        {"value":totals["deductions"],  "label":_("Deductions"),     "datatype":"Currency", "indicator":"red"},
        {"value":totals["amount"]-totals["refund_amount"]-totals["deductions"],
         "label":_("Balance Held"),     "datatype":"Currency",        "indicator":"green"},
    ]
    return columns, data, None, None, report_summary
