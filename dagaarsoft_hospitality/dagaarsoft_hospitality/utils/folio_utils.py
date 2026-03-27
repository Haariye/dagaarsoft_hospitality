import frappe
from frappe import _
from frappe.utils import flt, today, nowtime

@frappe.whitelist()
def post_charge_to_folio(folio_name, description, amount, charge_category,
                          reference_doctype=None, reference_name=None,
                          outlet=None, qty=1, rate=None, posting_date=None,
                          guest_stay=None):
    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.folio_status != "Open":
        frappe.throw(_("Folio {0} is not Open.").format(folio_name))
    if folio.docstatus != 1:
        frappe.throw(_("Folio {0} must be submitted.").format(folio_name))
    line = folio.append("folio_charges", {})
    line.description       = description
    line.qty               = flt(qty) or 1
    line.rate              = flt(rate) if rate is not None else flt(amount)
    line.amount            = flt(amount)
    line.charge_category   = charge_category
    line.posting_date      = posting_date or today()
    line.posting_time      = nowtime()
    line.reference_doctype = reference_doctype
    line.reference_name    = reference_name
    line.outlet            = outlet
    line.posted_by         = frappe.session.user
    line.is_read_only      = 1
    line.guest_stay        = guest_stay or folio.guest_stay
    folio.save(ignore_permissions=True)
    return folio_name

@frappe.whitelist()
def void_charge_line(folio_name, row_name, void_reason):
    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.folio_status != "Open":
        frappe.throw(_("Folio must be Open to void charges."))
    for line in folio.get("folio_charges") or []:
        if line.name == row_name:
            if line.is_void:
                frappe.throw(_("Already voided."))
            if line.is_billed:
                frappe.throw(_("Cannot void an already-invoiced charge."))
            line.is_void    = 1
            line.void_reason = void_reason
            folio.save(ignore_permissions=True)
            frappe.msgprint(_("Charge voided."), alert=True)
            return {"ok": True}
    frappe.throw(_("Charge line not found."))

@frappe.whitelist()
def get_folio_summary(folio_name):
    """
    Two-section summary:

    SECTION 1 — CHARGES (what services the guest consumed):
      Pure folio charge lines by category. Nothing to do with invoices or payments.
      This is the operational record: room nights, laundry, F&B, minibar, etc.

    SECTION 2 — FINANCIAL TRANSACTIONS (what has been invoiced and paid):
      All submitted Sales Invoices linked to this folio (primary + supplementary).
      All submitted Payment Entries linked to this folio.
      Credit Notes linked to this folio.
      True outstanding = sum of SI outstanding_amounts.
      No mixing with charge lines.
    """
    folio = frappe.get_doc("Guest Folio", folio_name)
    stay  = frappe.get_doc("Guest Stay", folio.guest_stay) if folio.guest_stay else None

    # ── SECTION 1: Charges ────────────────────────────────────────────────────
    by_cat = {}
    for line in (folio.get("folio_charges") or []):
        if line.is_void:
            continue
        cat = line.charge_category or "Miscellaneous"
        if cat not in by_cat:
            by_cat[cat] = {"category": cat, "amount": 0, "count": 0}
        by_cat[cat]["amount"] += flt(line.amount)
        by_cat[cat]["count"]  += 1

    total_charges  = sum(r["amount"] for r in by_cat.values())
    unbilled_total = sum(flt(l.amount) for l in (folio.get("folio_charges") or [])
                         if not l.is_void and not l.is_billed)

    # ── SECTION 2: Ledger — Debit / Credit / Running Balance ────────────────
    # Rules:
    #   Sales Invoice (normal)  → DEBIT  (guest owes us)
    #   Sales Invoice (return/credit note) → CREDIT (we owe guest)
    #   Payment Entry           → CREDIT (guest paid us)
    # Balance = cumulative Debit - cumulative Credit (positive = guest owes, negative = we owe)

    reservation = frappe.db.get_value("Guest Stay", folio.guest_stay, "reservation")         if folio.guest_stay else None

    # Fetch all SIs for this folio
    all_sis = frappe.db.sql("""
        SELECT name, grand_total, posting_date, is_return, return_against,
               status, creation
        FROM `tabSales Invoice`
        WHERE hotel_folio = %s AND docstatus = 1
        ORDER BY posting_date, creation
    """, folio_name, as_dict=True)

    # Fetch all PEs for this folio (including reservation deposits)
    if reservation:
        all_pes = frappe.db.sql("""
            SELECT pe.name, pe.paid_amount, pe.posting_date,
                   pe.mode_of_payment, pe.reference_no, pe.creation
            FROM `tabPayment Entry` pe
            WHERE pe.docstatus = 1
              AND (pe.hotel_folio = %s
                   OR (pe.hotel_reservation = %s
                       AND (pe.hotel_folio IS NULL OR pe.hotel_folio = '')))
            ORDER BY pe.posting_date, pe.creation
        """, (folio_name, reservation), as_dict=True)
    else:
        all_pes = frappe.db.sql("""
            SELECT pe.name, pe.paid_amount, pe.posting_date,
                   pe.mode_of_payment, pe.reference_no, pe.creation
            FROM `tabPayment Entry` pe
            WHERE pe.hotel_folio = %s AND pe.docstatus = 1
            ORDER BY pe.posting_date, pe.creation
        """, folio_name, as_dict=True)

    # Build unified ledger entries sorted by date then creation
    ledger_entries = []

    for si in all_sis:
        gt = flt(si.grand_total)
        is_credit = bool(si.is_return)
        ledger_entries.append({
            "date":       str(si.posting_date or ""),
            "creation":   str(si.creation or ""),
            "type":       "Sales Invoice",
            "name":       si.name,
            "description": "Credit Note" if is_credit else "Sales Invoice",
            "ref":        si.return_against or "",
            "debit":      0 if is_credit else abs(gt),
            "credit":     abs(gt) if is_credit else 0,
            "is_return":  is_credit,
            "status":     si.status or "",
        })

    for pe in all_pes:
        amt = flt(pe.paid_amount)
        ledger_entries.append({
            "date":       str(pe.posting_date or ""),
            "creation":   str(pe.creation or ""),
            "type":       "Payment Entry",
            "name":       pe.name,
            "description": pe.mode_of_payment or "Payment",
            "ref":        pe.reference_no or "",
            "debit":      0,
            "credit":     amt,
            "is_return":  False,
            "status":     "Paid",
        })

    # Sort by date then creation time
    ledger_entries.sort(key=lambda x: (x["date"], x["creation"]))

    # Calculate running balance
    running_balance = 0
    total_debit  = 0
    total_credit = 0
    for entry in ledger_entries:
        running_balance += entry["debit"] - entry["credit"]
        total_debit     += entry["debit"]
        total_credit    += entry["credit"]
        entry["balance"] = running_balance

    true_balance = running_balance  # positive = guest owes, negative = hotel owes

    # Keep backward-compat invoice/payment lists for other code
    invoices = [e for e in ledger_entries if e["type"] == "Sales Invoice"]
    payments = [e for e in ledger_entries if e["type"] == "Payment Entry"]

    return {
        "folio_name":       folio_name,
        "guest":            stay.guest_name if stay else folio.customer,
        "room":             folio.room,
        "arrival":          str(stay.arrival_date)   if stay else None,
        "departure":        str(stay.departure_date) if stay else None,
        "nights":           stay.num_nights if stay else 0,
        "billing_customer": folio.billing_customer,
        "customer":         folio.customer,
        "folio_status":     folio.folio_status,
        # Section 1 — Charges
        "charges_breakdown": list(by_cat.values()),
        "total_charges":     total_charges,
        "unbilled_total":    unbilled_total,
        # Section 2 — Ledger
        "ledger":            ledger_entries,
        "total_debit":       total_debit,
        "total_credit":      total_credit,
        "true_balance":      true_balance,
        # Legacy compat
        "balance_due":       true_balance,
        "invoices":          invoices,
        "payments":          payments,
        "sales_invoice":     folio.sales_invoice,
    }