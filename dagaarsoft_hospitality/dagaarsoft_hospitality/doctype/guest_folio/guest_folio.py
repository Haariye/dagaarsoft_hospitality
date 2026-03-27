import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.model.document import Document


class GuestFolio(Document):
    def validate(self):
        self._compute_totals()
        self._sync_invoice_status()
        if self.guest_stay:
            st = frappe.db.get_value("Guest Stay", self.guest_stay, "stay_status")
            if st == "Cancelled":
                frappe.throw(_("Cannot modify Folio for a Cancelled Stay."))

    def _compute_totals(self):
        charges  = sum(flt(l.amount) for l in (self.get("folio_charges") or []) if not l.is_void)
        payments = sum(flt(l.amount) for l in (self.get("folio_payments") or []))
        self.total_charges  = charges
        self.total_payments = payments
        self.balance_due    = charges - payments  # negative = credit/overpaid

    def _sync_invoice_status(self):
        if not self.sales_invoice or not frappe.db.exists("Sales Invoice", self.sales_invoice):
            return
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import get_invoice_billing_status
        info = get_invoice_billing_status(self.sales_invoice)
        self.sales_invoice_status = info.get("label", "")
        self.invoice_outstanding  = info.get("outstanding", 0)
        self.invoice_paid_amount  = info.get("paid", 0)

    def on_submit(self): pass
    def on_cancel(self): self.db_set("folio_status", "Closed")


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()


@frappe.whitelist()
def generate_invoice(folio_name, submit_invoice=0, discount_pct=0, discount_amount=0, bill_to_override=None):
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import create_sales_invoice_from_folio
    si = create_sales_invoice_from_folio(folio_name, submit=bool(int(submit_invoice)),
        discount_pct=flt(discount_pct), discount_amount=flt(discount_amount),
        bill_to_override=bill_to_override or None)
    frappe.msgprint(_("Sales Invoice {0} created.").format(si), alert=True)
    return si


@frappe.whitelist()
def settle_with_payment(folio_name, amount, payment_mode, reference_number=None):
    folio = frappe.get_doc("Guest Folio", folio_name)
    if not folio.sales_invoice:
        frappe.throw(_("Generate a Sales Invoice first."))
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import apply_payment_to_invoice
    pe = apply_payment_to_invoice(folio.sales_invoice, flt(amount), payment_mode, reference_number)
    # FIX: reload folio fresh before saving to avoid timestamp conflict
    folio = frappe.get_doc("Guest Folio", folio_name)
    line = folio.append("folio_payments", {})
    line.payment_date = today(); line.payment_mode = payment_mode
    line.description = "Payment - {0}".format(payment_mode)
    line.amount = flt(amount); line.reference_number = reference_number
    line.payment_entry = pe; line.posted_by = frappe.session.user
    folio.save(ignore_permissions=True)
    frappe.db.set_value("Guest Folio", folio_name, "payment_entry", pe, update_modified=False)
    frappe.msgprint(_("Payment Entry {0} created.").format(pe), alert=True)
    return pe


@frappe.whitelist()
def collect_deposit(folio_name, amount, payment_mode="Cash", reference_number=None):
    """
    FIX: hotel_deposit.on_submit already saves the folio internally.
    We must NOT save the folio again here — that causes the stale-timestamp error.
    Instead we let hotel_deposit._sync_links() handle the folio payment line,
    and we only create the Hotel Deposit document here.
    """
    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.folio_status != "Open":
        frappe.throw(_("Folio must be Open to collect deposit."))

    dep = frappe.new_doc("Hotel Deposit")
    dep.guest_stay       = folio.guest_stay
    dep.customer         = folio.billing_customer or folio.customer
    dep.deposit_amount   = flt(amount)
    dep.payment_mode     = payment_mode
    dep.reference_number = reference_number
    dep.deposit_status   = "Received"
    dep.property         = folio.property
    dep.deposit_date     = today()
    dep.insert(ignore_permissions=True)
    dep.submit()
    # hotel_deposit.on_submit → _sync_links() already added the payment line to the folio.
    # DO NOT save folio again here — it would cause "Document has been modified" error.
    frappe.msgprint(_("Deposit {0} collected and posted to Folio.").format(dep.name), alert=True)
    return dep.name


@frappe.whitelist()
def calculate_and_post_room_charges(folio_name):
    folio = frappe.get_doc("Guest Folio", folio_name)
    if not folio.guest_stay:
        frappe.throw(_("No Guest Stay linked."))
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import post_all_room_charges
    result = post_all_room_charges(folio.guest_stay)
    frappe.msgprint(result["message"], alert=True)
    return result


@frappe.whitelist()
def get_folio_summary(folio_name):
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import get_folio_summary
    return get_folio_summary(folio_name)


@frappe.whitelist()
def void_charge(folio_name, row_name, void_reason):
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import void_charge_line
    return void_charge_line(folio_name, row_name, void_reason)


@frappe.whitelist()
def get_reservation_deposit_summary(folio_name):
    """
    FIX 2: Calculate advance deposit from Reservation's linked Payment Entries.
    Looks for Payment Entries where:
      - hotel_reservation = this folio's reservation
      - hotel_deposit is set (linked to a Hotel Deposit)
      - docstatus = 1 (submitted)
    Returns total deposited and list of entries for display.
    """
    folio = frappe.get_doc("Guest Folio", folio_name)
    if not folio.guest_stay:
        return {"total": 0, "entries": [], "already_in_folio": 0}

    reservation = frappe.db.get_value("Guest Stay", folio.guest_stay, "reservation")
    if not reservation:
        return {"total": 0, "entries": [], "already_in_folio": 0}

    # Find all submitted PEs linked to this reservation via hotel_deposit
    pes = frappe.db.sql("""
        SELECT pe.name, pe.paid_amount, pe.posting_date, pe.mode_of_payment,
               pe.hotel_deposit, pe.reference_no
        FROM `tabPayment Entry` pe
        WHERE pe.hotel_reservation = %s
          AND pe.hotel_deposit IS NOT NULL
          AND pe.hotel_deposit != ''
          AND pe.docstatus = 1
    """, reservation, as_dict=True)

    # Check which are already in folio payments
    folio_pe_names = {
        l.payment_entry for l in (folio.get("folio_payments") or [])
        if l.payment_entry
    }

    total = 0
    entries = []
    for pe in pes:
        already = pe.name in folio_pe_names
        total += flt(pe.paid_amount) if not already else 0
        entries.append({
            "payment_entry": pe.name,
            "amount": flt(pe.paid_amount),
            "date": str(pe.posting_date or ""),
            "mode": pe.mode_of_payment or "",
            "deposit": pe.hotel_deposit or "",
            "reference": pe.reference_no or "",
            "already_in_folio": already
        })

    # Already counted in folio
    already_total = sum(
        flt(l.amount) for l in (folio.get("folio_payments") or [])
        if l.payment_entry in {e["payment_entry"] for e in entries}
    )

    return {
        "reservation": reservation,
        "total_deposit_pes": sum(flt(e["amount"]) for e in entries),
        "already_in_folio": already_total,
        "pending_to_sync": total,
        "entries": entries
    }


@frappe.whitelist()
def sync_reservation_deposits_to_folio(folio_name):
    """
    FIX 2: Pull all reservation-linked deposit Payment Entries into folio payments.
    Only adds entries not already present. Safe to call multiple times.
    """
    folio = frappe.get_doc("Guest Folio", folio_name)
    if not folio.guest_stay:
        frappe.throw(_("No Guest Stay linked."))

    reservation = frappe.db.get_value("Guest Stay", folio.guest_stay, "reservation")
    if not reservation:
        frappe.throw(_("Guest Stay has no linked Reservation."))

    pes = frappe.db.sql("""
        SELECT pe.name, pe.paid_amount, pe.posting_date, pe.mode_of_payment,
               pe.hotel_deposit, pe.reference_no
        FROM `tabPayment Entry` pe
        WHERE pe.hotel_reservation = %s
          AND pe.hotel_deposit IS NOT NULL
          AND pe.hotel_deposit != ''
          AND pe.docstatus = 1
    """, reservation, as_dict=True)

    folio_pe_names = {
        l.payment_entry for l in (folio.get("folio_payments") or [])
        if l.payment_entry
    }

    added = 0
    # Reload folio fresh to avoid modified timestamp conflict
    folio = frappe.get_doc("Guest Folio", folio_name)
    for pe in pes:
        if pe.name in folio_pe_names:
            continue
        line = folio.append("folio_payments", {})
        line.payment_date     = pe.posting_date or today()
        line.payment_mode     = pe.mode_of_payment or "Cash"
        line.description      = "Reservation Deposit - {0}".format(pe.hotel_deposit or pe.name)
        line.amount           = flt(pe.paid_amount)
        line.reference_number = pe.reference_no
        line.payment_entry    = pe.name
        line.posted_by        = "Administrator"
        added += 1

    if added:
        folio.save(ignore_permissions=True)
        frappe.msgprint(
            _("{0} reservation deposit(s) synced to Folio.").format(added), alert=True)
    else:
        frappe.msgprint(_("All reservation deposits already in Folio."), alert=True)

    return {"synced": added, "reservation": reservation}

@frappe.whitelist()
def generate_supplementary_invoice(folio_name):
    """Manual trigger: generate SI for all current unbilled charges."""
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import create_supplementary_invoice
    si = create_supplementary_invoice(folio_name, submit=True)
    if not si:
        frappe.throw(_("No unbilled charges found on this Folio."))
    frappe.msgprint(_("Supplementary Invoice {0} created.").format(si), alert=True)
    return si
