# -*- coding: utf-8 -*-
"""
install.py — after_install and after_migrate hooks.
Compatible with Frappe v14, v15, v16.

CRITICAL FIX: Custom fields linking to our own DocTypes (Room, Guest Stay,
Guest Folio, etc.) are only created AFTER those DocTypes are installed.
Without this guard, fresh install throws:
  WrongOptionsDoctypeLinkError: Options must be a valid DocType for field Hotel Room
"""
import frappe


# ── Fields linking to OUR OWN DocTypes (deferred until they exist) ────────────
_HOTEL_CUSTOM_FIELDS = {
    "Sales Invoice": [
        {"fieldname": "hotel_section", "label": "Hotel Charge",
         "fieldtype": "Section Break", "insert_after": "remarks",
         "collapsible": 1, "collapsible_depends_on": "eval:doc.hotel_room"},
        {"fieldname": "hotel_room", "label": "Hotel Room",
         "fieldtype": "Link", "options": "Room",
         "insert_after": "hotel_section", "in_list_view": 1, "in_standard_filter": 1},
        {"fieldname": "hotel_stay", "label": "Guest Stay",
         "fieldtype": "Link", "options": "Guest Stay",
         "insert_after": "hotel_room", "read_only": 1, "in_standard_filter": 1},
        {"fieldname": "hotel_col", "fieldtype": "Column Break",
         "insert_after": "hotel_stay"},
        {"fieldname": "hotel_folio", "label": "Guest Folio",
         "fieldtype": "Link", "options": "Guest Folio",
         "insert_after": "hotel_col", "read_only": 1},
        {"fieldname": "hotel_guest_name", "label": "Guest Name",
         "fieldtype": "Data", "insert_after": "hotel_folio", "read_only": 1},
        {"fieldname": "hotel_reservation", "label": "Hotel Reservation",
         "fieldtype": "Link", "options": "Reservation",
         "insert_after": "hotel_guest_name", "read_only": 1},
        {"fieldname": "hotel_rate_plan", "label": "Rate Plan",
         "fieldtype": "Link", "options": "Rate Plan",
         "insert_after": "hotel_reservation", "read_only": 1},
        {"fieldname": "hotel_billing_instruction", "label": "Billing Instruction",
         "fieldtype": "Data", "insert_after": "hotel_rate_plan", "read_only": 1},
        {"fieldname": "restaurant_table", "label": "Restaurant Table",
         "fieldtype": "Link", "options": "Restaurant Table",
         "insert_after": "hotel_billing_instruction"},
    ],
    "Payment Entry": [
        {"fieldname": "hotel_folio", "label": "Guest Folio",
         "fieldtype": "Link", "options": "Guest Folio", "insert_after": "party_name"},
        {"fieldname": "hotel_stay", "label": "Guest Stay",
         "fieldtype": "Link", "options": "Guest Stay", "insert_after": "hotel_folio"},
        {"fieldname": "hotel_room", "label": "Hotel Room",
         "fieldtype": "Link", "options": "Room", "insert_after": "hotel_stay"},
        {"fieldname": "hotel_reservation", "label": "Hotel Reservation",
         "fieldtype": "Link", "options": "Reservation", "insert_after": "hotel_room"},
        {"fieldname": "hotel_deposit", "label": "Hotel Deposit",
         "fieldtype": "Link", "options": "Hotel Deposit", "insert_after": "hotel_reservation"},
    ],
    "POS Opening Shift": [
        {"fieldname": "hotel_property", "label": "Property",
         "fieldtype": "Link", "options": "Property", "insert_after": "pos_profile"},
    ],
}

# ── Fields linking only to core ERPNext DocTypes (always safe) ────────────────
_CORE_CUSTOM_FIELDS = {
    "Customer": [
        {"fieldname": "loyalty_account", "label": "Loyalty Account",
         "fieldtype": "Link", "options": "Loyalty Account", "insert_after": "customer_details"},
        {"fieldname": "vip_status", "label": "VIP Status",
         "fieldtype": "Select", "options": "\nVIP\nVVIP\nHonorary", "insert_after": "loyalty_account"},
        {"fieldname": "id_type", "label": "ID Type",
         "fieldtype": "Select", "options": "\nPassport\nNational ID\nDriving License\nOther",
         "insert_after": "vip_status"},
        {"fieldname": "id_number", "label": "ID Number",
         "fieldtype": "Data", "insert_after": "id_type"},
        {"fieldname": "id_document", "label": "ID Document",
         "fieldtype": "Attach", "insert_after": "id_number"},
        {"fieldname": "nationality", "label": "Nationality",
         "fieldtype": "Data", "insert_after": "id_document"},
    ],
}

_HOTEL_REQUIRED_DOCTYPES = [
    "Room", "Guest Stay", "Guest Folio", "Reservation",
    "Rate Plan", "Hotel Deposit", "Restaurant Table", "Property",
]


def _hotel_doctypes_installed():
    """True only when every DocType we reference in custom fields exists."""
    return all(frappe.db.exists("DocType", dt) for dt in _HOTEL_REQUIRED_DOCTYPES)


def _ensure_custom_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    # Always safe — links only to core ERPNext
    try:
        create_custom_fields(_CORE_CUSTOM_FIELDS, update=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Hospitality: core custom fields error")

    # Only when our own DocTypes are fully installed
    if _hotel_doctypes_installed():
        try:
            create_custom_fields(_HOTEL_CUSTOM_FIELDS, update=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Hospitality: hotel custom fields error")
    else:
        # Will be retried automatically on next bench migrate
        frappe.logger("dagaarsoft_hospitality").warning(
            "Hotel DocTypes not yet synced — hotel custom fields deferred to bench migrate."
        )


def _ensure_roles():
    for role_name in ["Hotel Manager", "Hotel Receptionist", "Hotel Cashier",
                      "Hotel Housekeeper", "Hotel Auditor"]:
        if not frappe.db.exists("Role", role_name):
            try:
                frappe.get_doc({"doctype": "Role", "role_name": role_name,
                                "desk_access": 1}).insert(ignore_permissions=True)
            except Exception:
                pass


def _ensure_hospitality_settings():
    if not frappe.db.exists("DocType", "Hospitality Settings"):
        return
    defaults = {
        "manager_override_role":              "Hotel Manager",
        "rate_override_role":                 "Hotel Manager",
        "discount_role":                      "Hotel Manager",
        "waive_deposit_role":                 "Hotel Manager",
        "cascade_cancel_linked_transactions": 1,
        "allow_posa_room_charge":             1,
        "default_posa_charge_category":       "F&B",
        "room_service_enabled":               1,
        "deposit_collection_point":           "Folio",
        "auto_night_audit":                   1,
    }
    for k, v in defaults.items():
        try:
            if frappe.db.get_single_value("Hospitality Settings", k) is None:
                frappe.db.set_single_value("Hospitality Settings", k, v)
        except Exception:
            pass


def after_install():
    """
    Runs immediately after pip install of the app.
    Our own DocTypes are installed at this point, so hotel custom fields are safe.
    """
    _ensure_roles()
    _ensure_custom_fields()
    _ensure_hospitality_settings()
    frappe.db.commit()


def after_migrate():
    """
    Runs after every bench migrate — all DocTypes guaranteed to exist here.
    """
    _ensure_roles()
    _ensure_custom_fields()
    _ensure_hospitality_settings()
    frappe.db.commit()
