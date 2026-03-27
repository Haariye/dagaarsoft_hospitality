import frappe
from frappe import _
from frappe.utils import flt, today, getdate


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Lease"),        "fieldname": "lease",        "fieldtype": "Link",     "options": "RE Lease",      "width": 160},
        {"label": _("Unit"),         "fieldname": "unit",         "fieldtype": "Link",     "options": "RE Unit",       "width": 120},
        {"label": _("Tenant"),       "fieldname": "tenant_name",  "fieldtype": "Data",                                 "width": 160},
        {"label": _("Property"),     "fieldname": "property",     "fieldtype": "Link",     "options": "RE Property",   "width": 130},
        {"label": _("Period"),       "fieldname": "period",       "fieldtype": "Data",                                 "width": 110},
        {"label": _("Due Date"),     "fieldname": "due_date",     "fieldtype": "Date",                                 "width": 100},
        {"label": _("Amount"),       "fieldname": "amount",       "fieldtype": "Currency",                             "width": 110},
        {"label": _("Status"),       "fieldname": "status",       "fieldtype": "Data",                                 "width": 100},
        {"label": _("Invoice"),      "fieldname": "sales_invoice","fieldtype": "Link",     "options": "Sales Invoice", "width": 160},
        {"label": _("Payment"),      "fieldname": "payment_entry","fieldtype": "Link",     "options": "Payment Entry", "width": 160},
        {"label": _("Paid Date"),    "fieldname": "paid_date",    "fieldtype": "Date",                                 "width": 100},
        {"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int",                                  "width": 100},
    ]

    cond = [
        "rl.docstatus = 1",
        "rl.lease_status IN ('Active','Expiring Soon','Expired')",
    ]
    vals = {}
    if filters.get("property"):
        cond.append("rl.property = %(property)s")
        vals["property"] = filters["property"]
    if filters.get("tenant"):
        cond.append("rl.tenant = %(tenant)s")
        vals["tenant"] = filters["tenant"]
    if filters.get("from_date"):
        cond.append("rsl.due_date >= %(from_date)s")
        vals["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        cond.append("rsl.due_date <= %(to_date)s")
        vals["to_date"] = filters["to_date"]
    if filters.get("status"):
        cond.append("rsl.status = %(status)s")
        vals["status"] = filters["status"]

    where = " AND ".join(cond)

    rows = frappe.db.sql("""
        SELECT
            rsl.name            AS sched_name,
            rsl.period,
            rsl.due_date,
            rsl.amount,
            rsl.status,
            rsl.sales_invoice,
            rsl.payment_entry,
            rsl.paid_date,
            rl.name             AS lease,
            rl.unit,
            rl.property,
            IFNULL(rt.tenant_name, rl.tenant) AS tenant_name
        FROM `tabRE Rent Schedule Line` rsl
        INNER JOIN `tabRE Lease` rl ON rl.name = rsl.parent
        LEFT JOIN `tabRE Tenant` rt ON rt.name = rl.tenant
        WHERE {0}
        ORDER BY rsl.due_date DESC
    """.format(where), vals, as_dict=True)

    today_date = getdate(today())
    data = []
    totals = {"amount": 0}
    pending = invoiced = paid = overdue = 0

    for r in rows:
        days_overdue = 0
        if r.status in ("Pending", "Invoiced") and r.due_date:
            if getdate(r.due_date) < today_date:
                days_overdue = (today_date - getdate(r.due_date)).days

        data.append({
            "lease":         r.lease or "",
            "unit":          r.unit or "",
            "tenant_name":   r.tenant_name or "",
            "property":      r.property or "",
            "period":        r.period or "",
            "due_date":      r.due_date,
            "amount":        flt(r.amount),
            "status":        r.status or "",
            "sales_invoice": r.sales_invoice or "",
            "payment_entry": r.payment_entry or "",
            "paid_date":     r.paid_date,
            "days_overdue":  days_overdue,
        })
        totals["amount"] += flt(r.amount)
        if r.status == "Paid":        paid     += 1
        elif r.status == "Invoiced":  invoiced += 1
        elif r.status == "Overdue":   overdue  += 1
        else:                         pending  += 1

    report_summary = [
        {"value": pending,          "label": _("Pending"),      "datatype": "Int",      "indicator": "orange"},
        {"value": invoiced,         "label": _("Invoiced"),     "datatype": "Int",      "indicator": "blue"},
        {"value": paid,             "label": _("Paid"),         "datatype": "Int",      "indicator": "green"},
        {"value": overdue,          "label": _("Overdue"),      "datatype": "Int",      "indicator": "red"},
        {"value": totals["amount"], "label": _("Total Amount"), "datatype": "Currency", "indicator": "blue"},
    ]
    return columns, data, None, None, report_summary
