# -*- coding: utf-8 -*-
"""
Night Audit Run v3 — Full transparency, one-click operation.
Posts room charges, flags no-shows, generates audit summary.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, flt, today, getdate, add_days
from frappe.model.document import Document


class NightAuditRun(Document):

    def validate(self):
        if not self.audit_date:
            frappe.throw(_("Audit Date is required."))
        if frappe.db.exists("Night Audit Run", {
            "audit_date": self.audit_date, "property": self.property,
            "audit_status": "Completed", "name": ["!=", self.name or ""]
        }):
            frappe.throw(_("Night Audit already completed for {0} on {1}.").format(
                self.property, self.audit_date))

    def on_submit(self):
        self._preview_and_post_rates()
        self._flag_no_shows()
        self._handle_expected_arrivals()
        self._generate_summary()
        self.db_set("audit_status", "Completed")
        self.db_set("run_by", frappe.session.user)
        self.db_set("completed_at", now_datetime())
        frappe.msgprint(
            _("✓ Night Audit completed for {0}. {1} rooms charged, {2} no-shows flagged.").format(
                self.audit_date, self.rooms_charged or 0, self.no_shows_flagged or 0
            ), alert=True
        )

    def _preview_and_post_rates(self):
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
        stays = frappe.get_all("Guest Stay",
            filters={
                "property": self.property,
                "stay_status": "Checked In",
                "arrival_date": ["<=", self.audit_date],
                "departure_date": [">", self.audit_date]
            },
            fields=["name", "guest_folio", "room", "room_type", "nightly_rate",
                    "customer", "guest_name"]
        )
        count = 0
        total = 0
        charge_log = []
        for s in stays:
            if not s.guest_folio:
                continue
            # Check if already charged for this night
            already = frappe.db.sql("""
                SELECT COUNT(*) FROM `tabFolio Charge Line`
                WHERE parent=%s AND charge_category='Room Rate'
                AND posting_date=%s AND is_void=0
            """, (s.guest_folio, self.audit_date))[0][0]
            if already:
                continue

            rate = flt(s.nightly_rate) or flt(
                frappe.db.get_value("Room Type", s.room_type, "bar_rate") or 0
            )
            if rate:
                post_charge_to_folio(
                    s.guest_folio,
                    "Room Charge — {0} — {1}".format(s.room, self.audit_date),
                    rate,
                    "Room Rate",
                    "Night Audit Run",
                    self.name
                )
                count += 1
                total += rate
                charge_log.append({
                    "room": s.room,
                    "guest": s.guest_name,
                    "folio": s.guest_folio,
                    "amount": rate
                })

        self.db_set("rooms_charged", count)
        self.db_set("total_revenue", total)
        # Store log as JSON for transparency dashboard
        import json
        self.db_set("charge_log", json.dumps(charge_log))

    def _flag_no_shows(self):
        ns = frappe.get_all("Guest Stay",
            filters={
                "property": self.property,
                "stay_status": "Expected",
                "arrival_date": self.audit_date
            },
            fields=["name", "reservation"]
        )
        for s in ns:
            frappe.db.set_value("Guest Stay", s.name, "stay_status", "No Show")
            if s.reservation:
                frappe.db.set_value("Reservation", s.reservation, "reservation_status", "No Show")
        self.db_set("no_shows_flagged", len(ns))

    def _handle_expected_arrivals(self):
        """Flag late checkouts and generate morning report data."""
        next_day = str(add_days(getdate(self.audit_date), 1))
        arrivals = frappe.db.count("Guest Stay", {
            "property": self.property,
            "stay_status": "Expected",
            "arrival_date": next_day
        })
        departures = frappe.db.count("Guest Stay", {
            "property": self.property,
            "stay_status": "Checked In",
            "departure_date": next_day
        })
        self.db_set("expected_arrivals_tomorrow", arrivals)
        self.db_set("expected_departures_tomorrow", departures)

    def _generate_summary(self):
        """Compute occupancy and revenue stats for audit report."""
        total_rooms = frappe.db.count("Room", {
            "property": self.property, "is_active": 1, "is_out_of_order": 0
        })
        occupied = frappe.db.count("Guest Stay", {
            "property": self.property,
            "stay_status": "Checked In",
            "arrival_date": ["<=", self.audit_date],
            "departure_date": [">", self.audit_date]
        })
        occ_pct = (occupied / total_rooms * 100) if total_rooms else 0
        self.db_set("occupancy_pct", round(occ_pct, 2))
        self.db_set("occupied_rooms", occupied)
        self.db_set("total_rooms", total_rooms)


@frappe.whitelist()
def preview_night_audit(property_name, audit_date):
    """
    Preview what the night audit will do — called BEFORE submitting.
    Returns full transparency data for manager review.
    """
    # Rooms to be charged
    stays = frappe.get_all("Guest Stay",
        filters={
            "property": property_name,
            "stay_status": "Checked In",
            "arrival_date": ["<=", audit_date],
            "departure_date": [">", audit_date]
        },
        fields=["name", "room", "room_type", "nightly_rate", "guest_name",
                "guest_folio", "arrival_date", "departure_date"]
    )
    charge_preview = []
    total_to_charge = 0
    for s in stays:
        already = frappe.db.sql("""
            SELECT COUNT(*) FROM `tabFolio Charge Line`
            WHERE parent=%s AND charge_category='Room Rate'
            AND posting_date=%s AND is_void=0
        """, (s.guest_folio, audit_date))[0][0] if s.guest_folio else 0

        rate = flt(s.nightly_rate) or flt(
            frappe.db.get_value("Room Type", s.room_type, "bar_rate") or 0
        )
        charge_preview.append({
            "room": s.room,
            "guest": s.guest_name,
            "folio": s.guest_folio,
            "nights_so_far": frappe.utils.date_diff(audit_date, s.arrival_date),
            "nightly_rate": rate,
            "already_charged_tonight": bool(already),
            "will_charge": not bool(already) and rate > 0
        })
        if not already and rate > 0:
            total_to_charge += rate

    # No-shows
    no_shows = frappe.get_all("Guest Stay",
        filters={
            "property": property_name,
            "stay_status": "Expected",
            "arrival_date": audit_date
        },
        fields=["name", "guest_name", "room_type", "reservation"]
    )

    # Tomorrow's arrivals
    next_day = str(frappe.utils.add_days(frappe.utils.getdate(audit_date), 1))
    arrivals_tomorrow = frappe.db.count("Guest Stay", {
        "property": property_name, "stay_status": "Expected", "arrival_date": next_day
    })
    departures_tomorrow = frappe.db.count("Guest Stay", {
        "property": property_name, "stay_status": "Checked In", "departure_date": next_day
    })

    total_rooms = frappe.db.count("Room", {"property": property_name, "is_active": 1})
    occupied = len([s for s in charge_preview if s["will_charge"] or s["already_charged_tonight"]])

    return {
        "audit_date": audit_date,
        "property": property_name,
        "rooms_to_charge": [s for s in charge_preview if s["will_charge"]],
        "already_charged": [s for s in charge_preview if s["already_charged_tonight"]],
        "no_shows": no_shows,
        "total_to_charge": total_to_charge,
        "arrivals_tomorrow": arrivals_tomorrow,
        "departures_tomorrow": departures_tomorrow,
        "occupancy": {
            "occupied": occupied,
            "total": total_rooms,
            "pct": round(occupied / total_rooms * 100, 1) if total_rooms else 0
        },
        "already_run": frappe.db.exists("Night Audit Run", {
            "audit_date": audit_date, "property": property_name, "audit_status": "Completed"
        })
    }


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
