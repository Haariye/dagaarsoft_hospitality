# -*- coding: utf-8 -*-
"""
Reservation v3 — ERPNext Hotel Management
Tracks deposits, web bookings, improved validation
"""
import frappe
from frappe import _
from frappe.utils import getdate, date_diff, now_datetime
from frappe.model.document import Document


class Reservation(Document):

    def before_save(self):
        if self.arrival_date and self.departure_date:
            self.num_nights = date_diff(self.departure_date, self.arrival_date)
        if not self.reservation_number:
            self.reservation_number = self.name or ""
        self._populate_line_rates()

    def _populate_line_rates(self):
        default_rate_plan = self.rate_plan or (frappe.db.get_value("Property", self.property, "default_rate_plan") if self.property else None)
        for line in self.get("reservation_rooms") or []:
            if getattr(line, "rate", None):
                continue
            rate = 0
            use_plan = getattr(line, "rate_plan", None) or default_rate_plan
            if use_plan and line.room_type:
                rate = frappe.db.get_value("Rate Plan Line", {"parent": use_plan, "room_type": line.room_type}, "rate") or 0
            if not rate and line.room_type:
                rate = frappe.db.get_value("Room Type", line.room_type, "bar_rate") or 0
            line.rate = rate
            if not getattr(line, 'rate_plan', None) and use_plan:
                line.rate_plan = use_plan

    def validate(self):
        self.before_save()
        if not self.arrival_date or not self.departure_date:
            frappe.throw(_("Arrival and Departure dates are required."))
        if getdate(self.arrival_date) >= getdate(self.departure_date):
            frappe.throw(_("Departure must be after Arrival."))
        if not frappe.db.get_value("Property", self.property, "is_active"):
            frappe.throw(_("Property is not active."))
        if not self.get("reservation_rooms"):
            frappe.throw(_("At least one room line is required."))
        self._validate_room_lines()

    def _validate_room_lines(self):
        seen = []
        for idx, line in enumerate(self.reservation_rooms, 1):
            if not line.room_type:
                frappe.throw(_("Row {0}: Room Type is required.").format(idx))
            rt_prop = frappe.db.get_value("Room Type", line.room_type, "property")
            if rt_prop != self.property:
                frappe.throw(_("Row {0}: Room Type does not belong to this Property.").format(idx))
            if line.room:
                if line.room in seen:
                    frappe.throw(_("Row {0}: Room listed more than once.").format(idx))
                seen.append(line.room)
                r = frappe.db.get_value("Room", line.room,
                    ["property", "room_type", "is_out_of_order", "room_status"], as_dict=True)
                if not r:
                    frappe.throw(_("Row {0}: Room {1} not found.").format(idx, line.room))
                if r.property != self.property:
                    frappe.throw(_("Row {0}: Room does not belong to this Property.").format(idx))
                if r.room_type != line.room_type:
                    frappe.throw(_("Row {0}: Room is not of type {1}.").format(idx, line.room_type))
                if r.is_out_of_order:
                    frappe.throw(_("Row {0}: Room {1} is Out of Order.").format(idx, line.room))
                # Check for conflicting stays
                conflict = frappe.db.sql("""
                    SELECT name FROM `tabGuest Stay`
                    WHERE room=%s AND stay_status IN ('Expected','Checked In')
                    AND arrival_date < %s AND departure_date > %s
                    AND name != %s
                """, (line.room, self.departure_date, self.arrival_date, ""), as_dict=True)
                if conflict:
                    frappe.throw(_("Row {0}: Room {1} has a conflicting booking.").format(idx, line.room))

    def on_submit(self):
        self.db_set("reservation_status", "Confirmed")
        self.db_set("confirmed_on", now_datetime())
        self.db_set("created_by_user", frappe.session.user)
        self._create_guest_stays()
        frappe.msgprint(_("Reservation {0} confirmed.").format(self.name), alert=True)

    def on_cancel(self):
        self.db_set("reservation_status", "Cancelled")
        self.db_set("cancellation_date", now_datetime())
        self.db_set("cancelled_by", frappe.session.user)
        for s in frappe.get_all("Guest Stay",
            filters={"reservation": self.name, "stay_status": "Expected"},
            fields=["name", "docstatus"]
        ):
            sd = frappe.get_doc("Guest Stay", s["name"])
            if sd.docstatus == 1:
                sd.cancel()

    def _create_guest_stays(self):
        for line in self.get("reservation_rooms"):
            if frappe.db.exists("Guest Stay", {"reservation": self.name, "room": line.room}):
                continue
            stay = frappe.new_doc("Guest Stay")
            stay.naming_series = "STY-.YYYY.-.####"
            stay.property = self.property
            stay.reservation = self.name
            stay.customer = self.customer
            stay.room = line.room or None
            stay.room_type = line.room_type
            stay.arrival_date = self.arrival_date
            stay.departure_date = self.departure_date
            stay.adults = getattr(line, "adults", None) or self.adults or 1
            stay.children = getattr(line, "children", None) or self.children or 0
            stay.meal_plan = self.meal_plan
            stay.billing_instruction = self.billing_instruction
            stay.special_requests = self.special_requests
            stay.rate_plan = getattr(line, "rate_plan", None) or self.rate_plan
            stay.nightly_rate = getattr(line, "rate", 0) or 0
            stay.stay_status = "Expected"
            stay.source = self.source
            stay.web_booking = self.web_booking
            stay.insert(ignore_permissions=True)
            stay.submit()


@frappe.whitelist()
def get_available_rooms(property, room_type, arrival_date, departure_date, exclude_reservation=None):
    """Return available rooms for date range."""
    rooms = frappe.get_all("Room",
        filters={"property": property, "room_type": room_type,
                 "is_active": 1, "is_out_of_order": 0},
        fields=["name", "room_number", "floor", "wing", "room_status", "housekeeping_status"]
    )
    available = []
    for r in rooms:
        conflict = frappe.db.sql("""
            SELECT name FROM `tabGuest Stay`
            WHERE room=%s AND stay_status IN ('Expected','Checked In')
            AND arrival_date < %s AND departure_date > %s
        """, (r["name"], departure_date, arrival_date))
        if not conflict:
            available.append(r)
    return available


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
def before_save(doc, method=None): doc.before_save()
