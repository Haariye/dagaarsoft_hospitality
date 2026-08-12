import frappe
from frappe import _
from frappe.utils import date_diff, now_datetime, flt, today, getdate, cint
from frappe.model.document import Document


_VALID_TRANSITIONS = {
    "Expected":    ["Checked In", "Cancelled", "No Show"],
    "Checked In":  ["Checked Out"],
    "Checked Out": [],
    "Cancelled":   [],
    "No Show":     [],
}


def _validate_status_transition(current, new_status):
    allowed = _VALID_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        frappe.throw(_("Cannot transition from '{0}' to '{1}'. Allowed: {2}").format(
            current, new_status, ", ".join(allowed) or "None"))


def _log_audit(stay_name, action, details=""):
    try:
        frappe.get_doc({
            "doctype": "Activity Log",
            "subject": "Guest Stay {0}: {1}".format(stay_name, action),
            "content": details or action,
            "reference_doctype": "Guest Stay",
            "reference_name": stay_name,
            "user": frappe.session.user,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Audit Log Error")


class GuestStay(Document):
    def validate(self):
        self._auto_fill_property()
        self._validate_dates()
        self._validate_room()
        self._set_computed_fields()
        self._fetch_rate_from_plan()
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
        if self.reservation and not self.advance_deposit:
            dep = frappe.db.get_value("Reservation", self.reservation, "hotel_deposit")
            if dep:
                self.advance_deposit = dep

    def on_submit(self):
        self.db_set("stay_status", "Expected")
        self._create_folio()
        frappe.db.set_value("Room", self.room, {
            "current_guest": self.guest_name, "current_stay": self.name
        })
        if self.billing_instruction and self.guest_folio:
            frappe.db.set_value("Guest Folio", self.guest_folio, {
                "billing_instruction": self.billing_instruction,
                "billing_customer": self.billing_customer or ""
            }, update_modified=False)

    def on_cancel(self):
        self.db_set("stay_status", "Cancelled")
        if self.guest_folio:
            frappe.db.set_value("Guest Folio", self.guest_folio, "folio_status", "Closed")
        if self.room:
            frappe.db.set_value("Room", self.room, {"current_guest": "", "current_stay": ""})

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
        if self.reservation:
            _push_reservation_deposit_to_folio(self.reservation, folio.name, self.name)


def _push_reservation_deposit_to_folio(reservation_name, folio_name, stay_name):
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
            frappe.db.set_value("Hotel Deposit", dep.name, "guest_stay", stay_name, update_modified=False)
            frappe.db.set_value("Guest Stay", stay_name, "advance_deposit", dep.name, update_modified=False)


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()


@frappe.whitelist()
def do_checkin(stay_name):
    stay = frappe.get_doc("Guest Stay", stay_name)
    _validate_status_transition(stay.stay_status, "Checked In")
    if not stay.room:
        frappe.throw(_("Room is mandatory for check-in."))

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
            {"guest_stay": stay_name, "deposit_status": ["in", ["Received", "Applied"]], "docstatus": 1})
        if not has_deposit and stay.reservation:
            has_deposit = frappe.db.exists("Hotel Deposit",
                {"reservation": stay.reservation, "deposit_status": ["in", ["Received", "Applied"]], "docstatus": 1})
        if not has_deposit and stay.guest_folio:
            fp = frappe.db.sql("SELECT COUNT(*) FROM `tabFolio Payment Line` WHERE parent=%s AND amount>0",
                stay.guest_folio)[0][0]
            has_deposit = bool(fp)
        if not has_deposit:
            role = (prop.waive_deposit_role if prop else None) or "Hotel Manager"
            frappe.throw(_("Advance deposit required. Collect or waive ({0}).").format(role))

    frappe.db.set_value("Guest Stay", stay_name, {
        "stay_status": "Checked In", "actual_checkin": now_datetime(),
        "checked_in_by": frappe.session.user
    }, update_modified=False)

    frappe.db.set_value("Room", stay.room, {
        "room_status": "Occupied", "current_guest": stay.guest_name, "current_stay": stay.name
    })
    if stay.reservation:
        frappe.db.set_value("Reservation", stay.reservation,
            "reservation_status", "Checked In", update_modified=False)

    # Post first night room charge to folio (no invoice — invoiced at checkout)
    try:
        from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import post_room_charge_to_folio
        post_room_charge_to_folio(
            stay.guest_folio, stay.name, today(),
            flt(stay.nightly_rate), stay.room)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Checkin First Charge Error")

    _log_audit(stay_name, "Checked In", "Room: {0}".format(stay.room))
    frappe.msgprint(_("Checked in: {0} to Room {1}.").format(stay.guest_name, stay.room), alert=True)
    return stay_name


@frappe.whitelist()
def waive_deposit(stay_name, reason):
    stay = frappe.get_doc("Guest Stay", stay_name)
    required_role = (frappe.db.get_value("Property", stay.property, "waive_deposit_role")
        if stay.property else None) or "Hotel Manager"
    if required_role not in frappe.get_roles():
        frappe.throw(_("Only '{0}' can waive deposit.").format(required_role))
    frappe.db.set_value("Guest Stay", stay_name, {
        "deposit_waived": 1, "deposit_waived_by": frappe.session.user,
        "deposit_waiver_reason": reason
    }, update_modified=False)
    _log_audit(stay_name, "Deposit Waived", "Reason: {0}".format(reason))
    frappe.msgprint(_("Deposit waived."), alert=True)
    return {"ok": True}


@frappe.whitelist()
def extend_stay(stay_name, new_departure_date, reason=""):
    stay = frappe.get_doc("Guest Stay", stay_name)
    if stay.stay_status != "Checked In":
        frappe.throw(_("Can only extend a Checked In stay."))
    new_dep = getdate(new_departure_date)
    old_dep = getdate(stay.departure_date)
    if new_dep <= old_dep:
        frappe.throw(_("New departure must be after current ({0}).").format(old_dep))
    new_nights = date_diff(new_dep, getdate(stay.arrival_date))
    added = new_nights - cint(stay.num_nights)

    frappe.db.set_value("Guest Stay", stay_name, {
        "departure_date": str(new_dep), "num_nights": new_nights
    }, update_modified=False)
    if stay.guest_folio:
        frappe.db.set_value("Guest Folio", stay.guest_folio,
            {"num_nights": new_nights}, update_modified=False)

    _log_audit(stay_name, "Stay Extended",
        "{0} → {1} (+{2}). Reason: {3}".format(old_dep, new_dep, added, reason or "N/A"))
    frappe.msgprint(_("Extended +{0} nights → {1}.").format(added, new_dep), alert=True)
    return {"old_departure": str(old_dep), "new_departure": str(new_dep),
            "old_nights": cint(stay.num_nights), "new_nights": new_nights, "added_nights": added}


@frappe.whitelist()
def do_checkout(stay_name, force_checkout=0, adjustment_note=None):
    stay = frappe.get_doc("Guest Stay", stay_name)
    _validate_status_transition(stay.stay_status, "Checked Out")
    if not stay.guest_folio:
        frappe.throw(_("No Folio found."))

    force = bool(int(force_checkout))
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import validate_checkout_billing
    check = validate_checkout_billing(stay_name, force_checkout=force)

    if not check["can_checkout"] and not force:
        frappe.throw(_("Cannot check out:\n{0}").format("\n".join(check["issues"])))

    if check.get("is_early_checkout") and force:
        _void_future_room_charges(stay.guest_folio, stay_name)
        if adjustment_note:
            _post_adjustment_note(stay.guest_folio, stay_name, adjustment_note)
        _log_audit(stay_name, "Forced Early Checkout", adjustment_note or "")

    frappe.db.set_value("Guest Stay", stay_name, {
        "stay_status": "Checked Out", "actual_checkout": now_datetime(),
        "checked_out_by": frappe.session.user
    }, update_modified=False)

    folio = frappe.get_doc("Guest Folio", stay.guest_folio)
    if flt(folio.balance_due) <= 0.005:
        frappe.db.set_value("Guest Folio", stay.guest_folio,
            "folio_status", "Closed", update_modified=False)

    frappe.db.set_value("Room", stay.room, {
        "room_status": "Vacant Dirty", "housekeeping_status": "Dirty",
        "current_guest": "", "current_stay": ""
    })
    if stay.reservation:
        frappe.db.set_value("Reservation", stay.reservation,
            "reservation_status", "Checked Out", update_modified=False)

    try:
        if not frappe.db.exists("Housekeeping Task",
                {"room": stay.room, "task_date": today(), "task_type": "Cleaning", "docstatus": ["!=", 2]}):
            t = frappe.new_doc("Housekeeping Task")
            t.property = stay.property; t.room = stay.room
            t.task_type = "Cleaning"; t.task_date = today()
            t.task_status = "Pending"; t.priority = "High"
            t.notes = "Checkout: {0}".format(stay.guest_name)
            t.insert(ignore_permissions=True); t.submit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Checkout HK Error")

    _log_audit(stay_name, "Checked Out", "Room: {0}".format(stay.room))
    frappe.msgprint(_("Checked out: {0} from Room {1}.").format(stay.guest_name, stay.room), alert=True)
    return stay_name


def _void_future_room_charges(folio_name, stay_name):
    folio = frappe.get_doc("Guest Folio", folio_name)
    changed = False
    for line in folio.folio_charges:
        if (line.charge_category == "Room Rate" and not line.is_void and not line.is_billed
                and line.reference_name == stay_name and line.posting_date
                and getdate(str(line.posting_date)) >= getdate(today())):
            line.is_void = 1; line.void_reason = "Early checkout"; changed = True
    if changed:
        folio.save(ignore_permissions=True)


def _post_adjustment_note(folio_name, stay_name, note):
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
    try:
        post_charge_to_folio(folio_name=folio_name,
            description="Early Checkout: {0}".format(note),
            amount=0, charge_category="Adjustment",
            reference_doctype="Guest Stay", reference_name=stay_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Adjustment Note Error")


@frappe.whitelist()
def transfer_billing(stay_name, billing_customer, transfer_mode="from_now"):
    stay = frappe.get_doc("Guest Stay", stay_name)
    frappe.db.set_value("Guest Stay", stay_name, {
        "billing_customer": billing_customer,
        "billing_instruction": "Charge to Company" if billing_customer else "Charge to Room"
    }, update_modified=False)
    if stay.guest_folio:
        frappe.db.set_value("Guest Folio", stay.guest_folio,
            {"billing_customer": billing_customer}, update_modified=False)
    if transfer_mode == "all" and stay.guest_folio:
        for si in frappe.get_all("Sales Invoice",
                {"hotel_folio": stay.guest_folio, "docstatus": 0}, ["name"]):
            frappe.db.set_value("Sales Invoice", si.name, "customer", billing_customer)
    _log_audit(stay_name, "Billing Transferred", "To: {0} ({1})".format(billing_customer, transfer_mode))
    frappe.msgprint("Billing transferred.", alert=True)
    return {"ok": True}


@frappe.whitelist()
def update_customer_cascade(stay_name, new_customer):
    stay = frappe.get_doc("Guest Stay", stay_name)
    old_customer = stay.customer
    if old_customer == new_customer:
        return {"changed": 0}
    new_name = frappe.db.get_value("Customer", new_customer, "customer_name") or new_customer
    updated = []
    frappe.db.set_value("Guest Stay", stay_name,
        {"customer": new_customer, "guest_name": new_name}, update_modified=False)
    updated.append("Guest Stay")
    if stay.guest_folio:
        folio = frappe.get_doc("Guest Folio", stay.guest_folio)
        upd = {}
        if folio.customer == old_customer: upd["customer"] = new_customer
        if not folio.billing_customer or folio.billing_customer == old_customer:
            upd["billing_customer"] = new_customer
        if upd:
            frappe.db.set_value("Guest Folio", stay.guest_folio, upd, update_modified=False)
            updated.append("Guest Folio")
    frappe.db.commit()
    _log_audit(stay_name, "Customer Changed", "{0} → {1}".format(old_customer, new_customer))
    frappe.msgprint("Customer updated to {0}.".format(new_name), alert=True)
    return {"changed": len(updated), "updated": updated}


# ═══════════════════════════════════════════════════════════════════════════════
#  CASCADE CANCEL — Hotel Manager only
# ═══════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def cascade_cancel_stay(stay_name):
    """
    Hotel Manager: cancel a Guest Stay and ALL linked documents in correct order.
    Order: Payment Entries → Sales Invoices → Deposits → Folio → Stay → Reservation
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("You are not a Hotel Manager. Only Hotel Manager role can cancel all linked documents."))

    stay = frappe.get_doc("Guest Stay", stay_name)
    if stay.docstatus != 1:
        frappe.throw(_("Stay must be submitted to cancel."))

    cancelled = []
    folio_name = stay.guest_folio

    if folio_name and frappe.db.exists("Guest Folio", folio_name):
        # 1. Cancel Payment Entries linked to this folio
        for pe in frappe.get_all("Payment Entry",
                {"hotel_folio": folio_name, "docstatus": 1}, ["name"]):
            try:
                doc = frappe.get_doc("Payment Entry", pe.name)
                doc.flags.ignore_links = True
                doc.flags.ignore_validate_update_after_submit = True
                doc.cancel()
                cancelled.append("PE: " + pe.name)
            except Exception as e:
                frappe.log_error(str(e)[:120], "Cascade PE")

        # 2. Cancel Sales Invoices linked to this folio
        for si in frappe.get_all("Sales Invoice",
                {"hotel_folio": folio_name, "docstatus": 1}, ["name"],
                order_by="posting_date desc"):
            try:
                doc = frappe.get_doc("Sales Invoice", si.name)
                doc.flags.ignore_links = True
                doc.flags.ignore_validate_update_after_submit = True
                # Skip posa_integration hook during cascade
                doc.flags.from_cascade_cancel = True
                doc.cancel()
                cancelled.append("SI: " + si.name)
            except Exception as e:
                frappe.log_error(str(e)[:120], "Cascade SI")

        # 3. Cancel Hotel Deposits
        for dep in frappe.get_all("Hotel Deposit",
                {"guest_stay": stay_name, "docstatus": 1}, ["name"]):
            try:
                doc = frappe.get_doc("Hotel Deposit", dep.name)
                doc.flags.ignore_links = True
                doc.cancel()
                cancelled.append("DEP: " + dep.name)
            except Exception as e:
                frappe.log_error(str(e)[:120], "Cascade DEP")

        # 4. Cancel Guest Folio
        try:
            folio = frappe.get_doc("Guest Folio", folio_name)
            folio.flags.ignore_links = True
            folio.cancel()
            cancelled.append("Folio: " + folio_name)
        except Exception as e:
            frappe.log_error(str(e)[:120], "Cascade Folio")

    # 5. Cancel Guest Stay
    stay.reload()
    stay.flags.ignore_links = True
    stay.cancel()
    cancelled.append("Stay: " + stay_name)

    # 6. Reset Room
    if stay.room:
        frappe.db.set_value("Room", stay.room, {
            "room_status": "Vacant Clean", "current_guest": "", "current_stay": ""
        })

    # 7. Cancel Reservation (if linked and no other active stays depend on it)
    if stay.reservation and frappe.db.exists("Reservation", stay.reservation):
        other_stays = frappe.db.count("Guest Stay", {
            "reservation": stay.reservation,
            "docstatus": 1,
            "name": ["!=", stay_name]
        })
        if other_stays == 0:
            try:
                res = frappe.get_doc("Reservation", stay.reservation)
                if res.docstatus == 1:
                    res.flags.ignore_links = True
                    res.cancel()
                    cancelled.append("Reservation: " + stay.reservation)
            except Exception as e:
                frappe.log_error(str(e)[:120], "Cascade Reservation")

    _log_audit(stay_name, "Cascade Cancelled",
        "Cancelled {0} documents: {1}".format(len(cancelled), ", ".join(cancelled)))

    frappe.msgprint(
        _("Cancelled {0} documents: {1}").format(len(cancelled), ", ".join(cancelled)),
        alert=True)
    return {"cancelled": cancelled, "count": len(cancelled)}
