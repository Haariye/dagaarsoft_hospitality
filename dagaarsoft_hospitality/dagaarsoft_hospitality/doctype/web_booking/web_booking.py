# -*- coding: utf-8 -*-
"""
Web Booking — Online Reservation Portal
Handles website booking form submissions, converts to Reservation on approval.
"""
import frappe
import hashlib
import uuid
from frappe import _
from frappe.utils import flt, getdate, date_diff, today, now_datetime
from frappe.model.document import Document


class WebBooking(Document):

    def validate(self):
        self._calculate_nights()
        self._calculate_pricing()
        self._validate_dates()
        if not self.booking_token:
            self.booking_token = _generate_token()

    def _validate_dates(self):
        if self.arrival_date and self.departure_date:
            if getdate(self.arrival_date) >= getdate(self.departure_date):
                frappe.throw(_("Check-out must be after Check-in."))
            if getdate(self.arrival_date) < getdate(today()):
                frappe.throw(_("Check-in date cannot be in the past."))

    def _calculate_nights(self):
        if self.arrival_date and self.departure_date:
            self.num_nights = date_diff(self.departure_date, self.arrival_date)

    def _calculate_pricing(self):
        if self.room_type and self.num_nights:
            rate = _get_rate_for_room_type(self.room_type, self.rate_plan)
            self.nightly_rate = rate
            self.total_amount = flt(rate) * flt(self.num_nights)
            self.deposit_required = flt(self.total_amount) * 0.3  # 30% deposit

    def on_submit(self):
        self.db_set("booking_status", "Confirmed")
        self.db_set("submitted_on", now_datetime())
        self._send_confirmation_email()
        frappe.msgprint(
            _("Web Booking {0} confirmed. Confirmation sent to {1}.").format(
                self.name, self.guest_email
            ), alert=True
        )

    def _send_confirmation_email(self):
        try:
            frappe.sendmail(
                recipients=[self.guest_email],
                subject="Booking Confirmation — {0}".format(self.property),
                message=_get_confirmation_email_html(self),
                reference_doctype="Web Booking",
                reference_name=self.name
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Web Booking Email Error")


@frappe.whitelist(allow_guest=True)
def submit_web_booking(data):
    """
    Public API: Submit booking from website form.
    Called via AJAX from booking portal.
    """
    import json
    if isinstance(data, str):
        data = json.loads(data)

    # Validate required fields
    required = ["property", "guest_first_name", "guest_last_name", "guest_email",
                "guest_phone", "room_type", "arrival_date", "departure_date", "adults"]
    for f in required:
        if not data.get(f):
            frappe.throw(_("Field '{0}' is required.").format(f))

    # Check availability
    avail = check_availability(
        data["property"], data["room_type"],
        data["arrival_date"], data["departure_date"]
    )
    if not avail.get("available"):
        frappe.throw(_("Sorry, no rooms available for the selected dates. Please try different dates."))

    wb = frappe.new_doc("Web Booking")
    wb.property = data["property"]
    wb.guest_first_name = data["guest_first_name"]
    wb.guest_last_name = data["guest_last_name"]
    wb.guest_email = data["guest_email"]
    wb.guest_phone = data["guest_phone"]
    wb.guest_nationality = data.get("guest_nationality", "")
    wb.room_type = data["room_type"]
    wb.arrival_date = data["arrival_date"]
    wb.departure_date = data["departure_date"]
    wb.adults = int(data.get("adults", 1))
    wb.children = int(data.get("children", 0))
    wb.meal_plan = data.get("meal_plan", "Room Only")
    wb.special_requests = data.get("special_requests", "")
    wb.promo_code = data.get("promo_code", "")
    wb.ip_address = frappe.local.request.environ.get("REMOTE_ADDR", "") if frappe.local.request else ""
    wb.booking_status = "Pending"
    wb.insert(ignore_permissions=True)

    return {
        "success": True,
        "booking_id": wb.name,
        "token": wb.booking_token,
        "total_amount": wb.total_amount,
        "deposit_required": wb.deposit_required
    }


@frappe.whitelist(allow_guest=True)
def check_availability(property_name, room_type, arrival_date, departure_date):
    """Check real-time room availability for web booking."""
    # Count rooms of this type
    total_rooms = frappe.db.count("Room", {
        "property": property_name,
        "room_type": room_type,
        "is_active": 1,
        "is_out_of_order": 0
    })
    # Count conflicting stays
    booked = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabGuest Stay`
        WHERE room_type=%s AND property=%s
        AND stay_status IN ('Expected','Checked In')
        AND arrival_date < %s AND departure_date > %s
    """, (room_type, property_name, departure_date, arrival_date))[0][0]

    available_count = total_rooms - booked
    rate = _get_rate_for_room_type(room_type, None)
    nights = date_diff(departure_date, arrival_date)

    return {
        "available": available_count > 0,
        "available_count": available_count,
        "nightly_rate": rate,
        "total_nights": nights,
        "total_amount": flt(rate) * flt(nights)
    }


@frappe.whitelist(allow_guest=True)
def get_room_types_for_property(property_name):
    """Return room types with rates for booking widget."""
    room_types = frappe.get_all("Room Type",
        filters={"property": property_name},
        fields=["name", "room_type_name", "bar_rate", "description",
                "max_occupancy", "bed_type", "image"])
    return room_types


@frappe.whitelist(allow_guest=True)
def get_booking_status(token):
    """Guest-facing booking status lookup by token."""
    wb = frappe.db.get_value("Web Booking",
        {"booking_token": token},
        ["name", "booking_status", "arrival_date", "departure_date",
         "room_type", "total_amount", "guest_first_name", "reservation"],
        as_dict=True
    )
    if not wb:
        frappe.throw(_("Booking not found. Please check your confirmation email."))
    return wb


@frappe.whitelist()
def convert_to_reservation(web_booking_name):
    """
    Receptionist confirms web booking → creates Reservation + Customer.
    """
    wb = frappe.get_doc("Web Booking", web_booking_name)
    if wb.reservation:
        frappe.throw(_("Already converted to Reservation {0}.").format(wb.reservation))
    if wb.booking_status == "Cancelled":
        frappe.throw(_("Cannot convert a cancelled booking."))

    # Get or create Customer
    customer = _get_or_create_customer_from_booking(wb)

    # Create Reservation
    res = frappe.new_doc("Reservation")
    res.property = wb.property
    res.customer = customer
    res.arrival_date = wb.arrival_date
    res.departure_date = wb.departure_date
    res.meal_plan = wb.meal_plan
    res.special_requests = wb.special_requests
    res.source = "Online"
    res.reservation_status = "Confirmed"

    room_line = res.append("reservation_rooms", {})
    room_line.room_type = wb.room_type
    room_line.adults = wb.adults
    room_line.children = wb.children

    # Get rate
    rate = _get_rate_for_room_type(wb.room_type, wb.rate_plan)
    room_line.rate = rate

    res.insert(ignore_permissions=True)
    res.submit()

    # Update web booking
    wb.db_set("reservation", res.name)
    wb.db_set("customer", customer)
    wb.db_set("booking_status", "Converted")
    wb.db_set("converted_by", frappe.session.user)
    wb.db_set("converted_on", now_datetime())

    frappe.msgprint(
        _("Web Booking converted to Reservation {0}.").format(res.name), alert=True
    )
    return res.name


@frappe.whitelist()
def cancel_web_booking(web_booking_name, reason=None):
    """Cancel web booking and notify guest."""
    wb = frappe.get_doc("Web Booking", web_booking_name)
    wb.db_set("booking_status", "Cancelled")
    wb.db_set("cancellation_reason", reason or "Cancelled by staff")
    # Notify guest
    try:
        frappe.sendmail(
            recipients=[wb.guest_email],
            subject="Booking Cancellation — {0}".format(wb.property),
            message="<p>Dear {0},<br>Your booking (Ref: {1}) has been cancelled.</p><p>Reason: {2}</p>".format(
                wb.guest_first_name, wb.booking_token, reason or ""
            )
        )
    except Exception:
        pass
    return {"ok": True}


def _get_rate_for_room_type(room_type, rate_plan=None):
    if rate_plan:
        rate = frappe.db.get_value("Rate Plan Line",
            {"parent": rate_plan, "room_type": room_type}, "rate")
        if rate:
            return flt(rate)
    return flt(frappe.db.get_value("Room Type", room_type, "bar_rate") or 0)


def _get_or_create_customer_from_booking(wb):
    full_name = "{0} {1}".format(wb.guest_first_name, wb.guest_last_name)
    existing = frappe.db.get_value("Customer", {"customer_name": full_name}, "name")
    if existing:
        return existing
    c = frappe.new_doc("Customer")
    c.customer_name = full_name
    c.customer_type = "Individual"
    c.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "All Customer Groups"
    c.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"
    c.mobile_no = wb.guest_phone
    c.email_id = wb.guest_email
    c.insert(ignore_permissions=True)
    return c.name


def _generate_token():
    return hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:12].upper()


def _get_confirmation_email_html(wb):
    return """
    <html><body style="font-family:Arial,sans-serif;color:#333;">
    <h2 style="color:#2c5282;">Booking Confirmed ✓</h2>
    <p>Dear <strong>{first_name} {last_name}</strong>,</p>
    <p>Thank you for your reservation. Here are your booking details:</p>
    <table style="border-collapse:collapse;width:100%;max-width:500px;">
      <tr style="background:#f7fafc;"><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Booking Reference</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{token}</td></tr>
      <tr><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Property</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{property}</td></tr>
      <tr style="background:#f7fafc;"><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Room Type</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{room_type}</td></tr>
      <tr><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Check-In</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{arrival}</td></tr>
      <tr style="background:#f7fafc;"><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Check-Out</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{departure}</td></tr>
      <tr><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Guests</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{adults} Adults, {children} Children</td></tr>
      <tr style="background:#f7fafc;"><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Meal Plan</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;">{meal_plan}</td></tr>
      <tr><td style="padding:8px;border:1px solid #e2e8f0;"><strong>Total Amount</strong></td>
          <td style="padding:8px;border:1px solid #e2e8f0;color:#2c5282;font-weight:bold;">{total}</td></tr>
    </table>
    <br><p>We look forward to welcoming you!</p>
    <p style="color:#718096;font-size:12px;">Need help? Reply to this email or call our front desk.</p>
    </body></html>
    """.format(
        first_name=wb.guest_first_name, last_name=wb.guest_last_name,
        token=wb.booking_token, property=wb.property,
        room_type=wb.room_type, arrival=wb.arrival_date,
        departure=wb.departure_date, adults=wb.adults or 1,
        children=wb.children or 0, meal_plan=wb.meal_plan or "Room Only",
        total=frappe.format_value(wb.total_amount, {"fieldtype": "Currency"})
    )


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
