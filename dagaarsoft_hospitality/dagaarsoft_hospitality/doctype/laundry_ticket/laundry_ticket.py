# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.model.document import Document


class LaundryTicket(Document):

    def validate(self):
        self.total_amount = sum(
            flt(r.qty) * flt(r.rate) for r in (self.get("laundry_items") or [])
        )
        for row in self.get("laundry_items") or []:
            row.amount = flt(row.qty) * flt(row.rate)

    def on_submit(self):
        if self.guest_stay:
            stay = frappe.db.get_value("Guest Stay", self.guest_stay,
                ["stay_status", "guest_folio"], as_dict=True)
            if stay and stay.stay_status == "Checked In" and stay.guest_folio:
                from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
                post_charge_to_folio(
                    stay.guest_folio,
                    "Laundry: {0}".format(self.name),
                    self.total_amount,
                    "Laundry",
                    "Laundry Ticket",
                    self.name
                )
        else:
            self._create_sales_invoice()

    def _create_sales_invoice(self):
        if not self.customer:
            return
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import (
            _get_default_income_account, _get_or_create_item
        )
        prop = frappe.get_doc("Property", self.property) if self.property else None
        company = prop.company if prop else frappe.defaults.get_defaults().get("company")
        income_account = (getattr(prop, "income_account", None) if prop else None) or \
            _get_default_income_account(company)
        item_code = _get_or_create_item("Laundry")
        uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"

        si = frappe.new_doc("Sales Invoice")
        si.customer = self.customer
        si.company = company
        si.posting_date = today()
        for row in self.get("laundry_items") or []:
            r = si.append("items", {})
            r.item_code = item_code
            r.item_name = row.item_name or "Laundry"
            r.qty = flt(row.qty)
            r.uom = uom
            r.rate = flt(row.rate)
            r.amount = flt(row.qty) * flt(row.rate)
            r.income_account = income_account
        if si.get("items"):
            si.set_missing_values()
            si.calculate_taxes_and_totals()
            si.insert(ignore_permissions=True)
            si.submit()


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
