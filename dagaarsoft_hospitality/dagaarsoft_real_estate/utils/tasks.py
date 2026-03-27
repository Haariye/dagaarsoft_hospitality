import frappe
from frappe import _
from frappe.utils import flt, today, add_days, getdate, date_diff


def check_lease_expiry():
    """Daily: Flag leases expiring soon and send reminders."""
    try:
        reminder_days = int(
            frappe.db.get_single_value("RE Settings", "expiry_reminder_days") or 60)
    except Exception:
        reminder_days = 60
    threshold = add_days(today(), reminder_days)

    # Mark expiring soon
    soon = frappe.db.sql("""
        SELECT name FROM `tabRE Lease`
        WHERE docstatus=1 AND lease_status='Active'
          AND end_date BETWEEN %s AND %s
    """, (today(), threshold), as_list=True)
    for row in soon:
        frappe.db.set_value("RE Lease", row[0],
            "lease_status", "Expiring Soon", update_modified=False)

    # Mark actually expired
    expired = frappe.db.sql("""
        SELECT name FROM `tabRE Lease`
        WHERE docstatus=1 AND lease_status IN ('Active','Expiring Soon')
          AND end_date < %s
    """, today(), as_list=True)
    for row in expired:
        frappe.db.set_value("RE Lease", row[0],
            "lease_status", "Expired", update_modified=False)
        unit = frappe.db.get_value("RE Lease", row[0], "unit")
        if unit:
            frappe.db.set_value("RE Unit", unit, {
                "status": "Vacant - Cleaning",
                "current_tenant": "",
                "current_lease": "",
            })

    frappe.db.commit()


def generate_monthly_invoices():
    """Daily: Auto-generate rent invoices for due schedule lines."""
    try:
        send_reminder = frappe.db.get_single_value("RE Settings", "send_rent_reminder")
        reminder_days = int(frappe.db.get_single_value("RE Settings", "reminder_days_before") or 3)
    except Exception:
        send_reminder = 0
        reminder_days = 3

    due_threshold = add_days(today(), reminder_days)

    # Find pending schedule lines due within threshold
    lines = frappe.db.sql("""
        SELECT rsl.name, rsl.parent, rsl.due_date, rsl.amount
        FROM `tabRE Rent Schedule Line` rsl
        JOIN `tabRE Lease` rl ON rl.name = rsl.parent
        WHERE rsl.status = 'Pending'
          AND rsl.due_date <= %s
          AND rl.docstatus = 1
          AND rl.auto_generate_invoices = 1
          AND rl.lease_status IN ('Active', 'Expiring Soon')
    """, due_threshold, as_dict=True)

    generated = 0
    for line in lines:
        try:
            from dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease import (
                generate_rent_invoice)
            generate_rent_invoice(line.parent, line.name, submit_invoice=1)
            generated += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                f"RE Auto Invoice Error: {line.parent} / {line.name}")

    if generated:
        frappe.logger("dagaarsoft_real_estate").info(
            f"RE auto-generated {generated} rent invoice(s)")


def apply_late_fees():
    """Daily: Apply late fee penalties to overdue schedule lines."""
    try:
        fee_pct = flt(frappe.db.get_single_value("RE Settings", "late_fee_percentage") or 5)
        grace   = int(frappe.db.get_single_value("RE Settings", "late_fee_grace_days") or 5)
    except Exception:
        fee_pct = 5; grace = 5

    cutoff = add_days(today(), -grace)
    overdue = frappe.db.sql("""
        SELECT rsl.name, rsl.parent, rsl.amount, rsl.due_date
        FROM `tabRE Rent Schedule Line` rsl
        JOIN `tabRE Lease` rl ON rl.name = rsl.parent
        WHERE rsl.status = 'Invoiced'
          AND rsl.due_date < %s
          AND rl.docstatus = 1
          AND rl.lease_status IN ('Active','Expiring Soon')
    """, cutoff, as_dict=True)

    for row in overdue:
        # Check if penalty already exists
        if frappe.db.exists("RE Penalty", {
            "lease": row.parent,
            "penalty_type": "Late Payment",
            "description": ["like", f"%{row.name}%"],
            "docstatus": 1
        }):
            continue
        penalty_amount = flt(row.amount) * (fee_pct / 100)
        try:
            p = frappe.new_doc("RE Penalty")
            p.lease         = row.parent
            p.tenant        = frappe.db.get_value("RE Lease", row.parent, "tenant")
            p.penalty_type  = "Late Payment"
            p.penalty_date  = today()
            p.amount        = penalty_amount
            p.description   = f"Late payment penalty for schedule line {row.name} (due {row.due_date})"
            p.insert(ignore_permissions=True)
            p.submit()
            frappe.db.set_value("RE Rent Schedule Line", row.name, "status", "Overdue")
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                f"RE Late Fee Error: {row.parent}")
    frappe.db.commit()
