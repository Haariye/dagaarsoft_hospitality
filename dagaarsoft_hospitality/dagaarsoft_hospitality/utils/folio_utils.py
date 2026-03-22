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
    folio = frappe.get_doc("Guest Folio", folio_name)
    stay  = frappe.get_doc("Guest Stay", folio.guest_stay) if folio.guest_stay else None
    by_cat = {}
    for line in folio.get("folio_charges") or []:
        if line.is_void:
            continue
        cat = line.charge_category or "Miscellaneous"
        if cat not in by_cat:
            by_cat[cat] = {"category": cat, "amount": 0, "count": 0}
        by_cat[cat]["amount"] += flt(line.amount)
        by_cat[cat]["count"]  += 1
    total_charges  = sum(flt(l.amount) for l in (folio.get("folio_charges") or [])
                         if not l.is_void)
    total_payments = sum(flt(l.amount) for l in (folio.get("folio_payments") or []))
    return {
        "folio_name":        folio_name,
        "guest":             stay.guest_name if stay else folio.customer,
        "room":              folio.room,
        "arrival":           str(stay.arrival_date)   if stay else None,
        "departure":         str(stay.departure_date) if stay else None,
        "nights":            stay.num_nights if stay else 0,
        "charges_breakdown": list(by_cat.values()),
        "total_charges":     total_charges,
        "total_payments":    total_payments,
        "balance_due":       total_charges - total_payments,
        "folio_status":      folio.folio_status,
        "sales_invoice":     folio.sales_invoice,
        "billing_customer":  folio.billing_customer,
        "customer":          folio.customer,
        "all_charges": [
            {"name": l.name, "date": str(l.posting_date or ""),
             "description": l.description, "category": l.charge_category,
             "qty": flt(l.qty), "rate": flt(l.rate), "amount": flt(l.amount),
             "is_void": l.is_void, "is_billed": l.is_billed,
             "void_reason": l.void_reason or ""}
            for l in (folio.get("folio_charges") or [])
        ],
    }
