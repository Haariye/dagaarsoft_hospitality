import frappe
from frappe import _
from frappe.utils import flt, today, date_diff, getdate


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Folio"),           "fieldname": "folio",           "fieldtype": "Link",     "options": "Guest Folio",    "width": 150},
        {"label": _("Guest"),           "fieldname": "guest_name",      "fieldtype": "Data",                                  "width": 160},
        {"label": _("Room"),            "fieldname": "room",            "fieldtype": "Link",     "options": "Room",           "width": 90},
        {"label": _("Check-In"),        "fieldname": "arrival_date",    "fieldtype": "Date",                                  "width": 100},
        {"label": _("Check-Out"),       "fieldname": "departure_date",  "fieldtype": "Date",                                  "width": 100},
        {"label": _("Nights"),          "fieldname": "num_nights",      "fieldtype": "Int",                                   "width": 60},
        {"label": _("Bill To"),         "fieldname": "bill_to",         "fieldtype": "Data",                                  "width": 140},
        {"label": _("Billing"),         "fieldname": "billing_instr",   "fieldtype": "Data",                                  "width": 120},
        {"label": _("Stay Status"),     "fieldname": "stay_status",     "fieldtype": "Data",                                  "width": 100},
        {"label": _("Folio Status"),    "fieldname": "folio_status",    "fieldtype": "Data",                                  "width": 90},
        {"label": _("Total Charges"),   "fieldname": "total_charges",   "fieldtype": "Currency",                              "width": 120},
        {"label": _("Debit (SI)"),      "fieldname": "total_debit",     "fieldtype": "Currency",                              "width": 120},
        {"label": _("Credit (Pay)"),    "fieldname": "total_credit",    "fieldtype": "Currency",                              "width": 120},
        {"label": _("Balance"),         "fieldname": "balance",         "fieldtype": "Currency",                              "width": 120},
        {"label": _("Primary SI"),      "fieldname": "sales_invoice",   "fieldtype": "Link",     "options": "Sales Invoice",  "width": 150},
        {"label": _("SI Status"),       "fieldname": "si_status",       "fieldtype": "Data",                                  "width": 100},
        {"label": _("Type"),            "fieldname": "row_type",        "fieldtype": "Data",                                  "width": 100},
    ]

    # ── Build WHERE conditions ──────────────────────────────────────────────
    cond = ["gf.docstatus = 1"]
    vals = {}

    if filters.get("property"):
        cond.append("gf.property = %(property)s")
        vals["property"] = filters["property"]
    if filters.get("customer"):
        cond.append("(gf.customer = %(customer)s OR gf.billing_customer = %(customer)s)")
        vals["customer"] = filters["customer"]
    if filters.get("room"):
        cond.append("gf.room = %(room)s")
        vals["room"] = filters["room"]
    if filters.get("folio_status"):
        cond.append("gf.folio_status = %(folio_status)s")
        vals["folio_status"] = filters["folio_status"]
    if filters.get("billing_instruction"):
        cond.append("gf.billing_instruction = %(billing_instruction)s")
        vals["billing_instruction"] = filters["billing_instruction"]
    if filters.get("from_date"):
        cond.append("gs.arrival_date >= %(from_date)s")
        vals["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        cond.append("gs.arrival_date <= %(to_date)s")
        vals["to_date"] = filters["to_date"]
    if filters.get("stay_status"):
        cond.append("gs.stay_status = %(stay_status)s")
        vals["stay_status"] = filters["stay_status"]

    where = "WHERE " + " AND ".join(cond)

    # ── Main folio query ────────────────────────────────────────────────────
    folios = frappe.db.sql(f"""
        SELECT
            gf.name                 AS folio,
            gf.guest_stay,
            gf.property,
            gf.room,
            gf.folio_status,
            gf.billing_instruction  AS billing_instr,
            gf.billing_customer,
            gf.customer,
            gf.sales_invoice,
            gs.guest_name,
            gs.arrival_date,
            gs.departure_date,
            gs.num_nights,
            gs.stay_status
        FROM `tabGuest Folio` gf
        LEFT JOIN `tabGuest Stay` gs ON gs.name = gf.guest_stay
        {where}
        ORDER BY gs.arrival_date DESC, gf.name
    """, vals, as_dict=True)

    if not folios:
        return columns, []

    data = []
    show_detail = filters.get("show_detail", 1)

    # Totals for report summary
    grand_charges = grand_debit = grand_credit = grand_balance = 0

    for f in folios:
        folio_name = f.folio

        # ── Charges from folio charge lines ────────────────────────────────
        charges = frappe.db.sql("""
            SELECT charge_category, description, posting_date,
                   qty, rate, amount, is_void, is_billed, void_reason,
                   reference_doctype, reference_name
            FROM `tabFolio Charge Line`
            WHERE parent = %s
            ORDER BY posting_date, creation
        """, folio_name, as_dict=True)

        total_charges = sum(flt(c.amount) for c in charges if not c.is_void)

        # ── Sales Invoices from ERPNext (real GL source) ────────────────────
        sis = frappe.db.sql("""
            SELECT si.name, si.grand_total, si.outstanding_amount,
                   si.status, si.posting_date, si.is_return, si.return_against
            FROM `tabSales Invoice` si
            WHERE si.hotel_folio = %s AND si.docstatus = 1
            ORDER BY si.posting_date, si.creation
        """, folio_name, as_dict=True)

        # ── Payment Entries from ERPNext ────────────────────────────────────
        reservation = frappe.db.get_value("Guest Stay", f.guest_stay, "reservation") \
            if f.guest_stay else None

        pe_cond = "pe.hotel_folio = %s AND pe.docstatus = 1"
        pe_vals = [folio_name]
        if reservation:
            pe_cond = """(pe.hotel_folio = %s
                OR (pe.hotel_reservation = %s
                    AND (pe.hotel_folio IS NULL OR pe.hotel_folio = '')))
                AND pe.docstatus = 1"""
            pe_vals = [folio_name, reservation]

        pes = frappe.db.sql(f"""
            SELECT pe.name, pe.paid_amount, pe.posting_date,
                   pe.mode_of_payment, pe.reference_no, pe.party
            FROM `tabPayment Entry` pe
            WHERE {pe_cond}
            ORDER BY pe.posting_date, pe.creation
        """, pe_vals, as_dict=True)

        # ── Ledger calculation (Debit/Credit/Balance) ───────────────────────
        ledger = []
        for si in sis:
            amt = flt(si.grand_total)
            ledger.append({
                "date": si.posting_date, "type": "SI",
                "ref": si.name, "is_return": si.is_return,
                "debit": 0 if si.is_return else abs(amt),
                "credit": abs(amt) if si.is_return else 0,
            })
        for pe in pes:
            ledger.append({
                "date": pe.posting_date, "type": "PE",
                "ref": pe.name, "is_return": False,
                "debit": 0, "credit": flt(pe.paid_amount),
            })
        ledger.sort(key=lambda x: (str(x["date"] or ""), x["ref"]))

        total_debit = sum(e["debit"] for e in ledger)
        total_credit = sum(e["credit"] for e in ledger)
        balance = total_debit - total_credit

        # ── GL verification: check income account debits ────────────────────
        si_names = [si.name for si in sis if not si.is_return]
        gl_income = 0
        if si_names:
            gl_income = flt(frappe.db.sql("""
                SELECT SUM(credit) FROM `tabGL Entry`
                WHERE voucher_type = 'Sales Invoice'
                  AND voucher_no IN ({})
                  AND account IN (
                      SELECT name FROM `tabAccount`
                      WHERE account_type = 'Income Account' OR root_type = 'Income'
                  )
                  AND is_cancelled = 0
            """.format(", ".join(["%s"] * len(si_names))), si_names)[0][0] or 0)

        # ── Primary SI status ───────────────────────────────────────────────
        si_status = ""
        if f.sales_invoice and frappe.db.exists("Sales Invoice", f.sales_invoice):
            si_status = frappe.db.get_value("Sales Invoice", f.sales_invoice, "status") or ""

        bill_to = frappe.db.get_value("Customer", f.billing_customer, "customer_name") \
            if f.billing_customer else ""

        # ── Summary row ─────────────────────────────────────────────────────
        summary_row = {
            "folio":          folio_name,
            "guest_name":     f.guest_name or "",
            "room":           f.room or "",
            "arrival_date":   f.arrival_date,
            "departure_date": f.departure_date,
            "num_nights":     f.num_nights or 0,
            "bill_to":        bill_to or (frappe.db.get_value("Customer", f.customer, "customer_name") or ""),
            "billing_instr":  f.billing_instr or "",
            "stay_status":    f.stay_status or "",
            "folio_status":   f.folio_status or "",
            "total_charges":  total_charges,
            "total_debit":    total_debit,
            "total_credit":   total_credit,
            "balance":        balance,
            "sales_invoice":  f.sales_invoice or "",
            "si_status":      si_status,
            "row_type":       "Folio",
            "indent":         0,
        }
        data.append(summary_row)

        grand_charges += total_charges
        grand_debit   += total_debit
        grand_credit  += total_credit
        grand_balance += balance

        if show_detail:
            # ── Charge lines ────────────────────────────────────────────────
            for c in charges:
                status = "Void" if c.is_void else ("Billed" if c.is_billed else "Pending")
                data.append({
                    "folio":          folio_name,
                    "guest_name":     "  ↳ [{0}] {1}".format(c.charge_category or "", c.description or ""),
                    "room":           "",
                    "arrival_date":   c.posting_date,
                    "departure_date": None,
                    "num_nights":     flt(c.qty),
                    "bill_to":        status,
                    "billing_instr":  c.reference_name or "",
                    "stay_status":    "",
                    "folio_status":   "",
                    "total_charges":  0 if c.is_void else flt(c.amount),
                    "total_debit":    0,
                    "total_credit":   0,
                    "balance":        0,
                    "sales_invoice":  "",
                    "si_status":      "",
                    "row_type":       "Charge",
                    "indent":         1,
                })

            # ── Ledger lines (SI + PE) ───────────────────────────────────────
            running = 0
            for e in ledger:
                running += e["debit"] - e["credit"]
                ref_type = "Credit Note" if (e["type"] == "SI" and e["is_return"]) \
                    else ("Sales Invoice" if e["type"] == "SI" else "Payment Entry")
                data.append({
                    "folio":          folio_name,
                    "guest_name":     "  ↳ {0}".format(ref_type),
                    "room":           "",
                    "arrival_date":   e["date"],
                    "departure_date": None,
                    "num_nights":     0,
                    "bill_to":        e["ref"],
                    "billing_instr":  "",
                    "stay_status":    "",
                    "folio_status":   "",
                    "total_charges":  0,
                    "total_debit":    e["debit"],
                    "total_credit":   e["credit"],
                    "balance":        running,
                    "sales_invoice":  e["ref"] if e["type"] == "SI" else "",
                    "si_status":      "",
                    "row_type":       ref_type,
                    "indent":         1,
                })

    # ── Grand total row ─────────────────────────────────────────────────────
    if data:
        data.append({
            "folio": "GRAND TOTAL", "guest_name": "", "room": "", "arrival_date": None,
            "departure_date": None, "num_nights": None, "bill_to": "", "billing_instr": "",
            "stay_status": "", "folio_status": "",
            "total_charges": grand_charges, "total_debit": grand_debit,
            "total_credit": grand_credit, "balance": grand_balance,
            "sales_invoice": "", "si_status": "", "row_type": "Total", "indent": 0,
        })

    report_summary = [
        {"value": grand_charges, "label": _("Total Charges"),  "datatype": "Currency", "indicator": "blue"},
        {"value": grand_debit,   "label": _("Total Invoiced"), "datatype": "Currency", "indicator": "orange"},
        {"value": grand_credit,  "label": _("Total Received"), "datatype": "Currency", "indicator": "green"},
        {"value": grand_balance, "label": _("Net Balance"),    "datatype": "Currency",
         "indicator": "red" if grand_balance > 0 else "green"},
    ]

    return columns, data, None, None, report_summary
