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
        self.balance_due    = charges - payments  # negative = credit

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
    line = folio.append("folio_payments", {})
    line.payment_date = today(); line.payment_mode = payment_mode
    line.description = "Payment - {0}".format(payment_mode)
    line.amount = flt(amount); line.reference_number = reference_number
    line.payment_entry = pe; line.posted_by = frappe.session.user
    folio.save(ignore_permissions=True)
    frappe.db.set_value("Guest Folio", folio_name, "payment_entry", pe)
    frappe.msgprint(_("Payment Entry {0} created.").format(pe), alert=True)
    return pe

@frappe.whitelist()
def collect_deposit(folio_name, amount, payment_mode="Cash", reference_number=None):
    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.folio_status != "Open":
        frappe.throw(_("Folio must be Open to collect deposit."))
    dep = frappe.new_doc("Hotel Deposit")
    dep.guest_stay = folio.guest_stay
    dep.customer   = folio.billing_customer or folio.customer
    dep.deposit_amount = flt(amount); dep.payment_mode = payment_mode
    dep.reference_number = reference_number; dep.deposit_status = "Received"
    dep.property = folio.property; dep.deposit_date = today()
    dep.insert(ignore_permissions=True); dep.submit()
    line = folio.append("folio_payments", {})
    line.payment_date = today(); line.payment_mode = payment_mode
    line.description = "Deposit - {0}".format(dep.name)
    line.amount = flt(amount); line.reference_number = reference_number or dep.name
    line.posted_by = frappe.session.user
    folio.save(ignore_permissions=True)
    frappe.msgprint(_("Deposit {0} collected.").format(dep.name), alert=True)
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
