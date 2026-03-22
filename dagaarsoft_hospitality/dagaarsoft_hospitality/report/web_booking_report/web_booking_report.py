import frappe
from frappe import _


def execute(filters=None):
    columns = [
        {"label": _("Booking #"), "fieldname": "name", "fieldtype": "Link",
         "options": "Web Booking", "width": 130},
        {"label": _("Token"), "fieldname": "booking_token", "fieldtype": "Data", "width": 120},
        {"label": _("Guest"), "fieldname": "guest_name", "fieldtype": "Data", "width": 150},
        {"label": _("Email"), "fieldname": "guest_email", "fieldtype": "Data", "width": 160},
        {"label": _("Room Type"), "fieldname": "room_type", "fieldtype": "Data", "width": 120},
        {"label": _("Check-In"), "fieldname": "arrival_date", "fieldtype": "Date", "width": 100},
        {"label": _("Check-Out"), "fieldname": "departure_date", "fieldtype": "Date", "width": 100},
        {"label": _("Nights"), "fieldname": "num_nights", "fieldtype": "Int", "width": 70},
        {"label": _("Total"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Status"), "fieldname": "booking_status", "fieldtype": "Data", "width": 100},
        {"label": _("Reservation"), "fieldname": "reservation", "fieldtype": "Link",
         "options": "Reservation", "width": 120},
    ]

    conditions = "wb.docstatus != 2"
    values = {}
    if filters.get("property"):
        conditions += " AND wb.property = %(property)s"
        values["property"] = filters["property"]
    if filters.get("from_date"):
        conditions += " AND wb.arrival_date >= %(from_date)s"
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND wb.arrival_date <= %(to_date)s"
        values["to_date"] = filters["to_date"]
    if filters.get("booking_status"):
        conditions += " AND wb.booking_status = %(booking_status)s"
        values["booking_status"] = filters["booking_status"]

    data = frappe.db.sql("""
        SELECT wb.name, wb.booking_token,
               CONCAT(wb.guest_first_name, ' ', wb.guest_last_name) as guest_name,
               wb.guest_email, wb.room_type,
               wb.arrival_date, wb.departure_date, wb.num_nights,
               wb.total_amount, wb.booking_status, wb.reservation
        FROM `tabWeb Booking` wb
        WHERE {conditions}
        ORDER BY wb.submitted_on DESC
    """.format(conditions=conditions), values, as_dict=True)

    return columns, data
