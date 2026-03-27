from __future__ import unicode_literals

app_name        = "dagaarsoft_hospitality"
app_title       = "DagaarSoft Hospitality"
app_publisher   = "DagaarSoft"
app_description = "Enterprise Hotel & Hospitality Management for ERPNext v14/v15/v16"
app_email       = "support@dagaarsoft.com"
app_license     = "MIT"
app_version     = "5.1.0"
required_apps   = ["frappe", "erpnext"]

# ── Global JS (loaded on every page) ─────────────────────────────────────────
app_include_js = [
    "/assets/dagaarsoft_hospitality/js/property_session.js",
]

# ── Fixtures ──────────────────────────────────────────────────────────────────
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "DagaarSoft Hospitality"]]}
]

# ── Install ───────────────────────────────────────────────────────────────────
after_install  = "dagaarsoft_hospitality.install.after_install"
after_migrate  = ["dagaarsoft_hospitality.install.after_migrate"]

# ── DocType JS (plain static files — no build step) ───────────────────────────
doctype_js = {
    "Reservation":        "public/js/reservation.js",
    "Guest Stay":         "public/js/guest_stay.js",
    "Guest Folio":        "public/js/guest_folio.js",
    "Room Move":          "public/js/room_move.js",
    "Housekeeping Task":  "public/js/housekeeping_task.js",
    "Maintenance Ticket": "public/js/maintenance_ticket.js",
    "Banquet Booking":    "public/js/banquet_booking.js",
    "Night Audit Run":    "public/js/night_audit_run.js",
    "Room":               "public/js/room.js",
    "Sales Invoice":      "public/js/sales_invoice_extend.js",
    # ── Real Estate ────────────────────────────────────────────────────────────
    "RE Property":            "public/js/re/re_property.js",
    "RE Unit":                "public/js/re/re_unit.js",
    "RE Lease":               "public/js/re/re_lease.js",
    "RE Tenant":              "public/js/re/re_tenant.js",
    "RE Maintenance Request": "public/js/re/re_maintenance_request.js",
    "RE Inspection Report":   "public/js/re/re_inspection_report.js",
    "RE Notice":              "public/js/re/re_notice.js",
    "RE Utility Bill":        "public/js/re/re_utility_bill.js",
}

doctype_list_js = {
    "Reservation":       "public/js/list/reservation_list.js",
    "Guest Stay":        "public/js/list/guest_stay_list.js",
    "Room":              "public/js/list/room_list.js",
    "Housekeeping Task": "public/js/list/housekeeping_list.js",
}

# FIX 13: Inject hotel room widget into POSA on the POS page only
page_js = {
    "point-of-sale": "public/js/posa_overrides/hotel_room_mixin.js"
}

# ── Doc Events ────────────────────────────────────────────────────────────────
doc_events = {
    "Reservation": {
        "validate":    "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.reservation.reservation.validate",
        "before_save": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.reservation.reservation.before_save",
        "on_submit":   "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.reservation.reservation.on_submit",
        "on_cancel":   "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.reservation.reservation.on_cancel",
    },
    "Guest Stay": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.on_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.on_cancel",
    },
    "Guest Folio": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.on_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.on_cancel",
    },
    "Room Move": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.room_move.room_move.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.room_move.room_move.on_submit",
    },
    "Housekeeping Task": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.housekeeping_task.housekeeping_task.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.housekeeping_task.housekeeping_task.on_submit",
    },
    "Maintenance Ticket": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.maintenance_ticket.maintenance_ticket.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.maintenance_ticket.maintenance_ticket.on_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.maintenance_ticket.maintenance_ticket.on_cancel",
    },
    "Banquet Booking": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.banquet_booking.banquet_booking.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.banquet_booking.banquet_booking.on_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.banquet_booking.banquet_booking.on_cancel",
    },
    "Night Audit Run": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.night_audit_run.night_audit_run.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.night_audit_run.night_audit_run.on_submit",
    },
    "Hotel Deposit": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.hotel_deposit.hotel_deposit.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.hotel_deposit.hotel_deposit.on_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.hotel_deposit.hotel_deposit.on_cancel",
    },
    "Web Booking": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.web_booking.web_booking.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.web_booking.web_booking.on_submit",
    },
    "Sales Invoice": {
        # FIX 5: on_submit only posts F&B charge to folio for non-folio invoices
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.on_sales_invoice_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.on_sales_invoice_cancel",
    },

    # ── Real Estate ────────────────────────────────────────────────────────────
    "RE Lease": {
        "validate":  "dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease.validate",
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease.on_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease.on_cancel",
    },

    "Payment Entry": {
        # FIX 11: Immediately sync folio invoice status on payment
        "on_submit": "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.on_payment_entry_submit",
        "on_cancel": "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.on_payment_entry_cancel",
    },
}

# ── Scheduler ─────────────────────────────────────────────────────────────────
scheduler_events = {
    "cron": {
        "5 0 * * *": [
            "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.auto_post_room_charges",
            "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.flag_no_shows",
            "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.auto_night_audit",
        ],
        "0 6 * * *": [
            "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.flag_overdue_invoices",
            "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.send_arrival_reminders",
            "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.send_departure_reminders",
        ],
    },
    "hourly": [
        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.update_maintenance_overdue",
        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.update_housekeeping_overdue",
        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.sync_folio_invoice_statuses",
        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.auto_generate_supplementary_invoices",
    ],
    "daily": [
        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.auto_checkout_departed_guests",
        "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.tasks.check_lease_expiry",
        "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.tasks.generate_monthly_invoices",
        "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.tasks.apply_late_fees",

        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.purge_old_audit_logs",
    ],
    "weekly": [
        "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.tasks.generate_weekly_revenue_summary",
    ],
}

# ── Boot ──────────────────────────────────────────────────────────────────────
boot_session = "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.session.boot_session"

# ── Website ───────────────────────────────────────────────────────────────────
website_route_rules = [
    {"from_route": "/book-room",            "to_route": "book-room"},
    {"from_route": "/booking-confirmation", "to_route": "booking-confirmation"},
]
