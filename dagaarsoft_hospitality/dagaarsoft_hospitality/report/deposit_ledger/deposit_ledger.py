import frappe
from frappe import _
from frappe.utils import flt, today


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Deposit"),        "fieldname": "name",           "fieldtype": "Link",     "options": "Hotel Deposit",    "width": 150},
        {"label": _("Date"),           "fieldname": "deposit_date",   "fieldtype": "Date",                                    "width": 100},
        {"label": _("Customer"),       "fieldname": "customer_name",  "fieldtype": "Data",                                    "width": 160},
        {"label": _("Property"),       "fieldname": "property",       "fieldtype": "Link",     "options": "Property",         "width": 120},
        {"label": _("Reservation"),    "fieldname": "reservation",    "fieldtype": "Link",     "options": "Reservation",      "width": 150},
        {"label": _("Guest Stay"),     "fieldname": "guest_stay",     "fieldtype": "Link",     "options": "Guest Stay",       "width": 130},
        {"label": _("Folio"),          "fieldname": "folio",          "fieldtype": "Link",     "options": "Guest Folio",      "width": 150},
        {"label": _("Mode"),           "fieldname": "payment_mode",   "fieldtype": "Data",                                    "width": 100},
        {"label": _("Collected"),      "fieldname": "deposit_amount", "fieldtype": "Currency",                                "width": 120},
        {"label": _("Applied"),        "fieldname": "applied_amount", "fieldtype": "Currency",                                "width": 120},
        {"label": _("Refunded"),       "fieldname": "refund_amount",  "fieldtype": "Currency",                                "width": 120},
        {"label": _("Balance Held"),   "fieldname": "balance_held",   "fieldtype": "Currency",                                "width": 120},
        {"label": _("Status"),         "fieldname": "deposit_status", "fieldtype": "Data",                                    "width": 100},
        {"label": _("Payment Entry"),  "fieldname": "payment_entry",  "fieldtype": "Link",     "options": "Payment Entry",    "width": 150},
        {"label": _("PE Status"),      "fieldname": "pe_status",      "fieldtype": "Data",                                    "width": 100},
        {"label": _("Applied To SI"),  "fieldname": "applied_to_si",  "fieldtype": "Link",     "options": "Sales Invoice",    "width": 150},
        {"label": _("GL Verified"),    "fieldname": "gl_verified",    "fieldtype": "Data",                                    "width": 100},
        {"label": _("Reference"),      "fieldname": "reference_no",   "fieldtype": "Data",                                    "width": 130},
    ]

    cond = ["hd.docstatus = 1"]
    vals = {}
    if filters.get("property"):
        cond.append("hd.property = %(property)s"); vals["property"] = filters["property"]
    if filters.get("customer"):
        cond.append("hd.customer = %(customer)s"); vals["customer"] = filters["customer"]
    if filters.get("from_date"):
        cond.append("hd.deposit_date >= %(from_date)s"); vals["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        cond.append("hd.deposit_date <= %(to_date)s"); vals["to_date"] = filters["to_date"]
    if filters.get("deposit_status"):
        cond.append("hd.deposit_status = %(deposit_status)s")
        vals["deposit_status"] = filters["deposit_status"]
    where = "WHERE " + " AND ".join(cond)

    deposits = frappe.db.sql(f"""
        SELECT hd.name, hd.deposit_date, hd.customer, hd.property,
               hd.reservation, hd.guest_stay, hd.payment_mode,
               hd.deposit_amount, hd.applied_amount, hd.refund_amount,
               hd.balance_deposit, hd.deposit_status, hd.payment_entry,
               hd.applied_to_invoice, hd.reference_number,
               c.customer_name
        FROM `tabHotel Deposit` hd
        LEFT JOIN `tabCustomer` c ON c.name = hd.customer
        {where}
        ORDER BY hd.deposit_date DESC, hd.name
    """, vals, as_dict=True)

    data = []
    totals = {"deposit_amount": 0, "applied_amount": 0,
              "refund_amount": 0, "balance_held": 0}

    for d in deposits:
        # Get folio from guest_stay
        folio = ""
        if d.guest_stay:
            folio = frappe.db.get_value("Guest Stay", d.guest_stay, "guest_folio") or ""

        # Verify Payment Entry status
        pe_status = ""
        if d.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", d.payment_entry,
                ["status"], as_dict=True)
            pe_status = pe_status.status if pe_status else "Not Found"

        # GL verification: check if PE has a corresponding GL Entry
        gl_verified = "N/A"
        if d.payment_entry:
            gl_count = frappe.db.sql("""
                SELECT COUNT(*) FROM `tabGL Entry`
                WHERE voucher_type='Payment Entry' AND voucher_no=%s AND is_cancelled=0
            """, d.payment_entry)[0][0]
            gl_verified = "✓ {0} entries".format(gl_count) if gl_count else "✗ No GL"

        balance_held = flt(d.deposit_amount) - flt(d.applied_amount) - flt(d.refund_amount)

        row = {
            "name":           d.name,
            "deposit_date":   d.deposit_date,
            "customer_name":  d.customer_name or d.customer or "",
            "property":       d.property or "",
            "reservation":    d.reservation or "",
            "guest_stay":     d.guest_stay or "",
            "folio":          folio,
            "payment_mode":   d.payment_mode or "",
            "deposit_amount": flt(d.deposit_amount),
            "applied_amount": flt(d.applied_amount),
            "refund_amount":  flt(d.refund_amount),
            "balance_held":   balance_held,
            "deposit_status": d.deposit_status or "",
            "payment_entry":  d.payment_entry or "",
            "pe_status":      pe_status,
            "applied_to_si":  d.applied_to_invoice or "",
            "gl_verified":    gl_verified,
            "reference_no":   d.reference_number or "",
        }
        data.append(row)
        for k in totals:
            totals[k] += flt(row.get(k, 0))

    if data:
        data.append({
            "name": "TOTAL", "deposit_date": None, "customer_name": "",
            "property": "", "reservation": "", "guest_stay": "", "folio": "",
            "payment_mode": "", "deposit_status": "", "payment_entry": "",
            "pe_status": "", "applied_to_si": "", "gl_verified": "",
            "reference_no": "", **totals
        })

    report_summary = [
        {"value": totals["deposit_amount"], "label": _("Total Collected"), "datatype": "Currency", "indicator": "blue"},
        {"value": totals["applied_amount"], "label": _("Total Applied"),   "datatype": "Currency", "indicator": "orange"},
        {"value": totals["refund_amount"],  "label": _("Total Refunded"),  "datatype": "Currency", "indicator": "red"},
        {"value": totals["balance_held"],   "label": _("Balance Held"),    "datatype": "Currency", "indicator": "green"},
    ]
    return columns, data, None, None, report_summary
