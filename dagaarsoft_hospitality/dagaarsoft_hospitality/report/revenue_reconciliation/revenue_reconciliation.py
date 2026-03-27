import frappe
from frappe import _
from frappe.utils import flt, today


def execute(filters=None):
    filters = filters or {}
    from_date = filters.get("from_date") or today()
    to_date   = filters.get("to_date")   or today()

    columns = [
        {"label": _("Folio"),           "fieldname": "folio",          "fieldtype": "Link",     "options": "Guest Folio",   "width": 150},
        {"label": _("Guest"),           "fieldname": "guest_name",     "fieldtype": "Data",                                 "width": 150},
        {"label": _("Room"),            "fieldname": "room",           "fieldtype": "Link",     "options": "Room",          "width": 80},
        {"label": _("Arrival"),         "fieldname": "arrival_date",   "fieldtype": "Date",                                 "width": 100},
        {"label": _("Property"),        "fieldname": "property",       "fieldtype": "Link",     "options": "Property",      "width": 120},
        {"label": _("Folio Charges"),   "fieldname": "folio_charges",  "fieldtype": "Currency",                             "width": 130},
        {"label": _("SI Grand Total"),  "fieldname": "si_total",       "fieldtype": "Currency",                             "width": 130},
        {"label": _("GL Income"),       "fieldname": "gl_income",      "fieldtype": "Currency",                             "width": 130},
        {"label": _("PE Received"),     "fieldname": "pe_received",    "fieldtype": "Currency",                             "width": 130},
        {"label": _("Folio-SI Diff"),   "fieldname": "folio_si_diff",  "fieldtype": "Currency",                             "width": 120},
        {"label": _("SI-GL Diff"),      "fieldname": "si_gl_diff",     "fieldtype": "Currency",                             "width": 120},
        {"label": _("Status"),          "fieldname": "status",         "fieldtype": "Data",                                 "width": 120},
        {"label": _("Primary SI"),      "fieldname": "sales_invoice",  "fieldtype": "Link",     "options": "Sales Invoice", "width": 150},
        {"label": _("SI Count"),        "fieldname": "si_count",       "fieldtype": "Int",                                  "width": 80},
        {"label": _("Unbilled"),        "fieldname": "unbilled",       "fieldtype": "Currency",                             "width": 120},
    ]

    cond = ["gf.docstatus = 1"]
    vals = {"from_date": from_date, "to_date": to_date}
    cond.append("gs.arrival_date BETWEEN %(from_date)s AND %(to_date)s")
    if filters.get("property"):
        cond.append("gf.property = %(property)s")
        vals["property"] = filters["property"]
    where = "WHERE " + " AND ".join(cond)

    folios = frappe.db.sql(f"""
        SELECT gf.name folio, gf.property, gf.room, gf.sales_invoice,
               gf.customer, gf.billing_customer,
               gs.guest_name, gs.arrival_date, gs.stay_status
        FROM `tabGuest Folio` gf
        LEFT JOIN `tabGuest Stay` gs ON gs.name = gf.guest_stay
        {where}
        ORDER BY gs.arrival_date, gf.name
    """, vals, as_dict=True)

    data = []
    miss_count = 0
    totals = {"folio_charges": 0, "si_total": 0, "gl_income": 0,
              "pe_received": 0, "unbilled": 0}

    for f in folios:
        fn = f.folio

        # Folio charges (operational total)
        fc_total = flt(frappe.db.sql(
            "SELECT SUM(amount) FROM `tabFolio Charge Line` WHERE parent=%s AND is_void=0",
            fn)[0][0] or 0)
        unbilled = flt(frappe.db.sql(
            "SELECT SUM(amount) FROM `tabFolio Charge Line` WHERE parent=%s AND is_void=0 AND is_billed=0",
            fn)[0][0] or 0)

        # All submitted Sales Invoices
        si_rows = frappe.db.sql("""
            SELECT name, grand_total, is_return FROM `tabSales Invoice`
            WHERE hotel_folio=%s AND docstatus=1
        """, fn, as_dict=True)
        si_total = sum(
            flt(s.grand_total) if not s.is_return else -abs(flt(s.grand_total))
            for s in si_rows)
        si_count = len([s for s in si_rows if not s.is_return])
        si_names = [s.name for s in si_rows if not s.is_return]

        # GL income account credits (real accounting)
        gl_income = 0
        if si_names:
            gl_income = flt(frappe.db.sql("""
                SELECT SUM(credit) FROM `tabGL Entry`
                WHERE voucher_type='Sales Invoice'
                  AND voucher_no IN ({})
                  AND account IN (
                      SELECT name FROM `tabAccount`
                      WHERE account_type='Income Account' OR root_type='Income')
                  AND is_cancelled=0
            """.format(",".join(["%s"]*len(si_names))), si_names)[0][0] or 0)

        # Payment Entries
        reservation = frappe.db.get_value("Guest Stay",
            frappe.db.get_value("Guest Folio", fn, "guest_stay"), "reservation") or ""
        pe_cond = "(pe.hotel_folio=%s"
        pe_vals = [fn]
        if reservation:
            pe_cond += " OR (pe.hotel_reservation=%s AND (pe.hotel_folio IS NULL OR pe.hotel_folio=''))"
            pe_vals.append(reservation)
        pe_cond += ") AND pe.docstatus=1"
        pe_received = flt(frappe.db.sql(
            f"SELECT SUM(paid_amount) FROM `tabPayment Entry` pe WHERE {pe_cond}",
            pe_vals)[0][0] or 0)

        # Diffs
        folio_si_diff = fc_total - si_total
        si_gl_diff    = si_total - gl_income

        # Status flags
        flags = []
        if si_count == 0 and fc_total > 0:
            flags.append("No Invoice")
        if abs(folio_si_diff) > 0.01:
            flags.append("Folio≠SI")
        if abs(si_gl_diff) > 0.01 and si_total > 0:
            flags.append("SI≠GL")
        if unbilled > 0.01:
            flags.append("Unbilled:{:.2f}".format(unbilled))
        status = " | ".join(flags) if flags else "✓ OK"
        is_mismatch = bool(flags)
        if is_mismatch:
            miss_count += 1

        if filters.get("show_only_mismatches") and not is_mismatch:
            continue

        row = {
            "folio":         fn,
            "guest_name":    f.guest_name or "",
            "room":          f.room or "",
            "arrival_date":  f.arrival_date,
            "property":      f.property or "",
            "folio_charges": fc_total,
            "si_total":      si_total,
            "gl_income":     gl_income,
            "pe_received":   pe_received,
            "folio_si_diff": folio_si_diff,
            "si_gl_diff":    si_gl_diff,
            "status":        status,
            "sales_invoice": f.sales_invoice or "",
            "si_count":      si_count,
            "unbilled":      unbilled,
        }
        data.append(row)
        for k in totals:
            totals[k] += flt(row.get(k, 0))

    if data:
        data.append({
            "folio": "TOTAL", "guest_name": "", "room": "", "arrival_date": None,
            "property": "", "folio_si_diff": 0, "si_gl_diff": 0,
            "status": "{} mismatch(es)".format(miss_count),
            "sales_invoice": "", "si_count": None, **totals
        })

    report_summary = [
        {"value": totals["folio_charges"], "label": _("Folio Charges"),  "datatype": "Currency", "indicator": "blue"},
        {"value": totals["si_total"],      "label": _("SI Total"),       "datatype": "Currency", "indicator": "orange"},
        {"value": totals["gl_income"],     "label": _("GL Income"),      "datatype": "Currency", "indicator": "green"},
        {"value": totals["pe_received"],   "label": _("Payments"),       "datatype": "Currency", "indicator": "green"},
        {"value": miss_count,              "label": _("Mismatches"),     "datatype": "Int",
         "indicator": "red" if miss_count else "green"},
    ]
    return columns, data, None, None, report_summary
