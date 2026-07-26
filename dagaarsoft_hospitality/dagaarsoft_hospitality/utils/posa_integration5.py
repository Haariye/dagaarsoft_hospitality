import frappe
from frappe import _
from frappe.utils import flt, today

@frappe.whitelist()
def get_room_billing_info(room):
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.room_utils import get_billing_info_for_room
    return get_billing_info_for_room(room)


@frappe.whitelist()
def get_all_restaurant_tables():
    """Return all active restaurant tables for the POSA table selector."""
    tables = frappe.db.get_all("Restaurant Table",
        filters={"is_active": 1},
        fields=["name", "table_number", "outlet", "seating_capacity",
                "table_status", "floor", "current_pos_order"],
        order_by="table_number asc")
    result = []
    for t in tables:
        result.append({
            "name": t.name,
            "label": "Table {0}{1}{2}".format(
                t.table_number or t.name,
                " ({0})".format(t.outlet) if t.outlet else "",
                " - {0}".format(t.table_status) if t.table_status != "Available" else ""),
            "table_number": t.table_number or t.name,
            "outlet": t.outlet or "",
            "capacity": t.seating_capacity or 0,
            "status": t.table_status or "Available",
            "floor": t.floor or "",
        })
    return result


def on_sales_invoice_submit(doc, method=None):
    """
    When a POSA Sales Invoice with hotel_room is submitted:
    - Create ONE summary charge line on the Guest Folio
    - Link the Sales Invoice directly (reference_name = SI name)
    - Mark as is_billed=1 (already invoiced by POS)
    - Category = "Restaurant"

    This keeps the folio clean: one row per restaurant bill, not per item.
    The original SI has the item detail — drill down from the charge line reference.
    """
    if doc.docstatus != 1:
        return

    room       = getattr(doc, "hotel_room", None)
    folio_name = getattr(doc, "hotel_folio", None)

    # Skip if this SI was generated FROM the folio (not a POS sale)
    if folio_name and frappe.db.exists("Guest Folio", folio_name):
        billing_instr = frappe.db.get_value("Sales Invoice", doc.name,
            "hotel_billing_instruction")
        if billing_instr == "Folio Invoice":
            return
        folio_primary_si = frappe.db.get_value("Guest Folio", folio_name, "sales_invoice")
        if folio_primary_si == doc.name:
            return

    if not room:
        return

    # Resolve folio from room if not set
    if not folio_name:
        try:
            from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.room_utils import get_billing_info_for_room
            info = get_billing_info_for_room(room)
            doc.db_set("hotel_stay",  info.get("guest_stay"),  update_modified=False)
            doc.db_set("hotel_folio", info.get("guest_folio"), update_modified=False)
            folio_name = info.get("guest_folio")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "POSA Room Resolve Error")
            return

    if not folio_name or not frappe.db.exists("Guest Folio", folio_name):
        return

    # Dedup — never post same SI twice
    if frappe.db.exists("Folio Charge Line", {
            "parent": folio_name,
            "reference_doctype": "Sales Invoice",
            "reference_name": doc.name,
            "is_void": 0}):
        return

    # Determine category
    charge_cat = "Restaurant"
    table = getattr(doc, "restaurant_table", "") or ""

    try:
        folio = frappe.get_doc("Guest Folio", folio_name)
        if folio.folio_status != "Open" or folio.docstatus != 1:
            return

        # Build summary description
        item_count = len(doc.get("items") or [])
        desc = "Restaurant - {0}".format(doc.name)
        if table:
            desc += " | Table: {0}".format(table)
        if item_count > 0:
            # Show first 2 items as preview
            items = doc.get("items") or []
            preview = ", ".join([
                (i.item_name or i.item_code) for i in items[:2]
            ])
            if item_count > 2:
                preview += " +{0} more".format(item_count - 2)
            desc += " | {0}".format(preview)

        # ONE charge line for the whole SI
        line = folio.append("folio_charges", {})
        line.posting_date      = doc.posting_date or today()
        line.charge_category   = charge_cat
        line.description       = desc
        line.qty               = 1
        line.rate              = flt(doc.grand_total)
        line.amount            = flt(doc.grand_total)
        line.reference_doctype = "Sales Invoice"
        line.reference_name    = doc.name
        line.guest_stay        = getattr(doc, "hotel_stay", "") or folio.guest_stay
        line.posted_by         = frappe.session.user
        line.is_billed         = 1  # Already invoiced by POS

        folio.save(ignore_permissions=True)

        frappe.db.set_value("Guest Folio", folio_name,
            "sales_invoice_status", "Has POS Invoices", update_modified=False)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "POSA Folio Post Error: {0}".format(doc.name))


def on_sales_invoice_cancel(doc, method=None):
    try:
        cascade = frappe.db.get_single_value("Hospitality Settings",
            "cascade_cancel_linked_transactions")
    except Exception:
        cascade = 0
    if not cascade:
        return
    folio_name = getattr(doc, "hotel_folio", None)
    if not folio_name or not frappe.db.exists("Guest Folio", folio_name):
        return
    rows = frappe.get_all("Folio Charge Line",
        {"parent": folio_name, "reference_doctype": "Sales Invoice",
         "reference_name": doc.name, "is_void": 0}, ["name"])
    if not rows:
        return
    folio = frappe.get_doc("Guest Folio", folio_name)
    changed = False
    for row in folio.folio_charges:
        if row.name in {r.name for r in rows}:
            row.is_void = 1
            row.void_reason = "Auto-voided: SI {0} cancelled".format(doc.name)
            changed = True
    if changed:
        folio.save(ignore_permissions=True)
    folio_si = frappe.db.get_value("Guest Folio", folio_name, "sales_invoice")
    if folio_si == doc.name:
        frappe.db.set_value("Guest Folio", folio_name, {
            "sales_invoice_status": "Cancelled",
            "invoice_outstanding": 0, "invoice_paid_amount": 0
        }, update_modified=False)


def on_payment_entry_submit(doc, method=None):
    folio_name = getattr(doc, "hotel_folio", None)
    if not folio_name or not frappe.db.exists("Guest Folio", folio_name):
        return
    if frappe.db.exists("Folio Payment Line", {"parent": folio_name, "payment_entry": doc.name}):
        return
    folio = frappe.get_doc("Guest Folio", folio_name)
    line = folio.append("folio_payments", {})
    line.payment_date     = doc.posting_date or today()
    line.payment_mode     = doc.mode_of_payment
    line.description      = "Payment Entry - {0}".format(doc.name)
    line.amount           = flt(doc.paid_amount or doc.received_amount)
    line.reference_number = doc.reference_no
    line.payment_entry    = doc.name
    line.posted_by        = frappe.session.user
    folio.save(ignore_permissions=True)
    _sync_folio_invoice_status(folio_name)


def on_payment_entry_cancel(doc, method=None):
    try:
        cascade = frappe.db.get_single_value("Hospitality Settings",
            "cascade_cancel_linked_transactions")
    except Exception:
        cascade = 0
    if not cascade:
        return
    folio_name = getattr(doc, "hotel_folio", None)
    if not folio_name or not frappe.db.exists("Guest Folio", folio_name):
        return
    folio = frappe.get_doc("Guest Folio", folio_name)
    changed = False
    for row in list(folio.folio_payments):
        if row.payment_entry == doc.name:
            folio.remove(row); changed = True
    if changed:
        folio.save(ignore_permissions=True)
    _sync_folio_invoice_status(folio_name)


def _sync_folio_invoice_status(folio_name):
    si = frappe.db.get_value("Guest Folio", folio_name, "sales_invoice")
    if not si:
        return
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import get_invoice_billing_status
    info = get_invoice_billing_status(si)
    frappe.db.set_value("Guest Folio", folio_name, {
        "sales_invoice_status": info.get("label", ""),
        "invoice_outstanding":  info.get("outstanding", 0),
        "invoice_paid_amount":  info.get("paid", 0),
    }, update_modified=False)
