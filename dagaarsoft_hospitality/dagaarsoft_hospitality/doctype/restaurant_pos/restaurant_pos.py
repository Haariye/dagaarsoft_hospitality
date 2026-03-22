# -*- coding: utf-8 -*-
"""
Restaurant POS v4 — Uses items_json field instead of child table
to avoid Frappe orphan DocType conflicts with POSAwesome.
Items stored as JSON list in items_json field.
"""
import frappe
import json
from frappe import _
from frappe.utils import flt, today, nowtime, now_datetime
from frappe.model.document import Document


class RestaurantPOS(Document):

    def validate(self):
        if not self.order_date:
            self.order_date = today()
        if not self.order_time:
            self.order_time = nowtime()
        self._validate_room_service()
        self._calculate_totals()

    def _validate_room_service(self):
        if self.order_type == "Room Service" and self.room_number:
            stay = frappe.db.get_value("Guest Stay",
                {"room": self.room_number, "stay_status": "Checked In"},
                ["name", "customer", "guest_name", "guest_folio"], as_dict=True)
            if stay:
                self.guest_stay = stay.name
                self.customer = stay.customer
                self.guest_name_display = stay.guest_name
            else:
                frappe.throw(_("No checked-in guest in Room {0}.").format(self.room_number))

    def _calculate_totals(self):
        items = self._get_items()
        self.subtotal = sum(
            flt(i.get("qty", 0)) * flt(i.get("rate", 0))
            for i in items if not i.get("is_void")
        )
        if self.discount_type == "Percentage":
            self.discount_amount = flt(self.subtotal) * flt(self.discount_value) / 100
        elif self.discount_type == "Fixed Amount":
            self.discount_amount = flt(self.discount_value)
        else:
            self.discount_amount = 0
        after_disc = flt(self.subtotal) - flt(self.discount_amount)
        self.service_charge_amount = after_disc * flt(self.service_charge_pct) / 100
        self.total_amount = after_disc + flt(self.service_charge_amount) + flt(self.tax_amount)
        self.balance_due = flt(self.total_amount) - flt(self.paid_amount)
        if flt(self.amount_tendered) > 0:
            self.change_amount = max(flt(self.amount_tendered) - flt(self.total_amount), 0)
        # Build HTML display
        self.items_display = self._build_items_html(items)

    def _get_items(self):
        if not self.items_json:
            return []
        try:
            return json.loads(self.items_json) or []
        except Exception:
            return []

    def _build_items_html(self, items):
        if not items:
            return "<p style='color:#718096'>No items</p>"
        rows = ""
        for i in items:
            if i.get("is_void"):
                continue
            amt = flt(i.get("qty", 0)) * flt(i.get("rate", 0))
            rows += f"<tr><td style='padding:4px 8px'>{i.get('item_name','')}</td><td style='padding:4px 8px;text-align:center'>{i.get('qty','')}</td><td style='padding:4px 8px;text-align:right'>{amt:,.2f}</td></tr>"
        return f"<table style='width:100%;border-collapse:collapse;font-size:13px'><thead><tr style='background:#f0f4f8'><th style='padding:6px 8px;text-align:left'>Item</th><th style='padding:6px 8px'>Qty</th><th style='padding:6px 8px;text-align:right'>Amount</th></tr></thead><tbody>{rows}</tbody></table>"

    def on_submit(self):
        self._ensure_uom_on_items()
        if self.payment_mode == "Room Charge":
            self._post_to_folio()
        else:
            self._create_sales_invoice()
        if self.restaurant_table and self.order_type == "Dine In":
            frappe.db.set_value("Restaurant Table", self.restaurant_table,
                {"table_status": "Available", "current_pos_order": None})
        self.db_set("order_status", "Paid")
        self.db_set("paid_amount", self.total_amount)
        self.db_set("balance_due", 0)

    def _ensure_uom_on_items(self):
        items = self._get_items()
        for i in items:
            if not i.get("uom"):
                i["uom"] = frappe.db.get_value("Item", i.get("item_code"), "stock_uom") or "Nos"
        self.db_set("items_json", json.dumps(items))

    def on_cancel(self):
        if self.restaurant_table:
            frappe.db.set_value("Restaurant Table", self.restaurant_table,
                {"table_status": "Available", "current_pos_order": None})
        self.db_set("order_status", "Voided")
        if self.folio_charge_ref and self.guest_stay:
            folio = frappe.db.get_value("Guest Stay", self.guest_stay, "guest_folio")
            if folio:
                _void_folio_charge(folio, self.name)

    def _post_to_folio(self):
        if not self.guest_stay:
            frappe.throw(_("Guest Stay is required for Room Charge."))
        folio = frappe.db.get_value("Guest Stay", self.guest_stay, "guest_folio")
        if not folio:
            frappe.throw(_("No open folio found for this stay."))
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
        post_charge_to_folio(folio,
            "Restaurant POS: {0} — {1}".format(self.name, self.outlet),
            self.total_amount, "Restaurant", "Restaurant POS", self.name, self.outlet)
        self.db_set("folio_charge_ref", folio)
        frappe.msgprint(_("Charged {0} to Room {1}.").format(
            frappe.format_value(self.total_amount, {"fieldtype": "Currency"}),
            self.room_number), alert=True)

    def _create_sales_invoice(self):
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import (
            _get_default_income_account, _get_or_create_item)
        prop = frappe.db.get_value("Property", self.property,
            ["company", "income_account", "restaurant_income_account"], as_dict=True) if self.property else None
        company = (prop.company if prop else None) or frappe.defaults.get_defaults().get("company")
        income_account = (getattr(prop, "restaurant_income_account", None) or
                         getattr(prop, "income_account", None) if prop else None) or \
                         _get_default_income_account(company)
        customer = self.customer or _get_or_create_walkin_customer(company)

        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = company
        si.posting_date = self.order_date or today()
        si.due_date = self.order_date or today()
        si.remarks = "Restaurant POS: {0} | {1} | {2}".format(self.name, self.outlet, self.order_type)
        si.hotel_stay = self.guest_stay or None
        si.hotel_room = self.room_number or None

        for i in self._get_items():
            if i.get("is_void"):
                continue
            item_code = i.get("item_code")
            if not item_code:
                continue
            uom = i.get("uom") or frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
            row = si.append("items", {})
            row.item_code = item_code
            row.item_name = i.get("item_name") or item_code
            row.description = i.get("item_name") or item_code
            row.qty = flt(i.get("qty", 1))
            row.uom = uom
            row.stock_uom = uom
            row.conversion_factor = 1
            row.rate = flt(i.get("rate", 0))
            row.amount = flt(i.get("qty", 1)) * flt(i.get("rate", 0))
            row.income_account = income_account

        if flt(self.discount_amount):
            si.discount_amount = flt(self.discount_amount)
            si.apply_discount_on = "Grand Total"

        if not si.get("items"):
            frappe.throw(_("No items to invoice."))

        si.set_missing_values()
        si.calculate_taxes_and_totals()
        si.insert(ignore_permissions=True)
        si.submit()
        self.db_set("sales_invoice", si.name)

        if self.payment_mode and self.payment_mode not in ("City Ledger", "Room Charge"):
            from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import apply_payment_to_invoice
            pe = apply_payment_to_invoice(si.name, flt(self.total_amount), self.payment_mode, None, company)
            self.db_set("payment_entry", pe)

        frappe.msgprint(_("Sales Invoice {0} created.").format(si.name), alert=True)


def _void_folio_charge(folio_name, pos_ref):
    folio = frappe.get_doc("Guest Folio", folio_name)
    for line in folio.get("folio_charges") or []:
        if line.reference_name == pos_ref:
            line.is_void = 1
            line.void_reason = "POS Order Cancelled"
    folio.save(ignore_permissions=True)


def _get_or_create_walkin_customer(company):
    name = "Walk-in Customer"
    if frappe.db.exists("Customer", name):
        return name
    c = frappe.new_doc("Customer")
    c.customer_name = name
    c.customer_type = "Individual"
    c.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "All Customer Groups"
    c.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"
    c.insert(ignore_permissions=True)
    return c.name


# ─── Whitelisted APIs ────────────────────────────────────────────────────────

@frappe.whitelist()
def get_menu_items(outlet=None, item_group=None, search_text=None):
    filters = {"is_sales_item": 1, "disabled": 0}
    if item_group:
        filters["item_group"] = item_group
    if search_text:
        filters["item_name"] = ["like", "%{0}%".format(search_text)]
    return frappe.get_all("Item", filters=filters,
        fields=["name as item_code", "item_name", "item_group",
                "standard_rate", "stock_uom", "image"], limit=200)


@frappe.whitelist()
def get_item_groups():
    return frappe.get_all("Item Group",
        filters={"is_group": 0, "disabled": 0},
        fields=["name", "item_group_name"], order_by="name")


@frappe.whitelist()
def get_open_tables(outlet=None):
    filters = {"is_active": 1}
    if outlet:
        filters["outlet"] = outlet
    return frappe.get_all("Restaurant Table", filters=filters,
        fields=["name", "table_number", "seating_capacity",
                "table_status", "current_pos_order", "floor"])


@frappe.whitelist()
def assign_table(pos_name, table_name):
    frappe.db.set_value("Restaurant POS", pos_name, "restaurant_table", table_name)
    frappe.db.set_value("Restaurant Table", table_name,
        {"table_status": "Occupied", "current_pos_order": pos_name})
    return {"ok": True}


@frappe.whitelist()
def fetch_guest_by_room(room_number):
    stay = frappe.db.get_value("Guest Stay",
        {"room": room_number, "stay_status": "Checked In"},
        ["name", "customer", "guest_name", "guest_folio"], as_dict=True)
    if not stay:
        frappe.throw(_("No checked-in guest in Room {0}.").format(room_number))
    return stay


@frappe.whitelist()
def save_items(pos_name, items_json):
    """Save items JSON from POS screen back to the document."""
    frappe.db.set_value("Restaurant POS", pos_name, "items_json", items_json)
    # Recalculate totals
    doc = frappe.get_doc("Restaurant POS", pos_name)
    doc.save(ignore_permissions=True)
    return {"subtotal": doc.subtotal, "total_amount": doc.total_amount}


@frappe.whitelist()
def print_kot(pos_name):
    doc = frappe.get_doc("Restaurant POS", pos_name)
    items = doc._get_items()
    kot_items = [i for i in items if not i.get("is_void") and not i.get("kot_printed")]
    for i in kot_items:
        i["kot_printed"] = True
    doc.db_set("items_json", json.dumps(items))
    doc.db_set("order_status", "KOT Printed")
    doc.db_set("kot_reference", "KOT-{0}".format(pos_name))
    return {"table": doc.table_display or doc.room_number,
            "order_type": doc.order_type, "items": kot_items,
            "kitchen_notes": doc.kitchen_notes}


@frappe.whitelist()
def get_active_orders(outlet=None, order_type=None):
    filters = {"order_status": ["in", ["Open","KOT Printed","Ready","Served"]], "docstatus": ["!=", 2]}
    if outlet:
        filters["outlet"] = outlet
    if order_type:
        filters["order_type"] = order_type
    return frappe.get_all("Restaurant POS", filters=filters,
        fields=["name","order_type","table_display","room_number",
                "guest_name_display","order_status","total_amount","order_time"],
        order_by="order_time asc")


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
