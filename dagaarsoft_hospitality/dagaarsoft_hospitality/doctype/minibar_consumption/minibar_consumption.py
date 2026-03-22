# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document


class MinibarConsumption(Document):

    def validate(self):
        self.total_amount = sum(
            flt(r.qty) * flt(r.rate) for r in (self.get("minibar_items") or [])
        )
        for row in self.get("minibar_items") or []:
            row.amount = flt(row.qty) * flt(row.rate)

    def on_submit(self):
        if not self.guest_stay:
            frappe.throw(_("Guest Stay is required for Minibar charge."))
        stay = frappe.db.get_value("Guest Stay", self.guest_stay,
            ["stay_status", "guest_folio"], as_dict=True)
        if not stay or stay.stay_status != "Checked In":
            frappe.throw(_("Guest Stay must be Checked In."))
        if not stay.guest_folio:
            frappe.throw(_("No folio found for stay."))
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
        post_charge_to_folio(
            stay.guest_folio,
            "Minibar: {0}".format(self.name),
            self.total_amount,
            "Minibar",
            "Minibar Consumption",
            self.name
        )


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
