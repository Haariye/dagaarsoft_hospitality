# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document


class LoyaltyAccount(Document):

    def validate(self):
        if flt(self.points_balance) < 0:
            frappe.throw(_("Points balance cannot be negative."))

    def add_points(self, points, reason=None, reference=None):
        self.db_set("points_balance", flt(self.points_balance) + flt(points))
        self.db_set("lifetime_points", flt(self.lifetime_points) + flt(points))


@frappe.whitelist()
def award_stay_points(guest_stay_name):
    """Award loyalty points based on stay spend."""
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    if stay.stay_status != "Checked Out":
        frappe.throw(_("Points can only be awarded after checkout."))
    if not stay.customer:
        return
    # 1 point per currency unit spent
    folio = frappe.get_doc("Guest Folio", stay.guest_folio) if stay.guest_folio else None
    if not folio:
        return
    spend = sum(flt(l.amount) for l in (folio.get("folio_charges") or []) if not l.is_void)
    points = int(spend)
    la = frappe.db.get_value("Loyalty Account", {"customer": stay.customer}, "name")
    if la:
        doc = frappe.get_doc("Loyalty Account", la)
        doc.add_points(points, "Stay: {0}".format(guest_stay_name))
        frappe.msgprint(_("{0} loyalty points awarded.").format(points), alert=True)


def validate(doc, method=None): doc.validate()
