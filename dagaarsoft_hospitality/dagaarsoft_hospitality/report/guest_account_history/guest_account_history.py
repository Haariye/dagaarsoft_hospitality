import frappe
from frappe import _
from frappe.utils import flt, today


def execute(filters=None):
    filters = filters or {}
    if not filters.get("customer"):
        frappe.throw(_("Customer is required for this report."))

    columns = [
        {"label": _("Date"),          "fieldname": "date",          "fieldtype": "Date",                                  "width": 100},
        {"label": _("Stay/Folio"),    "fieldname": "stay",          "fieldtype": "Link",    "options": "Guest Stay",      "width": 140},
        {"label": _("Room"),          "fieldname": "room",          "fieldtype": "Link",    "options": "Room",            "width": 80},
        {"label": _("Nights"),        "fieldname": "nights",        "fieldtype": "Int",                                   "width": 60},
        {"label": _("Transaction"),   "fieldname": "transaction",   "fieldtype": "Data",                                  "width": 150},
        {"label": _("Reference"),     "fieldname": "reference",     "fieldtype": "Dynamic Link", "options": "ref_doctype","width": 160},
        {"label": _("Description"),   "fieldname": "description",   "fieldtype": "Data",                                  "width": 200},
        {"label": _("Debit"),         "fieldname": "debit",         "fieldtype": "Currency",                              "width": 120},
        {"label": _("Credit"),        "fieldname": "credit",        "fieldtype": "Currency",                              "width": 120},
        {"label": _("Balance"),       "fieldname": "balance",       "fieldtype": "Currency",                              "width": 120},
        {"label": _("Property"),      "fieldname": "property",      "fieldtype": "Link",    "options": "Property",        "width": 120},
        {"label": _("Ref Doctype"),   "fieldname": "ref_doctype",   "fieldtype": "Data",    "hidden": 1,                  "width": 120},
    ]

    cond = ["(gs.customer = %(customer)s OR gs.billing_customer = %(customer)s)"]
    vals = {"customer": filters["customer"]}
    if filters.get("property"):
        cond.append("gs.property = %(property)s"); vals["property"] = filters["property"]
    if filters.get("from_date"):
        cond.append("gs.arrival_date >= %(from_date)s"); vals["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        cond.append("gs.arrival_date <= %(to_date)s"); vals["to_date"] = filters["to_date"]
    where = "WHERE " + " AND ".join(cond)

    stays = frappe.db.sql(f"""
        SELECT gs.name stay, gs.property, gs.room, gs.arrival_date,
               gs.departure_date, gs.num_nights, gs.stay_status,
               gs.guest_folio, gs.customer, gs.guest_name
        FROM `tabGuest Stay` gs
        {where}
        ORDER BY gs.arrival_date DESC, gs.name
    """, vals, as_dict=True)

    data = []
    running_balance = 0
    total_debit = total_credit = 0
    stay_count = 0

    for stay in stays:
        stay_count += 1
        fn = stay.guest_folio

        # Stay header row
        data.append({
            "date":        stay.arrival_date,
            "stay":        stay.stay,
            "room":        stay.room or "",
            "nights":      stay.num_nights or 0,
            "transaction": "STAY — {0}".format(stay.stay_status or ""),
            "reference":   stay.stay,
            "description": "{0} to {1} | {2}".format(
                stay.arrival_date, stay.departure_date, stay.room or ""),
            "debit":       0, "credit": 0, "balance": running_balance,
            "property":    stay.property or "",
            "ref_doctype": "Guest Stay",
        })

        if not fn:
            continue

        # Charges from folio
        charges = frappe.db.sql("""
            SELECT posting_date, charge_category, description, amount, is_void
            FROM `tabFolio Charge Line`
            WHERE parent = %s AND is_void = 0
            ORDER BY posting_date, creation
        """, fn, as_dict=True)

        for c in charges:
            running_balance += flt(c.amount)
            total_debit     += flt(c.amount)
            data.append({
                "date":        c.posting_date,
                "stay":        stay.stay,
                "room":        stay.room or "",
                "nights":      0,
                "transaction": c.charge_category or "Charge",
                "reference":   fn,
                "description": c.description or "",
                "debit":       flt(c.amount),
                "credit":      0,
                "balance":     running_balance,
                "property":    stay.property or "",
                "ref_doctype": "Guest Folio",
            })

        # Sales Invoices
        sis = frappe.db.sql("""
            SELECT name, grand_total, posting_date, status, is_return, return_against
            FROM `tabSales Invoice`
            WHERE hotel_folio = %s AND docstatus = 1
            ORDER BY posting_date, creation
        """, fn, as_dict=True)

        for si in sis:
            gt = abs(flt(si.grand_total))
            is_credit = bool(si.is_return)
            # SIs don't affect the charge balance directly — show as financial row
            label = "Credit Note" if is_credit else "Sales Invoice"
            data.append({
                "date":        si.posting_date,
                "stay":        stay.stay,
                "room":        "",
                "nights":      0,
                "transaction": label,
                "reference":   si.name,
                "description": "{0} — Status: {1}{2}".format(
                    label, si.status or "",
                    " (against {0})".format(si.return_against) if is_credit else ""),
                "debit":       0,
                "credit":      0,
                "balance":     running_balance,
                "property":    stay.property or "",
                "ref_doctype": "Sales Invoice",
            })

        # Payment Entries
        reservation = frappe.db.get_value("Guest Stay", stay.stay, "reservation") or ""
        pe_cond = "(pe.hotel_folio=%s"
        pe_vals = [fn]
        if reservation:
            pe_cond += " OR (pe.hotel_reservation=%s AND (pe.hotel_folio IS NULL OR pe.hotel_folio=''))"
            pe_vals.append(reservation)
        pe_cond += ") AND pe.docstatus=1"
        pes = frappe.db.sql(f"""
            SELECT pe.name, pe.paid_amount, pe.posting_date, pe.mode_of_payment, pe.reference_no
            FROM `tabPayment Entry` pe
            WHERE {pe_cond}
            ORDER BY pe.posting_date, pe.creation
        """, pe_vals, as_dict=True)

        for pe in pes:
            amt = flt(pe.paid_amount)
            running_balance -= amt
            total_credit    += amt
            data.append({
                "date":        pe.posting_date,
                "stay":        stay.stay,
                "room":        "",
                "nights":      0,
                "transaction": "Payment — {0}".format(pe.mode_of_payment or ""),
                "reference":   pe.name,
                "description": pe.reference_no or pe.name,
                "debit":       0,
                "credit":      amt,
                "balance":     running_balance,
                "property":    stay.property or "",
                "ref_doctype": "Payment Entry",
            })

    if data:
        data.append({
            "date": None, "stay": "SUMMARY", "room": "", "nights": stay_count,
            "transaction": "{} stay(s)".format(stay_count),
            "reference": "", "description": "",
            "debit": total_debit, "credit": total_credit,
            "balance": running_balance,
            "property": "", "ref_doctype": "",
        })

    cname = frappe.db.get_value("Customer", filters["customer"], "customer_name") or filters["customer"]
    report_summary = [
        {"value": stay_count,       "label": _("Total Stays"),   "datatype": "Int",      "indicator": "blue"},
        {"value": total_debit,      "label": _("Total Charged"), "datatype": "Currency", "indicator": "orange"},
        {"value": total_credit,     "label": _("Total Paid"),    "datatype": "Currency", "indicator": "green"},
        {"value": running_balance,  "label": _("Net Balance"),   "datatype": "Currency",
         "indicator": "red" if running_balance > 0 else "green"},
    ]
    return columns, data, None, None, report_summary
