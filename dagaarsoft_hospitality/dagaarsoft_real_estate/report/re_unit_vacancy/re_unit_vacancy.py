import frappe
from frappe import _
from frappe.utils import flt, today, getdate


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Unit"),          "fieldname": "name",          "fieldtype": "Link",    "options": "RE Unit",     "width": 140},
        {"label": _("Unit No."),      "fieldname": "unit_number",   "fieldtype": "Data",                              "width": 90},
        {"label": _("Property"),      "fieldname": "property",      "fieldtype": "Link",    "options": "RE Property", "width": 140},
        {"label": _("Type"),          "fieldname": "unit_type",     "fieldtype": "Link",    "options": "RE Unit Type","width": 130},
        {"label": _("Furnishing"),    "fieldname": "furnishing",    "fieldtype": "Data",                              "width": 110},
        {"label": _("Status"),        "fieldname": "status",        "fieldtype": "Data",                              "width": 110},
        {"label": _("Monthly Rent"),  "fieldname": "monthly_rent",  "fieldtype": "Currency",                          "width": 120},
        {"label": _("Current Tenant"),"fieldname": "current_tenant","fieldtype": "Link",    "options": "RE Tenant",  "width": 150},
        {"label": _("Current Lease"), "fieldname": "current_lease", "fieldtype": "Link",    "options": "RE Lease",   "width": 150},
        {"label": _("Lease Expires"), "fieldname": "lease_end",     "fieldtype": "Date",                              "width": 110},
        {"label": _("Days Vacant"),   "fieldname": "days_vacant",   "fieldtype": "Int",                               "width": 100},
        {"label": _("Util. Incl."),   "fieldname": "rent_includes_utility", "fieldtype": "Check",                     "width": 90},
    ]

    cond = ["ru.is_active = 1"]
    vals = {}
    if filters.get("property"):
        cond.append("ru.property = %(property)s")
        vals["property"] = filters["property"]
    if filters.get("status"):
        cond.append("ru.status = %(status)s")
        vals["status"] = filters["status"]
    if filters.get("furnishing"):
        cond.append("ru.furnishing = %(furnishing)s")
        vals["furnishing"] = filters["furnishing"]

    where = " AND ".join(cond)

    units = frappe.db.sql("""
        SELECT
            ru.name,
            ru.unit_number,
            ru.property,
            ru.unit_type,
            ru.furnishing,
            ru.status,
            ru.monthly_rent,
            ru.current_tenant,
            ru.current_lease,
            ru.rent_includes_utility
        FROM `tabRE Unit` ru
        WHERE {0}
        ORDER BY ru.property, ru.status, ru.name
    """.format(where), vals, as_dict=True)

    if not units:
        return columns, []

    # Bulk fetch lease end dates for occupied units
    lease_ids = [u.current_lease for u in units if u.current_lease]
    lease_end_map = {}
    if lease_ids:
        placeholders = ", ".join(["%s"] * len(lease_ids))
        end_rows = frappe.db.sql("""
            SELECT name, end_date FROM `tabRE Lease`
            WHERE name IN ({0})
        """.format(placeholders), lease_ids, as_dict=True)
        lease_end_map = {r.name: r.end_date for r in end_rows}

    # Bulk fetch last move-out dates for vacant units
    unit_names = [u.name for u in units]
    placeholders_u = ", ".join(["%s"] * len(unit_names))
    moveout_rows = frappe.db.sql("""
        SELECT unit, MAX(move_out_date) AS last_out
        FROM `tabRE Move Out`
        WHERE unit IN ({0}) AND docstatus = 1
        GROUP BY unit
    """.format(placeholders_u), unit_names, as_dict=True)
    last_moveout = {r.unit: r.last_out for r in moveout_rows}

    today_date = getdate(today())
    data = []
    available = occupied = maintenance = 0

    for u in units:
        days_vacant = 0
        lease_end = lease_end_map.get(u.current_lease) if u.current_lease else None

        if u.status in ("Available", "Vacant - Cleaning"):
            available += 1
            last_out = last_moveout.get(u.name)
            if last_out:
                days_vacant = (today_date - getdate(last_out)).days
        elif u.status == "Occupied":
            occupied += 1
        else:
            maintenance += 1

        data.append({
            "name":                  u.name,
            "unit_number":           u.unit_number or "",
            "property":              u.property or "",
            "unit_type":             u.unit_type or "",
            "furnishing":            u.furnishing or "",
            "status":                u.status or "",
            "monthly_rent":          flt(u.monthly_rent),
            "current_tenant":        u.current_tenant or "",
            "current_lease":         u.current_lease or "",
            "lease_end":             lease_end,
            "days_vacant":           days_vacant,
            "rent_includes_utility": u.rent_includes_utility or 0,
        })

    total = len(data)
    occ_rate = round(occupied / total * 100, 1) if total else 0

    report_summary = [
        {"value": total,      "label": _("Total Units"),    "datatype": "Int",  "indicator": "blue"},
        {"value": occupied,   "label": _("Occupied"),       "datatype": "Int",  "indicator": "green"},
        {"value": available,  "label": _("Vacant"),         "datatype": "Int",  "indicator": "orange"},
        {"value": maintenance,"label": _("Maintenance"),    "datatype": "Int",  "indicator": "red"},
        {"value": "{0}%".format(occ_rate), "label": _("Occupancy Rate"), "datatype": "Data",
         "indicator": "green" if occ_rate >= 70 else "orange"},
    ]
    return columns, data, None, None, report_summary
