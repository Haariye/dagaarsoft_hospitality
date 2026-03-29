"""
add_posa_hotel_fields.py — Run after deploying updated files:

    bench --site YOUR_SITE execute dagaarsoft_hospitality.add_posa_hotel_fields.run

Safe to run multiple times.
"""
import frappe


def run():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    pos_profile_fields = {
        "POS Profile": [
            {"fieldname": "posa_section_hotel_integration",
             "label": "Hotel & Restaurant Integration (DagaarSoft)",
             "fieldtype": "Section Break",
             "insert_after": "posa_section_cash_movement", "collapsible": 1},
            {"fieldname": "posa_enable_hotel_room",
             "label": "Enable Hotel Room Selector",
             "fieldtype": "Check", "default": "0",
             "insert_after": "posa_section_hotel_integration",
             "description": "Show Hotel Room dropdown in POS."},
            {"fieldname": "posa_hotel_col1",
             "fieldtype": "Column Break",
             "insert_after": "posa_enable_hotel_room"},
            {"fieldname": "posa_hotel_auto_customer",
             "label": "Auto-set Customer from Room",
             "fieldtype": "Check", "default": "1",
             "insert_after": "posa_hotel_col1",
             "depends_on": "eval:doc.posa_enable_hotel_room"},
            {"fieldname": "posa_restaurant_sb",
             "fieldtype": "Section Break",
             "insert_after": "posa_hotel_auto_customer"},
            {"fieldname": "posa_enable_restaurant_table",
             "label": "Enable Restaurant Table Selector",
             "fieldtype": "Check", "default": "0",
             "insert_after": "posa_restaurant_sb",
             "description": "Show Restaurant Table dropdown in POS."},
        ],
    }

    print("Creating POS Profile fields...")
    try:
        create_custom_fields(pos_profile_fields, update=True)
        print("  OK")
    except Exception as e:
        print(f"  ERROR: {e}")

    if frappe.db.exists("DocType", "Room"):
        si_fields = {
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
            ],
        }
        try:
            create_custom_fields(si_fields, update=True)
            print("  SI hotel fields OK")
        except Exception as e:
            print(f"  SI fields ERROR: {e}")

    frappe.db.commit()
    print("Done! Enable in POS Profile > Hotel & Restaurant Integration section.")
