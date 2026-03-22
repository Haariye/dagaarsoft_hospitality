# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt, today, date_diff
from frappe.model.document import Document


class BanquetBooking(Document):

    def validate(self):
        if self.event_date and self.event_end_date:
            if self.event_date > self.event_end_date:
                frappe.throw(_("Event end date must be after start date."))
        self._calculate_totals()

    def _calculate_totals(self):
        services_total = sum(flt(r.amount) for r in (self.get("banquet_services") or []))
        self.total_amount = flt(services_total)

    def on_submit(self):
        self.db_set("booking_status", "Confirmed")
        if self.property:
            frappe.db.set_value("Banquet Hall", self.hall,
                "hall_status", "Reserved") if self.hall else None
        if self.customer:
            self._create_sales_invoice()

    def on_cancel(self):
        self.db_set("booking_status", "Cancelled")
        if self.hall:
            frappe.db.set_value("Banquet Hall", self.hall, "hall_status", "Available")

    def _create_sales_invoice(self):
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import (
            _get_default_income_account, _get_or_create_item
        )
        prop = frappe.get_doc("Property", self.property) if self.property else None
        company = prop.company if prop else frappe.defaults.get_defaults().get("company")
        income_account = (getattr(prop, "income_account", None) if prop else None) or \
            _get_default_income_account(company)

        si = frappe.new_doc("Sales Invoice")
        si.customer = self.customer
        si.company = company
        si.posting_date = today()
        si.due_date = today()
        si.remarks = "Banquet Booking: {0}".format(self.name)

        # Hall rental line
        item_code = _get_or_create_item("Banquet Hall")
        uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
        row = si.append("items", {})
        row.item_code = item_code
        row.item_name = "Banquet Hall: {0}".format(self.hall or "")
        row.qty = 1
        row.uom = uom
        row.rate = flt(self.hall_rate or 0)
        row.amount = flt(self.hall_rate or 0)
        row.income_account = income_account

        for svc in self.get("banquet_services") or []:
            svc_item = _get_or_create_item("Banquet")
            svc_uom = frappe.db.get_value("Item", svc_item, "stock_uom") or "Nos"
            srow = si.append("items", {})
            srow.item_code = svc_item
            srow.item_name = svc.service_name or "Banquet Service"
            srow.qty = flt(svc.qty or 1)
            srow.uom = svc_uom
            srow.rate = flt(svc.rate or 0)
            srow.amount = flt(svc.qty or 1) * flt(svc.rate or 0)
            srow.income_account = income_account

        if si.get("items"):
            si.set_missing_values()
            si.calculate_taxes_and_totals()
            si.insert(ignore_permissions=True)
            si.submit()
            self.db_set("sales_invoice", si.name)


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
