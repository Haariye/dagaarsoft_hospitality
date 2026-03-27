import frappe
from frappe import _
from frappe.utils import date_diff, now_datetime, flt, today, getdate
from frappe.model.document import Document


class GuestStay(Document):
    def validate(self):
        self._auto_fill_property()
        self._validate_dates()
        self._validate_room()
        self._set_computed_fields()
        self._fetch_rate_from_plan()
        # FIX 10: Always sync deposit info from linked reservation
        self._sync_reservation_deposit()

    def _auto_fill_property(self):
        if not self.property:
            try:
                self.property = frappe.db.get_single_value(
                    "Hospitality Settings", "hotel_property") or ""
            except Exception:
                pass

    def _validate_dates(self):
        if self.arrival_date and self.departure_date:
            nights = date_diff(self.departure_date, self.arrival_date)
            if nights <= 0:
                frappe.throw(_("Departure must be after Arrival."))
            self.num_nights = nights

    def _validate_room(self):
        if not self.room:
            frappe.throw(_("Room is mandatory."))
        if self.room and self.property:
            room = frappe.db.get_value("Room", self.room,
                ["property", "room_type", "is_out_of_order"], as_dict=True)
            if not room:
                frappe.throw(_("Room {0} not found.").format(self.room))
            if room.property != self.property:
                frappe.throw(_("Room {0} does not belong to Property {1}.").format(
                    self.room, self.property))
            if room.is_out_of_order:
                frappe.throw(_("Room {0} is Out of Order.").format(self.room))
            if not self.room_type:
                self.room_type = room.room_type

    def _set_computed_fields(self):
        if self.customer and not self.guest_name:
            self.guest_name = frappe.db.get_value(
                "Customer", self.customer, "customer_name") or ""

    def _fetch_rate_from_plan(self):
        if flt(self.nightly_rate) > 0:
            return
        rate_plan = self.rate_plan
        if not rate_plan and self.property:
            rate_plan = frappe.db.get_value("Property", self.property, "default_rate_plan")
        if not rate_plan:
            try:
                rate_plan = frappe.db.get_single_value("Hospitality Settings", "default_rate_plan")
            except Exception:
                pass
        if rate_plan:
            if not self.rate_plan:
                self.rate_plan = rate_plan
            if self.room_type:
                rate = flt(frappe.db.get_value("Rate Plan Line",
                    {"parent": rate_plan, "room_type": self.room_type}, "rate") or 0)
                if rate:
                    self.nightly_rate = rate
                    return
        if self.room_type:
            self.nightly_rate = flt(
                frappe.db.get_value("Room Type", self.room_type, "bar_rate") or 0)

    def _sync_reservation_deposit(self):
        """FIX 3+10: Pull advance_deposit from reservation if not set on stay."""
        if self.reservation and not self.advance_deposit:
            dep = frappe.db.get_value("Reservation", self.reservation, "hotel_deposit")
            if dep:
                self.advance_deposit = dep

    def on_submit(self):
        self.db_set("stay_status", "Expected")
        self._create_folio()
        frappe.db.set_value("Room", self.room, {
            "current_guest": self.guest_name,
            "current_stay": self.name
        })
        # FIX 10: Push billing_instruction to folio if set
        if self.billing_instruction and self.guest_folio:
            frappe.db.set_value("Guest Folio", self.guest_folio, {
                "billing_instruction": self.billing_instruction,
                "billing_customer": self.billing_customer or ""
            }, update_modified=False)

    def on_cancel(self):
        self.db_set("stay_status", "Cancelled")
        if self.guest_folio:
            frappe.db.set_value("Guest Folio", self.guest_folio,
                "folio_status", "Closed")
        if self.room:
            frappe.db.set_value("Room", self.room,
                {"current_guest": "", "current_stay": ""})

    def _create_folio(self):
        if frappe.db.exists("Guest Folio", {"guest_stay": self.name}):
            return
        invoice_customer = self.billing_customer or self.customer
        folio = frappe.new_doc("Guest Folio")
        folio.naming_series    = "FOL-.YYYY.-.####"
        folio.property         = self.property
        folio.guest_stay       = self.name
        folio.reservation      = self.reservation
        folio.customer         = self.customer
        folio.billing_customer = invoice_customer
        folio.room             = self.room
        folio.folio_status     = "Open"
        folio.billing_instruction = self.billing_instruction
        folio.nightly_rate     = self.nightly_rate
        folio.num_nights       = self.num_nights
        folio.rate_plan        = self.rate_plan
        folio.insert(ignore_permissions=True)
        folio.submit()
        self.db_set("guest_folio", folio.name)
        # FIX 3: If reservation has a deposit, push it to this folio
        if self.reservation:
            _push_reservation_deposit_to_folio(self.reservation, folio.name, self.name)


def _push_reservation_deposit_to_folio(reservation_name, folio_name, stay_name):
    """FIX 3: Copy reservation advance deposit payment lines to folio."""
    deposits = frappe.get_all("Hotel Deposit",
        {"reservation": reservation_name, "docstatus": 1,
         "deposit_status": ["in", ["Received", "Applied"]]},
        ["name", "deposit_amount", "payment_mode", "deposit_date",
         "reference_number", "payment_entry"])
    for dep in deposits:
        if dep.payment_entry and not frappe.db.exists("Folio Payment Line",
                {"parent": folio_name, "payment_entry": dep.payment_entry}):
            folio = frappe.get_doc("Guest Folio", folio_name)
            line = folio.append("folio_payments", {})
            line.payment_date     = dep.deposit_date or today()
            line.payment_mode     = dep.payment_mode
            line.description      = "Reservation Deposit - {0}".format(dep.name)
            line.amount           = flt(dep.deposit_amount)
            line.reference_number = dep.reference_number
            line.payment_entry    = dep.payment_entry
            line.posted_by        = "Administrator"
            folio.save(ignore_permissions=True)
            # Link the deposit to this stay
            frappe.db.set_value("Hotel Deposit", dep.name, "guest_stay",
                stay_name, update_modified=False)
            frappe.db.set_value("Guest Stay", stay_name, "advance_deposit",
                dep.name, update_modified=False)


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()


@frappe.whitelist()
def do_checkin(stay_name):
    stay = frappe.get_doc("Guest Stay", stay_name)
    if stay.stay_status != "Expected":
        frappe.throw(_("Stay must be Expected to check in."))
    if not stay.room:
        frappe.throw(_("Room is mandatory for check-in."))

    # FIX 7: Prevent same customer checking in same period in any room
    conflict = frappe.db.sql("""
        SELECT name, room FROM `tabGuest Stay`
        WHERE customer=%s AND stay_status='Checked In'
        AND name!=%s AND docstatus=1
        AND arrival_date < %s AND departure_date > %s
    """, (stay.customer, stay_name, stay.departure_date, stay.arrival_date), as_dict=True)
    if conflict:
        frappe.throw(_(
            "Customer {0} is already checked in at Room {1} for an overlapping period."
        ).format(stay.guest_name, conflict[0].room))

    # Deposit check
    prop = frappe.db.get_value("Property", stay.property,
        ["deposit_required", "waive_deposit_role"], as_dict=True) if stay.property else None
    try:
        global_dep = int(frappe.db.get_single_value("Hospitality Settings", "deposit_required") or 0)
    except Exception:
        global_dep = 0
    deposit_required = (prop and prop.deposit_required) or global_dep

    if deposit_required and not stay.deposit_waived:
        has_deposit = frappe.db.exists("Hotel Deposit",
            {"guest_stay": stay_name, "deposit_status": ["in", ["Received", "Applied"]],
             "docstatus": 1})
        # FIX 3: Also check reservation deposit
        if not has_deposit and stay.reservation:
            has_deposit = frappe.db.exists("Hotel Deposit",
                {"reservation": stay.reservation,
                 "deposit_status": ["in", ["Received", "Applied"]], "docstatus": 1})
        if not has_deposit and stay.guest_folio:
            fp = frappe.db.sql(
                "SELECT COUNT(*) FROM `tabFolio Payment Line` WHERE parent=%s AND amount>0",
                stay.guest_folio)[0][0]
            has_deposit = bool(fp)
        if not has_deposit:
            role = (prop.waive_deposit_role if prop else None) or "Hotel Manager"
            frappe.throw(_(
                "Advance deposit required before check-in. "
                "Collect deposit on the Folio or Reservation, or waive ({0} role)."
            ).format(role))

    # FIX 10: Update all fields at once, bypassing is_submittable restriction
    frappe.db.set_value("Guest Stay", stay_name, {
        "stay_status": "Checked In",
        "actual_checkin": now_datetime(),
        "checked_in_by": frappe.session.user
    }, update_modified=False)

    frappe.db.set_value("Room", stay.room, {
        "room_status": "Occupied",
        "current_guest": stay.guest_name,
        "current_stay": stay.name
    })
    if stay.reservation:
        frappe.db.set_value("Reservation", stay.reservation,
            "reservation_status", "Checked In", update_modified=False)
    frappe.msgprint(
        _("Checked in: {0} to Room {1}.").format(stay.guest_name, stay.room), alert=True)
    return stay_name


@frappe.whitelist()
def waive_deposit(stay_name, reason):
    stay = frappe.get_doc("Guest Stay", stay_name)
    required_role = (frappe.db.get_value("Property", stay.property, "waive_deposit_role")
        if stay.property else None) or "Hotel Manager"
    if required_role not in frappe.get_roles():
        frappe.throw(_("Only '{0}' role can waive deposit.").format(required_role))
    # FIX 10: Use db_set with update_modified=False to bypass submit restriction
    frappe.db.set_value("Guest Stay", stay_name, {
        "deposit_waived": 1,
        "deposit_waived_by": frappe.session.user,
        "deposit_waiver_reason": reason
    }, update_modified=False)
    frappe.msgprint(_("Deposit requirement waived."), alert=True)
    return {"ok": True}


@frappe.whitelist()
def do_checkout(stay_name, force_checkout=0, adjustment_note=None):
    """
    FIX 8: Allow early checkout with manager adjustment.
    FIX 9: Sponsored stays checkout freely.
    """
    stay = frappe.get_doc("Guest Stay", stay_name)
    if stay.stay_status != "Checked In":
        frappe.throw(_("Stay must be Checked In to check out."))
    if not stay.guest_folio:
        frappe.throw(_("No Folio found for this stay."))

    force = bool(int(force_checkout))
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import validate_checkout_billing
    check = validate_checkout_billing(stay_name, force_checkout=force)

    if not check["can_checkout"] and not force:
        frappe.throw(_("Cannot check out:\n{0}").format("\n".join(check["issues"])))

    # FIX 8: If forced early checkout by manager, void future room charges
    if check.get("is_early_checkout") and force:
        _void_future_room_charges(stay.guest_folio, stay_name)
        if adjustment_note:
            _post_adjustment_note(stay.guest_folio, stay_name, adjustment_note)

    # FIX 10: db_set bypasses submit restriction
    frappe.db.set_value("Guest Stay", stay_name, {
        "stay_status": "Checked Out",
        "actual_checkout": now_datetime(),
        "checked_out_by": frappe.session.user
    }, update_modified=False)

    frappe.db.set_value("Guest Folio", stay.guest_folio,
        "folio_status", "Closed", update_modified=False)
    frappe.db.set_value("Room", stay.room, {
        "room_status": "Vacant Dirty", "housekeeping_status": "Dirty",
        "current_guest": "", "current_stay": ""
    })
    if stay.reservation:
        frappe.db.set_value("Reservation", stay.reservation,
            "reservation_status", "Checked Out", update_modified=False)

    # Auto housekeeping task
    try:
        if not frappe.db.exists("Housekeeping Task",
                {"room": stay.room, "task_date": today(),
                 "task_type": "Cleaning", "docstatus": ["!=", 2]}):
            t = frappe.new_doc("Housekeeping Task")
            t.property = stay.property; t.room = stay.room
            t.task_type = "Cleaning"; t.task_date = today()
            t.task_status = "Pending"; t.priority = "High"
            t.notes = "Checkout: {0}".format(stay.guest_name)
            t.insert(ignore_permissions=True); t.submit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Checkout HK Error")

    frappe.msgprint(
        _("Checked out: {0} from Room {1}.").format(stay.guest_name, stay.room), alert=True)
    return stay_name


def _void_future_room_charges(folio_name, stay_name):
    """FIX 8: On early checkout, void room charges for future dates."""
    from frappe.utils import getdate, today
    folio = frappe.get_doc("Guest Folio", folio_name)
    changed = False
    for line in folio.folio_charges:
        if (line.charge_category == "Room Rate" and
                not line.is_void and not line.is_billed and
                line.reference_name == stay_name and
                line.posting_date and
                getdate(str(line.posting_date)) >= getdate(today())):
            line.is_void = 1
            line.void_reason = "Early checkout - future charge voided"
            changed = True
    if changed:
        folio.save(ignore_permissions=True)


def _post_adjustment_note(folio_name, stay_name, note):
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
    try:
        post_charge_to_folio(
            folio_name=folio_name,
            description="Early Checkout Adjustment: {0}".format(note),
            amount=0, charge_category="Adjustment",
            reference_doctype="Guest Stay", reference_name=stay_name)
    except Exception:
        pass

@frappe.whitelist()
def transfer_billing(stay_name, billing_customer, transfer_mode="from_now"):
    """
    FIX 4: Transfer billing to a third-party company or travel agency.
    transfer_mode:
      "from_now"  - only future charges use new billing_customer
      "all"       - also updates existing unbilled folio charges and the folio itself
    """
    stay = frappe.get_doc("Guest Stay", stay_name)

    # Update stay
    frappe.db.set_value("Guest Stay", stay_name, {
        "billing_customer": billing_customer,
        "billing_instruction": "Charge to Company" if billing_customer else "Charge to Room"
    }, update_modified=False)

    # Always update the folio's billing_customer
    if stay.guest_folio:
        frappe.db.set_value("Guest Folio", stay.guest_folio, {
            "billing_customer": billing_customer
        }, update_modified=False)

    if transfer_mode == "all" and stay.guest_folio:
        # Unbilled charges remain — they will use new billing_customer on next invoice
        # Also update any Draft Sales Invoices linked to this folio
        for si in frappe.get_all("Sales Invoice",
                {"hotel_folio": stay.guest_folio, "docstatus": 0}, ["name"]):
            frappe.db.set_value("Sales Invoice", si.name, "customer", billing_customer)

    frappe.msgprint(
        "Billing transferred to {0} ({1}).".format(
            frappe.db.get_value("Customer", billing_customer, "customer_name") or billing_customer,
            "all pending charges" if transfer_mode == "all" else "future charges only"),
        alert=True)
    return {"ok": True}


@frappe.whitelist()
def update_customer_cascade(stay_name, new_customer):
    """
    FIX 5: Update customer on Stay and cascade to all related documents.
    Updates: Guest Stay, Guest Folio, Hotel Deposit, Sales Invoice (draft only),
    Payment Entry (draft only).
    """
    stay = frappe.get_doc("Guest Stay", stay_name)
    old_customer = stay.customer
    if old_customer == new_customer:
        return {"changed": 0}

    new_name = frappe.db.get_value("Customer", new_customer, "customer_name") or new_customer
    updated = []

    # 1. Guest Stay
    frappe.db.set_value("Guest Stay", stay_name, {
        "customer": new_customer,
        "guest_name": new_name
    }, update_modified=False)
    updated.append("Guest Stay")

    # 2. Guest Folio
    if stay.guest_folio:
        folio = frappe.get_doc("Guest Folio", stay.guest_folio)
        # Only update customer if billing_customer was same as old customer
        update_data = {}
        if folio.customer == old_customer:
            update_data["customer"] = new_customer
        if not folio.billing_customer or folio.billing_customer == old_customer:
            update_data["billing_customer"] = new_customer
        if update_data:
            frappe.db.set_value("Guest Folio", stay.guest_folio,
                update_data, update_modified=False)
            updated.append("Guest Folio")

    # 3. Hotel Deposits (submitted — update customer for future reference)
    for dep in frappe.get_all("Hotel Deposit",
            {"guest_stay": stay_name}, ["name", "customer"]):
        if dep.customer == old_customer:
            frappe.db.set_value("Hotel Deposit", dep.name,
                "customer", new_customer, update_modified=False)
            updated.append("Hotel Deposit: " + dep.name)

    # 4. Draft Sales Invoices only (cannot modify submitted)
    if stay.guest_folio:
        for si in frappe.get_all("Sales Invoice",
                {"hotel_folio": stay.guest_folio, "docstatus": 0,
                 "customer": old_customer}, ["name"]):
            frappe.db.set_value("Sales Invoice", si.name,
                "customer", new_customer, update_modified=False)
            updated.append("Draft SI: " + si.name)

    # 5. Draft Payment Entries
    for pe in frappe.get_all("Payment Entry",
            {"hotel_stay": stay_name, "docstatus": 0,
             "party": old_customer}, ["name"]):
        frappe.db.set_value("Payment Entry", pe.name,
            "party", new_customer, update_modified=False)
        updated.append("Draft PE: " + pe.name)

    frappe.db.commit()
    frappe.msgprint(
        "Customer updated to {0}. Updated: {1}".format(
            new_name, ", ".join(updated)),
        alert=True)
    return {"changed": len(updated), "updated": updated}
