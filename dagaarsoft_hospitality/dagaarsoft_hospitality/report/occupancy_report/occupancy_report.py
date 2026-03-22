import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = [
        {"label": _("Room"), "fieldname": "room", "fieldtype": "Link", "options": "Room", "width": 100},
        {"label": _("Room Type"), "fieldname": "room_type", "fieldtype": "Data", "width": 120},
        {"label": _("Guest"), "fieldname": "guest_name", "fieldtype": "Data", "width": 150},
        {"label": _("Check-In"), "fieldname": "arrival_date", "fieldtype": "Date", "width": 100},
        {"label": _("Check-Out"), "fieldname": "departure_date", "fieldtype": "Date", "width": 100},
        {"label": _("Nights"), "fieldname": "num_nights", "fieldtype": "Int", "width": 70},
        {"label": _("Rate/Night"), "fieldname": "nightly_rate", "fieldtype": "Currency", "width": 110},
        {"label": _("Total Revenue"), "fieldname": "total_revenue", "fieldtype": "Currency", "width": 130},
        {"label": _("Status"), "fieldname": "stay_status", "fieldtype": "Data", "width": 100},
        {"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 100},
    ]

    conditions = []
    values = {}
    if filters.get("property"):
        conditions.append("gs.property = %(property)s")
        values["property"] = filters["property"]
    if filters.get("from_date"):
        conditions.append("gs.arrival_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("gs.departure_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("stay_status"):
        conditions.append("gs.stay_status = %(stay_status)s")
        values["stay_status"] = filters["stay_status"]

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    data = frappe.db.sql("""
        SELECT gs.room, gs.room_type, gs.guest_name, gs.arrival_date, gs.departure_date,
               gs.num_nights, gs.nightly_rate,
               (gs.nightly_rate * gs.num_nights) as total_revenue,
               gs.stay_status, gs.source
        FROM `tabGuest Stay` gs
        {where}
        ORDER BY gs.arrival_date DESC
    """.format(where=where), values, as_dict=True)

    return columns, data
