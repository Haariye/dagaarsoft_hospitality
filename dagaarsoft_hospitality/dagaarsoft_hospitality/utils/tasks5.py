import frappe
from frappe.utils import today, add_days, now_datetime, flt


def auto_post_room_charges():
    """
    15:00 daily: Post today's room charge + create Sales Invoice for each checked-in stay.
    Delegates to billing.auto_daily_room_charge() which is fully idempotent.
    """
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import auto_daily_room_charge
    auto_daily_room_charge()


def auto_invoice_pending_services():
    """
    Hourly: Auto-invoice unbilled non-restaurant service charges (laundry, spa, etc.).
    Restaurant charges are excluded — those come from POS.
    """
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import auto_invoice_pending_services as _auto
    _auto()


def flag_no_shows():
    for s in frappe.get_all("Guest Stay",
        {"stay_status": "Expected", "arrival_date": ["<", today()]},
        ["name", "reservation"]):
        frappe.db.set_value("Guest Stay", s.name, "stay_status", "No Show")
        if s.reservation:
            frappe.db.set_value("Reservation", s.reservation, "reservation_status", "No Show")


def auto_night_audit():
    try:
        if not frappe.db.get_single_value("Hospitality Settings", "auto_night_audit"):
            return
    except Exception:
        return
    for prop in frappe.get_all("Property", {"is_active": 1}, ["name"]):
        if frappe.db.exists("Night Audit Run", {
            "property": prop.name, "audit_date": today(), "audit_status": "Completed"
        }): continue
        try:
            nar = frappe.new_doc("Night Audit Run")
            nar.property = prop.name; nar.audit_date = today()
            nar.insert(ignore_permissions=True); nar.submit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Auto Night Audit Error")


def flag_overdue_invoices():
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import get_invoice_billing_status
    for f in frappe.get_all("Guest Folio",
        {"folio_status": "Open", "sales_invoice": ["!=", ""]}, ["name", "sales_invoice"]):
        if not f.sales_invoice: continue
        try:
            info = get_invoice_billing_status(f.sales_invoice)
            frappe.db.set_value("Guest Folio", f.name, {
                "sales_invoice_status": info.get("label", ""),
                "invoice_outstanding":  info.get("outstanding", 0),
                "invoice_paid_amount":  info.get("paid", 0),
            })
        except Exception:
            pass


def sync_folio_invoice_statuses():
    flag_overdue_invoices()


def send_arrival_reminders():
    tomorrow = str(add_days(today(), 1))
    for s in frappe.get_all("Guest Stay",
        {"stay_status": "Expected", "arrival_date": tomorrow},
        ["name", "customer", "guest_name", "arrival_date"]):
        email = frappe.db.get_value("Customer", s.customer, "email_id")
        if email:
            try:
                frappe.sendmail(recipients=[email], subject="Your stay is tomorrow!",
                    message="<p>Dear {0},<br>We look forward to welcoming you tomorrow.</p>".format(
                        s.guest_name))
            except Exception:
                pass


def send_departure_reminders():
    for s in frappe.get_all("Guest Stay",
        {"stay_status": "Checked In", "departure_date": today()},
        ["name", "customer", "guest_name", "guest_folio"]):
        if not s.guest_folio: continue
        balance = flt(frappe.db.get_value("Guest Folio", s.guest_folio, "balance_due") or 0)
        email   = frappe.db.get_value("Customer", s.customer, "email_id")
        if email and balance > 0:
            try:
                frappe.sendmail(recipients=[email], subject="Checkout Reminder",
                    message="<p>Dear {0},<br>Your checkout is today. Outstanding: {1}.</p>".format(
                        s.guest_name, frappe.format_value(balance, {"fieldtype": "Currency"})))
            except Exception:
                pass


def update_maintenance_overdue():
    for t in frappe.get_all("Maintenance Ticket",
        {"ticket_status": ["in", ["Open", "In Progress"]], "due_date": ["<", today()],
         "docstatus": 1}, ["name"]):
        frappe.db.set_value("Maintenance Ticket", t.name, "ticket_status", "Escalated")


def update_housekeeping_overdue():
    for t in frappe.get_all("Housekeeping Task",
        {"task_status": ["in", ["Pending", "In Progress"]], "task_date": ["<", today()],
         "docstatus": 1}, ["name"]):
        frappe.db.set_value("Housekeeping Task", t.name, "priority", "Urgent")


def auto_checkout_departed_guests():
    """Auto checkout only if fully settled (no outstanding)."""
    for s in frappe.get_all("Guest Stay",
        {"stay_status": "Checked In", "departure_date": ["<", today()]},
        ["name", "guest_folio", "room", "guest_name", "property"]):
        try:
            if s.guest_folio:
                # Check real outstanding from ERPNext
                outstanding = flt(frappe.db.sql("""
                    SELECT COALESCE(SUM(outstanding_amount), 0)
                    FROM `tabSales Invoice`
                    WHERE hotel_folio = %s AND docstatus = 1 AND is_return = 0
                """, s.guest_folio)[0][0])
                if outstanding > 0.01:
                    continue  # Don't auto-checkout with unpaid bills
            frappe.db.set_value("Guest Stay", s.name, {
                "stay_status": "Checked Out", "actual_checkout": now_datetime()})
            if s.guest_folio:
                frappe.db.set_value("Guest Folio", s.guest_folio, "folio_status", "Closed")
            if s.room:
                frappe.db.set_value("Room", s.room, {
                    "room_status": "Vacant Dirty", "housekeeping_status": "Dirty",
                    "current_guest": "", "current_stay": ""})
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Auto Checkout Error")


def purge_old_audit_logs():
    cutoff = str(add_days(today(), -90))
    for a in frappe.get_all("Night Audit Run",
        {"audit_date": ["<", cutoff], "audit_status": "Completed"}, ["name"]):
        frappe.db.set_value("Night Audit Run", a.name, "charge_log", "")


def generate_weekly_revenue_summary():
    week_start = str(add_days(today(), -7))
    for prop in frappe.get_all("Property", {"is_active": 1}, ["name", "email"]):
        try:
            rev = frappe.db.sql("""
                SELECT IFNULL(SUM(fcl.amount), 0)
                FROM `tabFolio Charge Line` fcl
                JOIN `tabGuest Folio` gf ON gf.name=fcl.parent
                WHERE gf.property=%s AND fcl.posting_date>=%s AND fcl.is_void=0
            """, (prop.name, week_start))[0][0]
            if prop.email:
                frappe.sendmail(recipients=[prop.email],
                    subject="Weekly Revenue - {0}".format(prop.name),
                    message="<p>Revenue last 7 days: {0}</p>".format(
                        frappe.format_value(flt(rev), {"fieldtype": "Currency"})))
        except Exception:
            pass
