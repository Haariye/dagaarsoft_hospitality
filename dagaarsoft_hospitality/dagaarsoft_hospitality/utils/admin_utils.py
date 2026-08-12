import frappe
from frappe import _
from frappe.utils import flt


# ─────────────────────────────────────────────────────────────────────────────
# PURGE ALL HOTEL TRANSACTIONS — System Administrator only
# ─────────────────────────────────────────────────────────────────────────────

# Doctypes to purge in safe order (children first, parents last).
# ERPNext accounting docs come first, then hotel docs.
# Property, Room, Room Type, Outlet, Rate Plan — NEVER deleted (config data).
_PURGE_ORDER = [
    # ERPNext accounting linked to hotel
    "Payment Entry",
    "Sales Invoice",
    "Journal Entry",
    # Hotel transactions
    "Laundry Ticket",
    "Minibar Consumption",
    "Service Request",
    "Transport Booking",
    "Restaurant Bill",
    "Banquet Booking",
    "Room Move",
    "Housekeeping Task",
    "Maintenance Ticket",
    "Hotel Deposit",
    "Refund Request",
    "Shift Handover",
    "Night Audit Run",
    "Guest Folio",
    "Guest Stay",
    "Reservation",
    "Web Booking",
]

# These are NEVER deleted — they are configuration, not transactions
_PROTECTED_DOCTYPES = [
    "Property", "Room", "Room Type", "Outlet", "Rate Plan",
    "Banquet Hall", "Banquet Package", "Restaurant Table",
    "Hospitality Settings", "Loyalty Account",
]


@frappe.whitelist()
def purge_all_hotel_transactions(password, confirm_text):
    """
    Delete ALL hotel transactions and linked ERPNext records.
    System Administrator only. Requires password + confirmation text.

    Args:
        password: The user's login password for verification
        confirm_text: Must be exactly "DELETE ALL HOTEL DATA" to proceed
    """
    # 1. Role check
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Administrator can purge hotel transactions."))

    # 2. Confirmation text check
    if confirm_text != "DELETE ALL HOTEL DATA":
        frappe.throw(_("Confirmation text must be exactly: DELETE ALL HOTEL DATA"))

    # 3. Password verification
    from frappe.utils.password import check_password
    try:
        check_password(frappe.session.user, password)
    except frappe.AuthenticationError:
        frappe.throw(_("Incorrect password."))

    # 4. Purge in order
    deleted = []
    errors = []

    for dt in _PURGE_ORDER:
        if not frappe.db.exists("DocType", dt):
            continue

        # For ERPNext docs (SI, PE, JE), only delete hotel-linked ones
        if dt in ("Sales Invoice", "Payment Entry"):
            records = frappe.get_all(dt,
                filters={"hotel_folio": ["is", "set"]},
                fields=["name", "docstatus"],
                order_by="docstatus desc")
        elif dt == "Journal Entry":
            records = frappe.db.sql("""
                SELECT DISTINCT je.name, je.docstatus
                FROM `tabJournal Entry` je
                WHERE je.user_remark LIKE '%%Folio:%%'
                   OR je.user_remark LIKE '%%Deposit Return%%'
                   OR je.user_remark LIKE '%%Charge to Credit%%'
                ORDER BY je.docstatus DESC
            """, as_dict=True)
        else:
            records = frappe.get_all(dt,
                fields=["name", "docstatus"],
                order_by="docstatus desc")

        count = 0
        for r in records:
            try:
                doc = frappe.get_doc(dt, r.name)
                if doc.docstatus == 1:
                    doc.flags.ignore_links = True
                    doc.flags.ignore_validate_update_after_submit = True
                    doc.flags.from_cascade_cancel = True
                    doc.cancel()
                frappe.delete_doc(dt, r.name,
                    force=True, ignore_permissions=True, delete_permanently=True)
                count += 1
            except Exception as e:
                errors.append("{0} {1}: {2}".format(dt, r.name, str(e)[:80]))

        if count:
            deleted.append("{0}: {1}".format(dt, count))

    # 5. Reset all rooms
    for r in frappe.get_all("Room", fields=["name"]):
        frappe.db.set_value("Room", r.name, {
            "room_status": "Vacant Clean",
            "current_guest": "",
            "current_stay": "",
            "housekeeping_status": ""
        })

    # 6. Reset all restaurant tables
    for t in frappe.get_all("Restaurant Table", fields=["name"]):
        frappe.db.set_value("Restaurant Table", t.name, {
            "table_status": "Available",
            "current_pos_order": ""
        })

    frappe.db.commit()

    # 7. Audit log
    try:
        frappe.get_doc({
            "doctype": "Activity Log",
            "subject": "HOTEL DATA PURGE by {0}".format(frappe.session.user),
            "content": "Deleted: {0}\nErrors: {1}".format(
                ", ".join(deleted) or "None",
                ", ".join(errors[:10]) or "None"),
            "user": frappe.session.user,
        }).insert(ignore_permissions=True)
    except Exception:
        pass

    result = {
        "deleted": deleted,
        "errors": errors[:10],
        "total_deleted": sum(int(d.split(": ")[1]) for d in deleted) if deleted else 0
    }

    frappe.msgprint(
        _("Purge complete. {0} records deleted. {1} errors.").format(
            result["total_deleted"], len(errors)),
        alert=True)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# PROTECT PROPERTY FROM COMPANY DELETION
# ─────────────────────────────────────────────────────────────────────────────

def protect_property_on_company_trash(doc, method=None):
    """
    When ERPNext deletes Company transactions, Property records might get caught.
    This hook prevents that by blocking Property deletion.
    """
    pass  # Property is not in _PURGE_ORDER and has its own doctype — ERPNext's
          # "Delete Company Transactions" tool only deletes standard ERPNext doctypes.
          # But as extra safety, we hook Property.on_trash below.


def block_property_deletion(doc, method=None):
    """
    Prevent accidental Property deletion.
    Only System Manager can delete, and only if no active stays exist.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Administrator can delete a Property."))

    active_stays = frappe.db.count("Guest Stay", {
        "property": doc.name,
        "stay_status": ["in", ["Expected", "Checked In"]],
        "docstatus": 1
    })
    if active_stays:
        frappe.throw(_(
            "Cannot delete Property {0}: {1} active stay(s) exist. "
            "Cancel or check out all stays first."
        ).format(doc.name, active_stays))


# ─────────────────────────────────────────────────────────────────────────────
# BILLING INTEGRITY CHECK — catch any blind spots
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def check_billing_integrity():
    """
    Hotel Manager action: scan all checked-in stays for billing gaps.
    Returns a list of stays missing charges for any past stay_date.
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("Only Hotel Manager can run billing integrity check."))

    from frappe.utils import getdate, add_days, today as _today
    today_date = getdate(_today())
    issues = []

    stays = frappe.get_all("Guest Stay",
        {"stay_status": "Checked In", "docstatus": 1},
        ["name", "guest_folio", "room", "guest_name", "arrival_date",
         "departure_date", "nightly_rate", "room_type"])

    for s in stays:
        if not s.guest_folio:
            issues.append({
                "stay": s.name, "room": s.room, "guest": s.guest_name,
                "issue": "No folio linked"
            })
            continue

        rate = flt(s.nightly_rate) or flt(
            frappe.db.get_value("Room Type", s.room_type, "bar_rate") or 0)

        # Get all charged dates for this stay
        charged_dates = set()
        rows = frappe.db.get_all("Folio Charge Line",
            {"parent": s.guest_folio, "charge_category": "Room Rate",
             "guest_stay": s.name, "is_void": 0},
            ["posting_date"])
        for r in rows:
            charged_dates.add(str(r.posting_date))

        # Check each stay_date from arrival to min(today, departure-1)
        departure = getdate(s.departure_date) if s.departure_date else add_days(today_date, 1)
        if today_date >= departure:
            last_night = today_date
        else:
            last_night = min(today_date, add_days(departure, -1))

        cur = getdate(s.arrival_date)
        missing = []
        while cur <= last_night:
            if str(cur) not in charged_dates:
                missing.append(str(cur))
            cur = add_days(cur, 1)

        if missing:
            issues.append({
                "stay": s.name, "room": s.room, "guest": s.guest_name,
                "issue": "{0} missing night(s): {1}".format(
                    len(missing), ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")),
                "missing_dates": missing,
                "rate": rate,
                "folio": s.guest_folio
            })

        # Check for duplicates
        from collections import Counter
        date_counts = Counter(str(r.posting_date) for r in rows)
        dupes = {d: c for d, c in date_counts.items() if c > 1}
        if dupes:
            issues.append({
                "stay": s.name, "room": s.room, "guest": s.guest_name,
                "issue": "DUPLICATE charges: {0}".format(
                    ", ".join("{0}(x{1})".format(d, c) for d, c in dupes.items())),
                "type": "duplicate"
            })

    return {"issues": issues, "total_stays_checked": len(stays), "issues_found": len(issues)}


@frappe.whitelist()
def fix_missing_charges(stay_name):
    """
    Hotel Manager: auto-fix missing room charges for a specific stay.
    Posts folio charges for any missing stay_dates.
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("Only Hotel Manager can fix charges."))

    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import (
        post_room_charge_to_folio, _room_charge_exists_for_date
    )
    from frappe.utils import getdate, add_days, today as _today

    stay = frappe.get_doc("Guest Stay", stay_name)
    if stay.stay_status != "Checked In":
        frappe.throw(_("Stay must be Checked In."))

    rate = flt(stay.nightly_rate) or flt(
        frappe.db.get_value("Room Type", stay.room_type, "bar_rate") or 0)
    if not rate:
        frappe.throw(_("No nightly rate."))

    today_date = getdate(_today())
    departure = getdate(stay.departure_date) if stay.departure_date else add_days(today_date, 1)
    if today_date >= departure:
        last_night = today_date
    else:
        last_night = min(today_date, add_days(departure, -1))

    fixed = 0
    cur = getdate(stay.arrival_date)
    while cur <= last_night:
        ds = str(cur)
        if not _room_charge_exists_for_date(stay.guest_folio, stay.name, ds):
            result = post_room_charge_to_folio(
                stay.guest_folio, stay.name, ds, rate, stay.room)
            if result:
                fixed += 1
        cur = add_days(cur, 1)

    return {"fixed": fixed, "message": _("{0} missing charge(s) posted.").format(fixed)}
