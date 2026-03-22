import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.model.document import Document


class HotelDeposit(Document):

    def validate(self):
        self.balance_deposit = flt(self.deposit_amount) - flt(self.applied_amount) - flt(self.refund_amount)
        if flt(self.balance_deposit) < 0:
            frappe.throw(_("Applied + Refunded cannot exceed Deposit amount."))
        if not self.received_by:
            self.received_by = frappe.session.user

    def on_submit(self):
        # FIX 4: Prevent duplicate PE - check if one already exists for this deposit
        if self.payment_entry and frappe.db.exists("Payment Entry", self.payment_entry):
            frappe.msgprint(_("Payment Entry {0} already exists.").format(self.payment_entry), alert=True)
            return
        self.db_set("deposit_status", "Received")
        self.db_set("received_by", frappe.session.user)
        pe = self._create_advance_payment_entry()
        if pe:
            self.db_set("payment_entry", pe)
            self._sync_links(pe)
            frappe.msgprint(_("Advance Payment Entry {0} created.").format(pe), alert=True)

    def on_cancel(self):
        try:
            cascade = frappe.db.get_single_value("Hospitality Settings", "cascade_cancel_linked_transactions")
        except Exception:
            cascade = 1
        if cascade and self.payment_entry:
            try:
                pe_doc = frappe.get_doc("Payment Entry", self.payment_entry)
                if pe_doc.docstatus == 1:
                    pe_doc.cancel()
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Deposit Cancel PE Error")
        self._sync_links(None, cancelled=True)
        self.db_set("deposit_status", "Cancelled")

    def _create_advance_payment_entry(self):
        # FIX 4: Idempotency check - never create PE twice for same deposit
        existing = frappe.db.get_value("Payment Entry", {"hotel_deposit": self.name, "docstatus": 1}, "name")
        if existing:
            frappe.logger("dagaarsoft_hospitality").warning(
                f"PE already exists for deposit {self.name}: {existing}")
            return existing

        prop = frappe.db.get_value("Property", self.property,
            ["company", "debtors_account"], as_dict=True) if self.property else None
        company = (prop.company if prop else None) or frappe.defaults.get_defaults().get("company")

        # Get receivable account
        party_account = (
            (prop.debtors_account if prop else None) or
            frappe.db.get_value("Account",
                {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
        )
        party_currency = frappe.db.get_value("Account", party_account, "account_currency") or \
                         frappe.db.get_single_value("Global Defaults", "default_currency")

        paid_to = (
            frappe.db.get_value("Mode of Payment Account",
                {"parent": self.payment_mode, "company": company}, "default_account") or
            frappe.db.get_value("Account",
                {"company": company, "account_type": "Cash", "is_group": 0}, "name")
        )
        paid_to_currency = frappe.db.get_value("Account", paid_to, "account_currency") or party_currency

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = self.customer
        pe.party_account_currency = party_currency
        pe.company = company
        pe.posting_date = self.deposit_date or today()
        pe.mode_of_payment = self.payment_mode
        pe.paid_from = party_account
        pe.paid_from_account_currency = party_currency
        pe.paid_to = paid_to
        pe.paid_to_account_currency = paid_to_currency
        pe.paid_amount = flt(self.deposit_amount)
        pe.received_amount = flt(self.deposit_amount)
        pe.source_exchange_rate = 1
        pe.target_exchange_rate = 1
        pe.reference_no = self.reference_number or self.name
        pe.reference_date = self.deposit_date or today()
        pe.remarks = "Advance Deposit: {0} | {1}".format(
            self.name, self.reservation or self.guest_stay or "")
        pe.hotel_deposit = self.name
        pe.hotel_stay = self.guest_stay
        pe.hotel_reservation = getattr(self, "reservation", None)
        if self.guest_stay and frappe.db.exists("Guest Stay", self.guest_stay):
            pe.hotel_folio = frappe.db.get_value("Guest Stay", self.guest_stay, "guest_folio")
        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe.name

    def _sync_links(self, payment_entry_name=None, cancelled=False):
        # Sync to Guest Stay
        if self.guest_stay and frappe.db.exists("Guest Stay", self.guest_stay):
            frappe.db.set_value("Guest Stay", self.guest_stay,
                "advance_deposit", None if cancelled else self.name, update_modified=False)
            stay = frappe.get_doc("Guest Stay", self.guest_stay)
            if stay.guest_folio and frappe.db.exists("Guest Folio", stay.guest_folio):
                folio = frappe.get_doc("Guest Folio", stay.guest_folio)
                if not cancelled and payment_entry_name:
                    # FIX 4: Only add to folio if not already there
                    if not frappe.db.exists("Folio Payment Line",
                            {"parent": folio.name, "payment_entry": payment_entry_name}):
                        line = folio.append("folio_payments", {})
                        line.payment_date = self.deposit_date or today()
                        line.payment_mode = self.payment_mode
                        line.description = "Deposit - {0}".format(self.name)
                        line.amount = flt(self.deposit_amount)
                        line.reference_number = self.reference_number
                        line.payment_entry = payment_entry_name
                        line.posted_by = frappe.session.user
                        folio.save(ignore_permissions=True)
                elif cancelled:
                    changed = False
                    for row in list(folio.folio_payments):
                        if row.payment_entry == self.payment_entry:
                            folio.remove(row); changed = True
                    if changed:
                        folio.save(ignore_permissions=True)

        # FIX 3: Sync reservation -> guest stay deposit recognition
        reservation_name = getattr(self, "reservation", None)
        if reservation_name and frappe.db.exists("Reservation", reservation_name):
            update_reservation_deposit_status(reservation_name)
            # Push deposit to linked guest stays
            _sync_deposit_to_guest_stays(reservation_name, self.name if not cancelled else None,
                                          payment_entry_name, cancelled)

        if self.guest_stay:
            stay = frappe.db.get_value("Guest Stay", self.guest_stay, "reservation")
            if stay:
                update_reservation_deposit_status(stay)


def _sync_deposit_to_guest_stays(reservation_name, deposit_name, payment_entry_name, cancelled=False):
    """FIX 3: When deposit is on Reservation, push recognition to all linked Guest Stays."""
    stays = frappe.get_all("Guest Stay",
        {"reservation": reservation_name, "docstatus": 1,
         "stay_status": ["in", ["Expected", "Checked In"]]},
        ["name", "guest_folio"])
    for stay in stays:
        # Link the deposit to the guest stay
        frappe.db.set_value("Guest Stay", stay.name,
            "advance_deposit", None if cancelled else deposit_name, update_modified=False)
        # Add payment line to folio if not already there
        if stay.guest_folio and payment_entry_name and not cancelled:
            if not frappe.db.exists("Folio Payment Line",
                    {"parent": stay.guest_folio, "payment_entry": payment_entry_name}):
                try:
                    folio = frappe.get_doc("Guest Folio", stay.guest_folio)
                    line = folio.append("folio_payments", {})
                    dep = frappe.db.get_value("Hotel Deposit", deposit_name,
                        ["deposit_date", "payment_mode", "deposit_amount", "reference_number"], as_dict=True)
                    line.payment_date = dep.deposit_date or today()
                    line.payment_mode = dep.payment_mode
                    line.description = "Reservation Deposit - {0}".format(deposit_name)
                    line.amount = flt(dep.deposit_amount)
                    line.reference_number = dep.reference_number
                    line.payment_entry = payment_entry_name
                    line.posted_by = "Administrator"
                    folio.save(ignore_permissions=True)
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "Deposit Sync to Stay Error")


@frappe.whitelist()
def apply_deposit_to_invoice(deposit_name, sales_invoice_name):
    dep = frappe.get_doc("Hotel Deposit", deposit_name)
    si = frappe.get_doc("Sales Invoice", sales_invoice_name)
    available = flt(dep.deposit_amount) - flt(dep.applied_amount) - flt(dep.refund_amount)
    if available <= 0:
        return {"applied": 0}
    apply_amount = min(available, flt(si.outstanding_amount))
    if apply_amount <= 0:
        return {"applied": 0}

    prop = frappe.db.get_value("Property", dep.property,
        ["company", "debtors_account"], as_dict=True) if dep.property else None
    company = (prop.company if prop else None) or si.company

    paid_to = (
        frappe.db.get_value("Mode of Payment Account",
            {"parent": dep.payment_mode, "company": company}, "default_account") or
        frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name")
    )
    paid_from = frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = si.customer
    pe.company = company
    pe.posting_date = today()
    pe.mode_of_payment = dep.payment_mode or "Cash"
    pe.paid_from = paid_from
    pe.paid_to = paid_to
    pe.paid_amount = apply_amount
    pe.received_amount = apply_amount
    pe.reference_no = dep.name
    pe.reference_date = today()
    pe.hotel_deposit = dep.name
    pe.hotel_stay = dep.guest_stay
    pe.hotel_reservation = getattr(dep, "reservation", None)
    if dep.guest_stay and frappe.db.exists("Guest Stay", dep.guest_stay):
        pe.hotel_folio = frappe.db.get_value("Guest Stay", dep.guest_stay, "guest_folio")
    ref = pe.append("references", {})
    ref.reference_doctype = "Sales Invoice"
    ref.reference_name = sales_invoice_name
    ref.allocated_amount = apply_amount
    pe.set_missing_values()
    pe.insert(ignore_permissions=True)
    pe.submit()

    frappe.db.set_value("Hotel Deposit", deposit_name, {
        "applied_amount": flt(dep.applied_amount) + apply_amount,
        "balance_deposit": flt(dep.deposit_amount) - flt(dep.applied_amount) - apply_amount,
        "applied_to_invoice": sales_invoice_name,
        "deposit_status": "Applied"
    })
    return {"applied": apply_amount, "payment_entry": pe.name}


@frappe.whitelist()
def update_reservation_deposit_status(reservation_name):
    deposits = frappe.get_all("Hotel Deposit",
        {"reservation": reservation_name, "docstatus": 1},
        ["name", "deposit_amount", "applied_amount", "refund_amount"])
    paid = sum(flt(d.deposit_amount) - flt(d.refund_amount) for d in deposits)
    frappe.db.set_value("Reservation", reservation_name, "deposit_paid", paid, update_modified=False)
    req = flt(frappe.db.get_value("Reservation", reservation_name, "deposit_amount"))
    status = ("Not Required" if req <= 0 else
              "Paid" if paid >= req else
              "Partially Paid" if paid > 0 else "Pending")
    frappe.db.set_value("Reservation", reservation_name, "deposit_status", status, update_modified=False)
    if deposits:
        frappe.db.set_value("Reservation", reservation_name, "hotel_deposit",
            deposits[-1].name, update_modified=False)
    return {"deposit_paid": paid, "deposit_status": status}


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
