# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.model.document import Document


class RefundRequest(Document):

    def validate(self):
        if flt(self.refund_amount) <= 0:
            frappe.throw(_("Refund amount must be greater than zero."))

    def on_submit(self):
        self.db_set("request_status", "Approved")
        self.db_set("approved_by", frappe.session.user)
        self._process_refund()

    def _process_refund(self):
        """Process refund — create Payment Entry outgoing."""
        if not self.customer:
            frappe.throw(_("Customer is required for refund."))
        if not self.property:
            return
        prop = frappe.get_doc("Property", self.property)
        company = prop.company if prop else frappe.defaults.get_defaults().get("company")

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Pay"
        pe.party_type = "Customer"
        pe.party = self.customer
        pe.company = company
        pe.posting_date = today()
        pe.paid_amount = flt(self.refund_amount)
        pe.received_amount = flt(self.refund_amount)
        pe.mode_of_payment = self.refund_mode or "Cash"
        pe.remarks = "Refund: {0} | Reason: {1}".format(self.name, self.refund_reason or "")
        pe.set_missing_values()
        pe.insert(ignore_permissions=True)
        pe.submit()
        self.db_set("payment_entry", pe.name)
        frappe.msgprint(_("Refund Payment Entry {0} created.").format(pe.name), alert=True)

    def on_cancel(self):
        self.db_set("request_status", "Cancelled")
        if self.payment_entry:
            pe = frappe.get_doc("Payment Entry", self.payment_entry)
            if pe.docstatus == 1:
                pe.cancel()


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
