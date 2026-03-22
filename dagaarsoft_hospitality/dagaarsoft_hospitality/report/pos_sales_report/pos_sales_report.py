import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = [
        {"label": _("Order #"), "fieldname": "name", "fieldtype": "Link",
         "options": "Restaurant POS", "width": 120},
        {"label": _("Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 100},
        {"label": _("Outlet"), "fieldname": "outlet", "fieldtype": "Data", "width": 120},
        {"label": _("Order Type"), "fieldname": "order_type", "fieldtype": "Data", "width": 110},
        {"label": _("Table/Room"), "fieldname": "table_room", "fieldtype": "Data", "width": 100},
        {"label": _("Covers"), "fieldname": "covers", "fieldtype": "Int", "width": 70},
        {"label": _("Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Payment"), "fieldname": "payment_mode", "fieldtype": "Data", "width": 110},
        {"label": _("Status"), "fieldname": "order_status", "fieldtype": "Data", "width": 100},
        {"label": _("Waiter"), "fieldname": "waiter", "fieldtype": "Data", "width": 130},
    ]

    conditions = "rp.docstatus != 2"
    values = {}
    if filters.get("property"):
        conditions += " AND rp.property = %(property)s"
        values["property"] = filters["property"]
    if filters.get("outlet"):
        conditions += " AND rp.outlet = %(outlet)s"
        values["outlet"] = filters["outlet"]
    if filters.get("from_date"):
        conditions += " AND rp.order_date >= %(from_date)s"
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND rp.order_date <= %(to_date)s"
        values["to_date"] = filters["to_date"]
    if filters.get("order_type"):
        conditions += " AND rp.order_type = %(order_type)s"
        values["order_type"] = filters["order_type"]

    data = frappe.db.sql("""
        SELECT rp.name, rp.order_date, rp.outlet, rp.order_type,
               COALESCE(rp.table_display, rp.room_number, '') as table_room,
               rp.covers, rp.total_amount, rp.payment_mode,
               rp.order_status, rp.waiter
        FROM `tabRestaurant POS` rp
        WHERE {conditions}
        ORDER BY rp.order_date DESC, rp.order_time DESC
    """.format(conditions=conditions), values, as_dict=True)

    if data:
        total = sum(flt(r.total_amount) for r in data if r.order_status != "Voided")
        data.append({
            "name": "", "order_date": "", "outlet": "TOTAL", "order_type": "",
            "table_room": "", "covers": sum(r.covers or 0 for r in data),
            "total_amount": total, "payment_mode": "", "order_status": "",
            "waiter": ""
        })

    return columns, data
