import frappe

def boot_session(bootinfo):
    bootinfo["hospitality_version"] = "5.0.0"
    try:
        s = frappe.get_single("Hospitality Settings")
        bootinfo["hospitality_defaults"] = {
            "property":                     s.hotel_property or "",
            "rate_plan":                    s.default_rate_plan or "",
            "allow_posa_room_charge":       int(s.allow_posa_room_charge or 0),
            "default_posa_charge_category": s.default_posa_charge_category or "F&B",
            "enable_restaurant_table_field":int(getattr(s, "enable_restaurant_table_field", 0) or 0),
            "room_service_enabled":         int(s.room_service_enabled or 0),
            "manager_override_role":        s.manager_override_role or "Hotel Manager",
        }
    except Exception:
        bootinfo["hospitality_defaults"] = {}
