import frappe
from frappe import _
from frappe.utils import now_datetime, flt, date_diff, getdate, today, nowtime
from frappe.model.document import Document


class RoomMove(Document):
    def validate(self):
        if not self.guest_stay:
            frappe.throw(_("Guest Stay is required."))
        status = frappe.db.get_value("Guest Stay", self.guest_stay, "stay_status")
        if status != "Checked In":
            frappe.throw(_("Guest must be Checked In (current: {0}).").format(status))
        if self.to_room:
            r = frappe.db.get_value("Room", self.to_room,
                ["room_status", "is_out_of_order"], as_dict=True)
            if not r:
                frappe.throw(_("Target Room {0} not found.").format(self.to_room))
            if r.is_out_of_order:
                frappe.throw(_("Room {0} is Out of Order.").format(self.to_room))
            if r.room_status == "Occupied":
                # Allow if it's the same room (shouldn't happen but guard)
                curr = frappe.db.get_value("Guest Stay", self.guest_stay, "room")
                if r.room_status == "Occupied" and self.to_room != curr:
                    frappe.throw(_("Room {0} is already Occupied.").format(self.to_room))
        self._auto_fill()
        self._compute_rate()
        self._compute_billing()

    def _auto_fill(self):
        stay = frappe.db.get_value("Guest Stay", self.guest_stay,
            ["room", "nightly_rate", "room_type", "departure_date", "rate_plan"], as_dict=True)
        if not stay: return
        self.from_room     = stay.room
        self.old_room_type = stay.room_type
        self._departure    = stay.departure_date
        self._rate_plan    = stay.rate_plan
        # Ensure old_nightly_rate has a value — fall back to room_type bar_rate
        old_rate = flt(stay.nightly_rate)
        if not old_rate and stay.room_type:
            old_rate = flt(frappe.db.get_value("Room Type", stay.room_type, "bar_rate") or 0)
        self.old_nightly_rate = old_rate

    def _compute_rate(self):
        if not self.to_room: return
        new_rt = frappe.db.get_value("Room", self.to_room, "room_type")
        self.new_room_type = new_rt
        rate_plan = getattr(self, "_rate_plan", None)
        new_rate  = 0
        if rate_plan and new_rt:
            new_rate = flt(frappe.db.get_value("Rate Plan Line",
                {"parent": rate_plan, "room_type": new_rt}, "rate") or 0)
        if not new_rate and new_rt:
            new_rate = flt(frappe.db.get_value("Room Type", new_rt, "bar_rate") or 0)
        self.new_nightly_rate = new_rate

    def _compute_billing(self):
        old  = flt(self.old_nightly_rate)
        new  = flt(self.new_nightly_rate)
        diff = new - old
        dep  = getdate(getattr(self, "_departure", None) or
               frappe.db.get_value("Guest Stay", self.guest_stay, "departure_date"))
        move = getdate(self.move_date or today())
        remaining = max(date_diff(str(dep), str(move)), 0)
        self.rate_difference          = diff
        self.remaining_nights         = remaining
        self.total_billing_adjustment = diff * remaining
        if diff > 0:   self.adjustment_type = "Upgrade Surcharge"
        elif diff < 0: self.adjustment_type = "Downgrade Credit - refund at checkout"
        else:          self.adjustment_type = "No Rate Change"

    def on_submit(self):
        # FIX 6: Guard - if already posted, do not post again
        if self.billing_posted:
            frappe.msgprint(_("Billing already posted for this move."), alert=True)
            return

        stay  = frappe.get_doc("Guest Stay", self.guest_stay)
        old   = self.from_room; new = self.to_room
        diff  = flt(self.rate_difference); rem = flt(self.remaining_nights)
        new_rt   = self.new_room_type or frappe.db.get_value("Room", new, "room_type")
        new_rate = flt(self.new_nightly_rate) or flt(self.old_nightly_rate)

        frappe.db.set_value("Room", old, {
            "room_status": "Vacant Dirty", "housekeeping_status": "Dirty",
            "current_guest": "", "current_stay": ""})
        frappe.db.set_value("Room", new, {
            "room_status": "Occupied",
            "current_guest": stay.guest_name, "current_stay": stay.name})
        frappe.db.set_value("Guest Stay", self.guest_stay,
            {"room": new, "room_type": new_rt, "nightly_rate": new_rate},
            update_modified=False)

        if stay.guest_folio:
            frappe.db.set_value("Guest Folio", stay.guest_folio,
                {"room": new, "nightly_rate": new_rate}, update_modified=False)

            if diff != 0 and rem > 0:
                from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import _charge_exists
                if not _charge_exists(stay.guest_folio, "Room Move", self.name):
                    folio = frappe.get_doc("Guest Folio", stay.guest_folio)
                    if folio.folio_status == "Open":
                        cat   = "Room Rate Adjustment" if diff > 0 else "Room Rate Credit"
                        sign  = "+" if diff > 0 else "-"
                        abs_amt = abs(flt(diff * rem))
                        desc  = "{0}: {1}->{2} | {3}{4}/n x {5}n = {6}".format(
                            self.adjustment_type, old, new,
                            sign, round(abs(diff), 2), int(rem), round(abs_amt, 2))
                        line = folio.append("folio_charges", {})
                        line.description = desc
                        line.qty = flt(rem)
                        # FIX 6: Store as POSITIVE amount always — negative amounts
                        # cause "Grand Total must be >= 0" error on Sales Invoice.
                        # Room Rate Credit category signals it is a credit.
                        line.rate = flt(abs(diff))
                        line.amount = abs_amt
                        line.charge_category = cat
                        line.posting_date = str(self.move_date or today())
                        line.posting_time = nowtime()
                        line.reference_doctype = "Room Move"
                        line.reference_name = self.name
                        line.guest_stay = self.guest_stay
                        line.posted_by = frappe.session.user
                        line.is_read_only = 1
                        folio.save(ignore_permissions=True)

                        # FIX 6: Downgrade = Credit Note against the existing SI
                        if diff < 0 and folio.sales_invoice:
                            try:
                                _create_room_move_credit_note(
                                    folio.sales_invoice, stay.guest_folio,
                                    abs_amt, self.name, stay.name,
                                    stay.property, self.adjustment_type)
                            except Exception:
                                frappe.log_error(frappe.get_traceback(),
                                    "Room Move Credit Note Error")
                self.db_set("billing_posted", 1)

        # Auto housekeeping
        try:
            if not frappe.db.exists("Housekeeping Task",
                    {"room": old, "task_date": today(), "task_type": "Cleaning",
                     "docstatus": ["!=", 2]}):
                t = frappe.new_doc("Housekeeping Task")
                t.property = stay.property; t.room = old; t.task_type = "Cleaning"
                t.task_date = today(); t.task_status = "Pending"; t.priority = "High"
                t.notes = "Room Move - vacated: {0}".format(self.name)
                t.insert(ignore_permissions=True); t.submit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Room Move HK Error")

        self.db_set("move_time", now_datetime())
        frappe.msgprint(_("Room Move: {0} -> {1} | Rate: {2} -> {3}/n").format(
            old, new, round(flt(self.old_nightly_rate), 2), round(new_rate, 2)), alert=True)


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()


@frappe.whitelist()
def get_room_move_preview(guest_stay_name, to_room):
    stay = frappe.db.get_value("Guest Stay", guest_stay_name,
        ["room", "nightly_rate", "room_type", "departure_date", "rate_plan", "guest_name"],
        as_dict=True)
    if not stay: frappe.throw(_("Guest Stay not found."))
    new_rt = frappe.db.get_value("Room", to_room, "room_type")
    new_rate = 0
    if stay.rate_plan and new_rt:
        new_rate = flt(frappe.db.get_value("Rate Plan Line",
            {"parent": stay.rate_plan, "room_type": new_rt}, "rate") or 0)
    if not new_rate and new_rt:
        new_rate = flt(frappe.db.get_value("Room Type", new_rt, "bar_rate") or 0)
    old_rate = flt(stay.nightly_rate); diff = new_rate - old_rate
    dep = getdate(stay.departure_date) if stay.departure_date else getdate(today())
    remaining = max(date_diff(str(dep), str(getdate(today()))), 0)
    total = diff * remaining
    return {
        "guest_name": stay.guest_name, "from_room": stay.room, "to_room": to_room,
        "old_room_type": stay.room_type, "new_room_type": new_rt,
        "old_rate": old_rate, "new_rate": new_rate,
        "rate_difference": diff, "remaining_nights": remaining, "total_adjustment": total,
        "adjustment_type": ("No Rate Change" if diff == 0 else
                            "Upgrade Surcharge" if diff > 0 else "Downgrade Credit"),
        "message": ("No billing change." if diff == 0 else
                    "UPGRADE: +{0} ({1}n x +{2}/n)".format(
                        round(total, 2), remaining, round(diff, 2))
                    if diff > 0 else
                    "DOWNGRADE: Credit {0} ({1}n x {2}/n)".format(
                        round(abs(total), 2), remaining, round(diff, 2)))
    }

def _create_room_move_credit_note(original_si, folio_name, credit_amount, move_name,
                                    stay_name, property_name, adjustment_type):
    """
    FIX 6: Create a proper Credit Note (Return Invoice) for room downgrade.
    ERPNext cannot have negative grand_total on a Sales Invoice.
    A Credit Note is a return invoice linked to the original SI.
    """
    from frappe.utils import flt, today
    orig = frappe.get_doc("Sales Invoice", original_si)

    # Build credit note (return invoice)
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_return_doc
    try:
        credit_note = make_return_doc("Sales Invoice", original_si)
    except Exception:
        # Fallback: create manually
        credit_note = frappe.new_doc("Sales Invoice")
        credit_note.is_return = 1
        credit_note.return_against = original_si
        credit_note.customer = orig.customer
        credit_note.company = orig.company
        credit_note.debit_to = orig.debit_to

    credit_note.posting_date = today()
    credit_note.due_date = today()
    credit_note.hotel_folio = folio_name
    credit_note.hotel_stay = stay_name
    credit_note.hotel_room = orig.hotel_room
    credit_note.remarks = "Downgrade Credit - Room Move: {0} | {1}".format(
        move_name, adjustment_type)

    # Clear items and add single credit line
    credit_note.items = []
    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import _get_item, _default_income
    company = orig.company
    income_acct = _default_income(company)
    ic = _get_item("Room Rate Credit")
    uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
    r = credit_note.append("items", {})
    r.item_code = ic
    r.item_name = "Room Downgrade Credit - {0}".format(move_name)
    r.description = "Downgrade credit for Room Move {0}".format(move_name)
    r.qty = 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
    r.rate = flt(credit_amount); r.amount = flt(credit_amount)
    r.income_account = income_acct

    credit_note.taxes = []
    credit_note.set_missing_values()
    credit_note.calculate_taxes_and_totals()
    credit_note.insert(ignore_permissions=True)

    from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing import _register_folio_si
    _register_folio_si(folio_name, credit_note.name)
    credit_note.submit()

    frappe.msgprint(
        "Credit Note {0} created for room downgrade.".format(credit_note.name),
        alert=True)
    return credit_note.name
