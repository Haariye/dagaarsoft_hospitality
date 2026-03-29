import frappe


def boot_session(bootinfo):
    bootinfo["hospitality_version"] = "5.1.0"
    try:
        s = frappe.get_single("Hospitality Settings")
        global_property = s.hotel_property or ""

        # ── User Permission based property (takes priority over global) ────
        # If user has a User Permission for "Property", use that automatically.
        # No error thrown — purely auto-fill behaviour.
        user_property = _get_user_permitted_property()
        active_property = user_property or global_property

        bootinfo["hospitality_defaults"] = {
            "property":                     active_property,
            "user_property":                user_property,        # only if via permission
            "global_property":              global_property,      # from settings
            "property_locked":              bool(user_property),  # JS uses this to lock the field
            "rate_plan":                    s.default_rate_plan or "",
            "allow_posa_room_charge":       int(s.allow_posa_room_charge or 0),
            "default_posa_charge_category": s.default_posa_charge_category or "F&B",
            "enable_restaurant_table_field":int(getattr(s, "enable_restaurant_table_field", 0) or 0),
            "room_service_enabled":         int(s.room_service_enabled or 0),
            "manager_override_role":        s.manager_override_role or "Hotel Manager",
        }
    except Exception:
        bootinfo["hospitality_defaults"] = {}


def _get_user_permitted_property():
    """
    Check if the current user has a User Permission restricting them to a specific Property.
    Returns the property name if exactly one is permitted, else empty string.
    This is non-mandatory — no error if none found.
    """
    try:
        perms = frappe.db.get_all(
            "User Permission",
            filters={
                "user":      frappe.session.user,
                "allow":     "Property",
                "is_default": 1,
            },
            fields=["for_value"],
            limit=1,
        )
        if perms:
            return perms[0].for_value

        # Also check without is_default (if only one exists, use it)
        all_perms = frappe.db.get_all(
            "User Permission",
            filters={"user": frappe.session.user, "allow": "Property"},
            fields=["for_value"],
        )
        if len(all_perms) == 1:
            return all_perms[0].for_value

        return ""
    except Exception:
        return ""


@frappe.whitelist()
def get_session_property():
    """Called from JS to get the active property for the current session."""
    defaults = frappe._dict(frappe.boot.get("hospitality_defaults") or {})
    if defaults:
        return {
            "property":       defaults.get("property", ""),
            "property_locked": defaults.get("property_locked", False),
        }
    # Fallback: re-compute
    user_property   = _get_user_permitted_property()
    global_property = frappe.db.get_single_value("Hospitality Settings", "hotel_property") or ""
    active          = user_property or global_property
    return {
        "property":        active,
        "property_locked": bool(user_property),
    }
