import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = [
        {"label": _("Deposit #"), "fieldname": "name", "fieldtype": "Link",
         "options": "Hotel Deposit", "width": 120},
        {"label": _("Date"), "fieldname": "deposit_date", "fieldtype": "Date", "width": 100},
        {"label": _("Guest"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
        {"label": _("Reservation"), "fieldname": "reservation", "fieldtype": "Link",
         "options": "Reservation", "width": 120},
        {"label": _("Amount"), "fieldname": "deposit_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Applied"), "fieldname": "applied_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Refunded"), "fieldname": "refund_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Balance"), "fieldname": "balance_deposit", "fieldtype": "Currency", "width": 120},
        {"label": _("Status"), "fieldname": "deposit_status", "fieldtype": "Data", "width": 100},
        {"label": _("Payment Mode"), "fieldname": "payment_mode", "fieldtype": "Data", "width": 110},
    ]

    conditions = "hd.docstatus = 1"
    values = {}
    if filters.get("property"):
        conditions += " AND hd.property = %(property)s"
        values["property"] = filters["property"]
    if filters.get("from_date"):
        conditions += " AND hd.deposit_date >= %(from_date)s"
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions += " AND hd.deposit_date <= %(to_date)s"
        values["to_date"] = filters["to_date"]
    if filters.get("deposit_status"):
        conditions += " AND hd.deposit_status = %(deposit_status)s"
        values["deposit_status"] = filters["deposit_status"]

    data = frappe.db.sql("""
        SELECT hd.name, hd.deposit_date,
               c.customer_name,
               hd.reservation, hd.deposit_amount, hd.applied_amount,
               hd.refund_amount, hd.balance_deposit,
               hd.deposit_status, hd.payment_mode
        FROM `tabHotel Deposit` hd
        LEFT JOIN `tabCustomer` c ON c.name = hd.customer
        WHERE {conditions}
        ORDER BY hd.deposit_date DESC
    """.format(conditions=conditions), values, as_dict=True)

    return columns, data
