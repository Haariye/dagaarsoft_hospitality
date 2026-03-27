import frappe
from frappe import _
from frappe.utils import flt, today, add_days


def execute(filters=None):
    filters = filters or {}
    from_date = filters.get("from_date") or today()
    to_date   = filters.get("to_date")   or today()
    prop      = filters.get("property")

    columns = [
        {"label": _("Date"),          "fieldname": "date",          "fieldtype": "Date",                                "width": 110},
        {"label": _("Section"),       "fieldname": "section",       "fieldtype": "Data",                                "width": 160},
        {"label": _("Category"),      "fieldname": "category",      "fieldtype": "Data",                                "width": 160},
        {"label": _("Count"),         "fieldname": "count",         "fieldtype": "Int",                                 "width": 70},
        {"label": _("Amount"),        "fieldname": "amount",        "fieldtype": "Currency",                            "width": 130},
        {"label": _("GL Amount"),     "fieldname": "gl_amount",     "fieldtype": "Currency",                            "width": 130},
        {"label": _("Variance"),      "fieldname": "variance",      "fieldtype": "Currency",                            "width": 110},
        {"label": _("Reference"),     "fieldname": "reference",     "fieldtype": "Data",                                "width": 180},
        {"label": _("Property"),      "fieldname": "property",      "fieldtype": "Link",     "options": "Property",    "width": 120},
    ]

    data = []

    # Build property condition
    prop_cond = "AND gf.property = %(prop)s" if prop else ""
    prop_val  = {"prop": prop} if prop else {}

    # ── 1. Room Charges (from Night Audit / folio charge lines) ─────────────
    room_charges = frappe.db.sql(f"""
        SELECT fcl.posting_date, COUNT(*) cnt, SUM(fcl.amount) total
        FROM `tabFolio Charge Line` fcl
        JOIN `tabGuest Folio` gf ON gf.name = fcl.parent
        WHERE fcl.charge_category = 'Room Rate'
          AND fcl.is_void = 0
          AND fcl.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {prop_cond}
        GROUP BY fcl.posting_date
        ORDER BY fcl.posting_date
    """, {"from_date": from_date, "to_date": to_date, **prop_val}, as_dict=True)

    total_room = 0
    for r in room_charges:
        # GL verification for room charges
        gl_room = flt(frappe.db.sql("""
            SELECT SUM(gle.credit) FROM `tabGL Entry` gle
            WHERE gle.voucher_type = 'Sales Invoice'
              AND gle.posting_date = %s
              AND gle.account IN (SELECT name FROM `tabAccount`
                  WHERE account_type='Income Account' OR root_type='Income')
              AND gle.is_cancelled = 0
              AND gle.voucher_no IN (
                  SELECT si.name FROM `tabSales Invoice` si
                  JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
                  WHERE si.docstatus=1
                    AND sii.item_code LIKE 'Hotel - Room Rate%%'
                    AND si.posting_date = %s)
        """, (r.posting_date, r.posting_date))[0][0] or 0)
        amt = flt(r.total)
        total_room += amt
        data.append({
            "date": r.posting_date, "section": "Room Revenue",
            "category": "Room Rate", "count": r.cnt,
            "amount": amt, "gl_amount": gl_room,
            "variance": amt - gl_room,
            "reference": "Night Audit charges", "property": prop or "",
        })

    # ── 2. Other Charges (F&B, Laundry, Minibar etc.) ───────────────────────
    other_charges = frappe.db.sql(f"""
        SELECT fcl.posting_date, fcl.charge_category,
               COUNT(*) cnt, SUM(fcl.amount) total
        FROM `tabFolio Charge Line` fcl
        JOIN `tabGuest Folio` gf ON gf.name = fcl.parent
        WHERE fcl.charge_category NOT IN ('Room Rate','Room Rate Adjustment','Room Rate Credit')
          AND fcl.is_void = 0
          AND fcl.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {prop_cond}
        GROUP BY fcl.posting_date, fcl.charge_category
        ORDER BY fcl.posting_date, fcl.charge_category
    """, {"from_date": from_date, "to_date": to_date, **prop_val}, as_dict=True)

    total_other = 0
    for r in other_charges:
        amt = flt(r.total)
        total_other += amt
        data.append({
            "date": r.posting_date, "section": "Other Revenue",
            "category": r.charge_category, "count": r.cnt,
            "amount": amt, "gl_amount": 0, "variance": 0,
            "reference": "", "property": prop or "",
        })

    # ── 3. Invoices Generated ────────────────────────────────────────────────
    invoices = frappe.db.sql(f"""
        SELECT si.posting_date, COUNT(*) cnt,
               SUM(CASE WHEN si.is_return=0 THEN si.grand_total ELSE 0 END) regular,
               SUM(CASE WHEN si.is_return=1 THEN ABS(si.grand_total) ELSE 0 END) credits,
               COUNT(CASE WHEN si.is_return=1 THEN 1 END) credit_count
        FROM `tabSales Invoice` si
        JOIN `tabGuest Folio` gf ON gf.name = si.hotel_folio
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {prop_cond}
        GROUP BY si.posting_date
        ORDER BY si.posting_date
    """, {"from_date": from_date, "to_date": to_date, **prop_val}, as_dict=True)

    total_invoiced = total_credited = 0
    for r in invoices:
        reg = flt(r.regular); cr = flt(r.credits)
        total_invoiced  += reg
        total_credited  += cr
        gl_inv = flt(frappe.db.sql("""
            SELECT SUM(credit) FROM `tabGL Entry`
            WHERE voucher_type='Sales Invoice'
              AND posting_date=%s AND is_cancelled=0
              AND account IN (SELECT name FROM `tabAccount`
                  WHERE account_type='Income Account' OR root_type='Income')
        """, r.posting_date)[0][0] or 0)
        data.append({
            "date": r.posting_date, "section": "Invoicing",
            "category": "Sales Invoices ({0}) + Credit Notes ({1})".format(
                r.cnt - (r.credit_count or 0), r.credit_count or 0),
            "count": r.cnt,
            "amount": reg - cr, "gl_amount": gl_inv,
            "variance": (reg - cr) - gl_inv,
            "reference": "", "property": prop or "",
        })

    # ── 4. Payments by Mode ──────────────────────────────────────────────────
    payments = frappe.db.sql(f"""
        SELECT pe.posting_date, pe.mode_of_payment,
               COUNT(*) cnt, SUM(pe.paid_amount) total
        FROM `tabPayment Entry` pe
        JOIN `tabGuest Folio` gf ON gf.name = pe.hotel_folio
        WHERE pe.docstatus = 1
          AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {prop_cond}
        GROUP BY pe.posting_date, pe.mode_of_payment
        ORDER BY pe.posting_date, pe.mode_of_payment
    """, {"from_date": from_date, "to_date": to_date, **prop_val}, as_dict=True)

    # Also deposits
    deposits = frappe.db.sql(f"""
        SELECT hd.deposit_date posting_date, hd.payment_mode mode_of_payment,
               COUNT(*) cnt, SUM(hd.deposit_amount) total
        FROM `tabHotel Deposit` hd
        WHERE hd.docstatus = 1
          AND hd.deposit_date BETWEEN %(from_date)s AND %(to_date)s
          {'AND hd.property=%(prop)s' if prop else ''}
        GROUP BY hd.deposit_date, hd.payment_mode
        ORDER BY hd.deposit_date
    """, {"from_date": from_date, "to_date": to_date, **prop_val}, as_dict=True)

    total_payments = total_deposits = 0
    for r in payments:
        amt = flt(r.total)
        total_payments += amt
        gl_pe = flt(frappe.db.sql("""
            SELECT SUM(debit) FROM `tabGL Entry`
            WHERE voucher_type='Payment Entry'
              AND posting_date=%s AND is_cancelled=0
              AND account IN (SELECT name FROM `tabAccount`
                  WHERE account_type IN ('Cash','Bank'))
        """, r.posting_date)[0][0] or 0)
        data.append({
            "date": r.posting_date, "section": "Settlements",
            "category": "Payment — {0}".format(r.mode_of_payment or "Unknown"),
            "count": r.cnt,
            "amount": amt, "gl_amount": gl_pe, "variance": amt - gl_pe,
            "reference": "", "property": prop or "",
        })

    for r in deposits:
        amt = flt(r.total)
        total_deposits += amt
        data.append({
            "date": r.posting_date, "section": "Deposits",
            "category": "Deposit — {0}".format(r.mode_of_payment or ""),
            "count": r.cnt, "amount": amt, "gl_amount": 0, "variance": 0,
            "reference": "", "property": prop or "",
        })

    # ── AR Balance: sum of all outstanding SIs for this period ───────────────
    ar_open = flt(frappe.db.sql(f"""
        SELECT SUM(si.outstanding_amount)
        FROM `tabSales Invoice` si
        JOIN `tabGuest Folio` gf ON gf.name = si.hotel_folio
        WHERE si.docstatus=1 AND si.is_return=0
          AND si.status IN ('Unpaid','Partly Paid','Overdue')
          {prop_cond}
    """, prop_val)[0][0] or 0)

    data.append({})  # spacer
    data.append({
        "date": None, "section": "━━ SUMMARY", "category": "Room Revenue",
        "count": None, "amount": total_room, "gl_amount": 0, "variance": 0,
        "reference": "", "property": prop or "",
    })
    data.append({
        "date": None, "section": "━━ SUMMARY", "category": "Other Charges",
        "count": None, "amount": total_other, "gl_amount": 0, "variance": 0,
        "reference": "", "property": prop or "",
    })
    data.append({
        "date": None, "section": "━━ SUMMARY", "category": "Total Invoiced",
        "count": None, "amount": total_invoiced, "gl_amount": 0, "variance": 0,
        "reference": "", "property": prop or "",
    })
    data.append({
        "date": None, "section": "━━ SUMMARY", "category": "Total Payments",
        "count": None, "amount": total_payments, "gl_amount": 0, "variance": 0,
        "reference": "", "property": prop or "",
    })
    data.append({
        "date": None, "section": "━━ SUMMARY", "category": "Deposits Collected",
        "count": None, "amount": total_deposits, "gl_amount": 0, "variance": 0,
        "reference": "", "property": prop or "",
    })
    data.append({
        "date": None, "section": "━━ AR Balance", "category": "Open Invoices",
        "count": None, "amount": ar_open, "gl_amount": 0, "variance": 0,
        "reference": "Outstanding as of today", "property": prop or "",
    })

    report_summary = [
        {"value": total_room + total_other, "label": _("Total Charges"),  "datatype": "Currency", "indicator": "blue"},
        {"value": total_invoiced,           "label": _("Invoiced"),       "datatype": "Currency", "indicator": "orange"},
        {"value": total_payments,           "label": _("Received"),       "datatype": "Currency", "indicator": "green"},
        {"value": total_deposits,           "label": _("Deposits"),       "datatype": "Currency", "indicator": "blue"},
        {"value": ar_open,                  "label": _("Open AR"),        "datatype": "Currency",
         "indicator": "red" if ar_open > 0 else "green"},
    ]
    return columns, data, None, None, report_summary
