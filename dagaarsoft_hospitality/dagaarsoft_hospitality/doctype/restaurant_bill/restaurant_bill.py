# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.model.document import Document

class RestaurantBill(Document):
    def validate(self):
        if self.charge_to_room and self.guest_stay:
            st = frappe.db.get_value("Guest Stay",self.guest_stay,"stay_status")
            if st != "Checked In":
                frappe.throw(_("Guest Stay must be Checked In to charge to room."))
        self.total_amount = sum(flt(l.amount) for l in (self.get("bill_items") or []))

    def on_submit(self):
        if self.charge_to_room and self.guest_stay:
            folio = frappe.db.get_value("Guest Stay",self.guest_stay,"guest_folio")
            if folio:
                from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
                post_charge_to_folio(folio,
                    "Restaurant Bill: {0}".format(self.name),
                    self.total_amount or 0,"Restaurant","Restaurant Bill",self.name,self.outlet)
        else:
            # Generate Sales Invoice for non-room charges
            self._create_sales_invoice()

    def on_cancel(self): pass

    def _create_sales_invoice(self):
        if not self.customer: return
        prop = frappe.get_doc("Property",self.property) if self.property else None
        company = prop.company if prop else frappe.defaults.get_defaults().get("company")
        income_account = (prop.restaurant_income_account or prop.income_account) if prop else None
        si = frappe.new_doc("Sales Invoice")
        si.customer = self.customer
        si.company  = company
        si.posting_date = today()
        si.due_date = today()
        for line in self.get("bill_items") or []:
            row = si.append("items",{})
            row.item_code = line.item
            row.item_name = line.item_name
            row.qty       = line.qty or 1
            row.rate      = flt(line.rate)
            row.amount    = flt(line.amount)
            if income_account: row.income_account = income_account
        if si.get("items"):
            si.set_missing_values()
            si.calculate_taxes_and_totals()
            si.insert(ignore_permissions=True)
            si.submit()
            self.db_set("sales_invoice",si.name)


def validate(doc,method=None): doc.validate()
def on_submit(doc,method=None): doc.on_submit()
def on_cancel(doc,method=None): doc.on_cancel()


@frappe.whitelist()
def create_room_service_pos_draft(guest_stay_name, outlet_name=None):
    """
    Create a POS Invoice draft in POS Awesome for room service orders.
    The invoice is tagged with the room and stay so restaurant can see it.
    """
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    if stay.stay_status != "Checked In":
        frappe.throw(_("Guest Stay must be Checked In for room service."))

    prop = frappe.get_doc("Property", stay.property) if stay.property else None
    pos_profile = None
    if outlet_name:
        pos_profile = frappe.db.get_value("Outlet", outlet_name, "pos_profile")
    if not pos_profile and prop:
        pos_profile = prop.default_pos_profile

    pi = frappe.new_doc("POS Invoice")
    pi.customer      = stay.customer
    pi.posting_date  = frappe.utils.today()
    pi.pos_profile   = pos_profile
    pi.charge_to_room = 1
    pi.room_number   = stay.room
    pi.guest_stay_ref = guest_stay_name
    pi.remarks = "Room Service — Room {0} — {1}".format(stay.room, stay.guest_name)
    pi.insert(ignore_permissions=True)
    frappe.msgprint(_("POS Invoice {0} created for Room Service.").format(pi.name), alert=True)
    return pi.name
