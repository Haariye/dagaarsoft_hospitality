import frappe
from frappe import _
from frappe.utils import flt, today, date_diff, getdate, add_days, nowtime, now_datetime


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _charge_exists(folio_name, reference_doctype, reference_name):
    return frappe.db.exists("Folio Charge Line", {
        "parent": folio_name,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "is_void": 0
    })


def _room_charge_exists_for_date(folio_name, stay_name, posting_date):
    return frappe.db.sql("""
        SELECT COUNT(*) FROM `tabFolio Charge Line`
        WHERE parent=%s AND charge_category='Room Rate'
        AND reference_name=%s AND posting_date=%s AND is_void=0
    """, (folio_name, stay_name, posting_date))[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# INVOICE STATUS
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_invoice_billing_status(sales_invoice_name):
    if not sales_invoice_name or not frappe.db.exists("Sales Invoice", sales_invoice_name):
        return {"status": "Not Found", "paid": 0, "outstanding": 0,
                "grand_total": 0, "label": "\u2014", "color": "grey"}
    si = frappe.db.get_value("Sales Invoice", sales_invoice_name,
        ["status", "grand_total", "outstanding_amount",
         "due_date", "docstatus", "is_return"], as_dict=True)
    if not si:
        return {"status": "Not Found", "paid": 0, "outstanding": 0,
                "grand_total": 0, "label": "\u2014", "color": "grey"}
    gt  = flt(si.grand_total)
    ost = flt(si.outstanding_amount)
    if si.docstatus == 2:
        return {"status": "Cancelled", "paid": 0, "outstanding": 0,
                "grand_total": gt, "label": "Cancelled", "color": "red"}
    if si.is_return:
        return {"status": "Return", "paid": 0, "outstanding": 0,
                "grand_total": gt, "label": "Return / Credit Note", "color": "orange"}
    if ost <= 0.005:
        return {"status": "Paid", "paid": gt, "outstanding": 0,
                "grand_total": gt, "label": "Fully Paid \u2713", "color": "green"}
    paid = gt - ost
    if paid > 0.005:
        pct = round((paid / gt) * 100, 1) if gt else 0
        return {"status": "Partly Paid", "paid": paid, "outstanding": ost,
                "grand_total": gt, "label": "Partly Paid ({0}%)".format(pct), "color": "yellow"}
    if si.due_date and getdate(str(si.due_date)) < getdate(today()):
        days = date_diff(today(), str(si.due_date))
        return {"status": "Overdue", "paid": 0, "outstanding": ost,
                "grand_total": gt, "label": "Overdue {0}d".format(days), "color": "red"}
    return {"status": "Unpaid", "paid": 0, "outstanding": ost,
            "grand_total": gt, "label": "Unpaid", "color": "orange"}


# ─────────────────────────────────────────────────────────────────────────────
# POST ROOM CHARGE + INVOICE ATOMICALLY
# ─────────────────────────────────────────────────────────────────────────────

def _get_folio_accounts(folio):
    """Get company, income and debtors accounts for a folio."""
    prop = None
    if folio.property:
        prop = frappe.db.get_value("Property", folio.property,
            ["company", "income_account", "debtors_account", "default_tax_template"],
            as_dict=True)
    company = (prop.company if prop else None) or frappe.defaults.get_defaults().get("company")
    income_acct = (getattr(prop, "income_account", None) if prop else None) or _default_income(company)
    debtors_acct = (getattr(prop, "debtors_account", None) if prop else None) or _default_debtors(company)
    tax_template = getattr(prop, "default_tax_template", None) if prop else None
    return company, income_acct, debtors_acct, tax_template


def post_room_charge_with_invoice(folio_name, stay_name, charge_date, rate, room, guest_stay_ref=None):
    """
    Atomic: creates BOTH a folio charge line AND a submitted Sales Invoice for one night.
    Returns the SI name or None if already posted.
    """
    # Dedup check
    if _room_charge_exists_for_date(folio_name, stay_name, charge_date):
        return None

    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.folio_status != "Open" or folio.docstatus != 1:
        return None

    invoice_to = folio.billing_customer or folio.customer
    if not invoice_to:
        frappe.log_error("No customer on folio {0}".format(folio_name), "Room Charge Error")
        return None

    company, income_acct, debtors_acct, tax_template = _get_folio_accounts(folio)

    # 1. Create Sales Invoice
    si = frappe.new_doc("Sales Invoice")
    si.customer = invoice_to
    si.company = company
    si.posting_date = str(charge_date)
    si.due_date = str(charge_date)
    si.debit_to = debtors_acct
    si.hotel_folio = folio_name
    si.hotel_stay = stay_name
    si.hotel_room = room
    si.hotel_billing_instruction = "Folio Invoice"
    si.remarks = "Room Charge - Room {0} - {1}".format(room, charge_date)

    ic = _get_item("Room Rate")
    uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
    r = si.append("items", {})
    r.item_code = ic
    r.item_name = "Room Charge - {0} - {1}".format(room, charge_date)
    r.description = r.item_name
    r.qty = 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
    r.rate = flt(rate); r.amount = flt(rate)
    r.income_account = income_acct

    if tax_template:
        si.taxes_and_charges = tax_template

    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)
    si.submit()

    # 2. Create folio charge line (already billed, linked to SI)
    folio.reload()  # Reload to avoid stale doc
    line = folio.append("folio_charges", {})
    line.description = "Room Charge - {0} - {1}".format(room, charge_date)
    line.qty = 1; line.rate = flt(rate); line.amount = flt(rate)
    line.charge_category = "Room Rate"
    line.posting_date = str(charge_date)
    line.posting_time = nowtime()
    line.reference_doctype = "Sales Invoice"
    line.reference_name = si.name
    line.posted_by = frappe.session.user or "Administrator"
    line.is_read_only = 1
    line.guest_stay = stay_name
    line.is_billed = 1
    folio.save(ignore_permissions=True)

    return si.name


@frappe.whitelist()
def post_all_room_charges(guest_stay_name):
    """
    Hotel Manager action: post room charges from check-in to today.
    Each day gets a charge line + submitted Sales Invoice atomically.
    No future charges allowed.
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("Only Hotel Manager can post room charges."))

    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    if stay.stay_status != "Checked In":
        frappe.throw(_("Stay must be Checked In."))
    if not stay.guest_folio:
        frappe.throw(_("No folio linked to this stay."))

    rate = flt(stay.nightly_rate) or flt(
        frappe.db.get_value("Room Type", stay.room_type, "bar_rate") or 0)
    if not rate:
        frappe.throw(_("No nightly rate set."))

    # Charge from arrival to today (inclusive), never future
    today_date = getdate(today())
    departure = getdate(stay.departure_date) if stay.departure_date else today_date
    end_date = min(today_date, departure)

    posted = 0; skipped = 0
    cur = getdate(stay.arrival_date)
    while cur < end_date:
        ds = str(cur)
        si = post_room_charge_with_invoice(
            stay.guest_folio, stay.name, ds, rate, stay.room)
        if si:
            posted += 1
        else:
            skipped += 1
        cur = add_days(cur, 1)

    return {
        "posted": posted, "skipped": skipped,
        "total_amount": rate * posted,
        "message": _("{0} night(s) charged with invoices. {1} already existed.").format(
            posted, skipped)
    }


@frappe.whitelist()
def calculate_room_charges_for_stay(guest_stay_name):
    """Preview room charges — no future dates."""
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    if not stay.arrival_date or not stay.departure_date:
        frappe.throw(_("Stay needs arrival and departure dates."))
    rate = flt(stay.nightly_rate) or flt(
        frappe.db.get_value("Room Type", stay.room_type, "bar_rate") or 0)

    posted_dates = set()
    if stay.guest_folio:
        rows = frappe.db.get_all("Folio Charge Line",
            {"parent": stay.guest_folio, "charge_category": "Room Rate",
             "reference_name": ["like", "%"], "is_void": 0,
             "guest_stay": guest_stay_name}, ["posting_date"])
        posted_dates = {str(r.posting_date) for r in rows}

    charges = []
    today_date = getdate(today())
    departure = getdate(stay.departure_date)
    end_date = min(today_date, departure)
    cur = getdate(stay.arrival_date)
    while cur < end_date:
        ds = str(cur)
        charges.append({"date": ds,
                        "description": "Room Charge - {0} - {1}".format(stay.room, ds),
                        "amount": rate, "already_posted": ds in posted_dates})
        cur = add_days(cur, 1)

    total_nights = len(charges)
    posted_count = len([c for c in charges if c["already_posted"]])
    pending = total_nights - posted_count
    return {"charges": charges, "total": rate * total_nights, "nights": total_nights,
            "nightly_rate": rate, "pending_count": pending,
            "already_posted_count": posted_count, "pending_amount": rate * pending,
            "room": stay.room, "guest_name": stay.guest_name}


# ─────────────────────────────────────────────────────────────────────────────
# DAILY 15:00 SCHEDULER — auto room charges with invoices
# ─────────────────────────────────────────────────────────────────────────────

def auto_daily_room_charge():
    """
    Scheduler: runs at 15:00 daily. For each checked-in stay, posts today's
    room charge + creates a submitted Sales Invoice. Idempotent.
    """
    charge_date = today()
    stays = frappe.get_all("Guest Stay",
        {"stay_status": "Checked In", "docstatus": 1,
         "arrival_date": ["<=", charge_date],
         "departure_date": [">", charge_date]},
        ["name", "guest_folio", "room", "room_type", "nightly_rate"])

    posted = 0
    for s in stays:
        if not s.guest_folio:
            continue
        rate = flt(s.nightly_rate) or flt(
            frappe.db.get_value("Room Type", s.room_type, "bar_rate") or 0)
        if not rate:
            continue
        try:
            si = post_room_charge_with_invoice(
                s.guest_folio, s.name, charge_date, rate, s.room)
            if si:
                posted += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                "Auto Room Charge Error: {0}".format(s.name))

    if posted:
        frappe.logger("dagaarsoft_hospitality").info(
            "Daily 15:00 room charges: {0} invoices created".format(posted))


# ─────────────────────────────────────────────────────────────────────────────
# HOURLY — auto-invoice pending non-restaurant services
# ─────────────────────────────────────────────────────────────────────────────

_RESTAURANT_CATEGORIES = ("Restaurant", "F&B")

def auto_invoice_pending_services():
    """
    Hourly: For open folios with unbilled non-restaurant charges
    (laundry, minibar, spa, transport, etc.), create a supplementary SI.
    Restaurant charges are excluded — those come from POS.
    """
    folios = frappe.db.sql("""
        SELECT DISTINCT gf.name
        FROM `tabGuest Folio` gf
        JOIN `tabFolio Charge Line` fcl ON fcl.parent = gf.name
        WHERE gf.folio_status = 'Open'
          AND gf.docstatus = 1
          AND fcl.is_void = 0
          AND fcl.is_billed = 0
          AND fcl.charge_category NOT IN ('Restaurant', 'F&B', 'Room Rate',
              'Room Rate Adjustment', 'Room Rate Credit')
    """, as_list=True)

    count = 0
    for row in folios:
        folio_name = row[0]
        try:
            si = _create_service_invoice(folio_name)
            if si:
                count += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                "Auto Service Invoice Error: {0}".format(folio_name))

    if count:
        frappe.logger("dagaarsoft_hospitality").info(
            "Hourly service invoices: {0} created".format(count))


def _create_service_invoice(folio_name):
    """Create SI for unbilled non-restaurant, non-room-rate charges."""
    folio = frappe.get_doc("Guest Folio", folio_name)
    unbilled = [c for c in (folio.get("folio_charges") or [])
                if not c.is_void and not c.is_billed
                and c.charge_category not in ("Restaurant", "F&B", "Room Rate",
                    "Room Rate Adjustment", "Room Rate Credit")]
    if not unbilled:
        return None

    # Mark as billed first (idempotency)
    for c in unbilled:
        frappe.db.set_value("Folio Charge Line", c.name, "is_billed", 1)
    frappe.db.commit()

    invoice_to = folio.billing_customer or folio.customer
    if not invoice_to:
        return None

    company, income_acct, debtors_acct, tax_template = _get_folio_accounts(folio)

    si = frappe.new_doc("Sales Invoice")
    si.customer = invoice_to
    si.company = company
    si.posting_date = today()
    si.due_date = today()
    si.debit_to = debtors_acct
    si.hotel_folio = folio_name
    si.hotel_stay = folio.guest_stay
    si.hotel_room = folio.room
    si.hotel_billing_instruction = "Folio Invoice"
    si.remarks = "Hotel Services - Folio: {0}".format(folio_name)

    for c in unbilled:
        ic = _get_item(c.charge_category)
        uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
        r = si.append("items", {})
        r.item_code = ic
        r.item_name = r.description = c.description or c.charge_category
        r.qty = flt(c.qty) or 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
        r.rate = flt(c.rate) or flt(c.amount); r.amount = flt(c.amount)
        r.income_account = income_acct

    if tax_template:
        si.taxes_and_charges = tax_template

    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)
    si.submit()

    return si.name


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED GENERATE INVOICE (replaces Generate Invoice + Bill Pending)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def generate_folio_invoice(folio_name, discount_pct=0, discount_amount=0):
    """
    Hotel Manager action: Generate a Sales Invoice for ALL unbilled charges.
    This replaces both 'Generate Invoice' and 'Bill Pending' — one button.
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("Only Hotel Manager can generate invoices."))

    folio = frappe.get_doc("Guest Folio", folio_name)
    if folio.folio_status != "Open" or folio.docstatus != 1:
        frappe.throw(_("Folio must be Open and submitted."))

    unbilled = [c for c in (folio.get("folio_charges") or [])
                if not c.is_void and not c.is_billed]
    if not unbilled:
        frappe.throw(_("No unbilled charges on this folio."))

    invoice_to = folio.billing_customer or folio.customer
    if not invoice_to:
        frappe.throw(_("No customer linked to folio."))

    company, income_acct, debtors_acct, tax_template = _get_folio_accounts(folio)

    # Discount validation
    if flt(discount_pct) > 0 or flt(discount_amount) > 0:
        prop = frappe.db.get_value("Property", folio.property,
            ["allow_discount", "discount_role", "max_discount_pct"], as_dict=True) if folio.property else None
        if prop and not prop.allow_discount:
            frappe.throw(_("Discounts not allowed for this property."))
        if prop and prop.discount_role and prop.discount_role not in frappe.get_roles():
            frappe.throw(_("Only '{0}' role can apply discounts.").format(prop.discount_role))
        if prop and prop.max_discount_pct and flt(discount_pct) > flt(prop.max_discount_pct):
            frappe.throw(_("Max discount is {0}%.").format(prop.max_discount_pct))

    # Mark all as billed first (idempotency)
    for c in unbilled:
        frappe.db.set_value("Folio Charge Line", c.name, "is_billed", 1)
    frappe.db.commit()

    si = frappe.new_doc("Sales Invoice")
    si.customer = invoice_to
    si.company = company
    si.posting_date = today()
    si.due_date = today()
    si.debit_to = debtors_acct
    si.hotel_folio = folio_name
    si.hotel_stay = folio.guest_stay
    si.hotel_room = folio.room
    si.hotel_billing_instruction = "Folio Invoice"

    gname = frappe.db.get_value("Customer", folio.customer, "customer_name") or folio.customer
    si.remarks = "Folio: {0} | Stay: {1} | Room: {2} | Guest: {3}".format(
        folio_name, folio.guest_stay or "", folio.room or "", gname)

    # Group room charges
    room_charges = [c for c in unbilled if c.charge_category in
                    ("Room Rate", "Room Rate Adjustment", "Room Rate Credit")]
    other_charges = [c for c in unbilled if c not in room_charges]

    if room_charges:
        total_room = sum(flt(c.amount) for c in room_charges)
        nights = len([c for c in room_charges if c.charge_category == "Room Rate"])
        rate = flt(folio.nightly_rate) or (total_room / nights if nights else 0)
        ic = _get_item("Room Rate")
        uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
        r = si.append("items", {})
        r.item_code = ic
        r.item_name = r.description = "Room Charges - {0} night(s)".format(nights or 1)
        r.qty = nights or 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
        r.rate = rate; r.amount = total_room
        r.income_account = income_acct

    for c in other_charges:
        ic = _get_item(c.charge_category)
        uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
        r = si.append("items", {})
        r.item_code = ic
        r.item_name = r.description = c.description or c.charge_category
        r.qty = flt(c.qty) or 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
        r.rate = flt(c.rate) or flt(c.amount); r.amount = flt(c.amount)
        r.income_account = income_acct

    if flt(discount_pct) > 0:
        si.additional_discount_percentage = flt(discount_pct)
        si.apply_discount_on = "Grand Total"
    elif flt(discount_amount) > 0:
        si.discount_amount = flt(discount_amount)
        si.apply_discount_on = "Grand Total"

    if tax_template:
        si.taxes_and_charges = tax_template

    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)
    si.submit()

    # Update folio reference
    if not folio.sales_invoice:
        frappe.db.set_value("Guest Folio", folio_name, {
            "sales_invoice": si.name,
            "sales_invoice_status": si.status
        }, update_modified=False)

    return si.name


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENTS
# ─────────────────────────────────────────────────────────────────────────────

def apply_payment_to_invoice(si_name, amount, payment_mode="Cash",
                              reference_number=None, company=None):
    si = frappe.get_doc("Sales Invoice", si_name)
    co = si.company or company
    ost = flt(si.outstanding_amount)
    amt = flt(amount)
    if amt > ost + 0.005:
        frappe.throw(_("Payment {0} exceeds outstanding {1}.").format(
            frappe.format_value(amt, {"fieldtype": "Currency"}),
            frappe.format_value(ost, {"fieldtype": "Currency"})))
    paid_to = (
        frappe.db.get_value("Mode of Payment Account",
            {"parent": payment_mode, "company": co}, "default_account") or
        frappe.db.get_value("Account", {"company": co, "account_type": "Cash", "is_group": 0}, "name")
    )
    paid_from = frappe.db.get_value("Account",
        {"company": co, "account_type": "Receivable", "is_group": 0}, "name")
    pe = frappe.new_doc("Payment Entry")
    pe.hotel_folio = getattr(si, "hotel_folio", None)
    pe.hotel_stay = getattr(si, "hotel_stay", None)
    pe.hotel_room = getattr(si, "hotel_room", None)
    pe.payment_type = "Receive"; pe.party_type = "Customer"; pe.party = si.customer
    pe.company = co; pe.posting_date = today()
    pe.paid_amount = amt; pe.received_amount = amt
    pe.reference_no = reference_number or si_name; pe.reference_date = today()
    pe.mode_of_payment = payment_mode
    pe.paid_from = paid_from; pe.paid_to = paid_to
    ref = pe.append("references", {})
    ref.reference_doctype = "Sales Invoice"
    ref.reference_name = si_name
    ref.allocated_amount = amt
    pe.set_missing_values(); pe.insert(ignore_permissions=True); pe.submit()
    return pe.name


# ─────────────────────────────────────────────────────────────────────────────
# DEPOSIT RETURN
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def return_excess_deposit(folio_name, amount, payment_mode="Cash", reference_number=None):
    """
    Return excess deposit to guest via a Journal Entry.
    Debit: Cash/Bank (money going out)
    Credit: Receivable (reduce what guest has paid in advance)
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("Only Hotel Manager can process deposit returns."))

    folio = frappe.get_doc("Guest Folio", folio_name)
    amt = flt(amount)
    if amt <= 0:
        frappe.throw(_("Amount must be greater than zero."))

    customer = folio.billing_customer or folio.customer
    company, income_acct, debtors_acct, _tax_tpl = _get_folio_accounts(folio)

    # Get cash/bank account for the payment mode
    cash_acct = (
        frappe.db.get_value("Mode of Payment Account",
            {"parent": payment_mode, "company": company}, "default_account") or
        frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name")
    )
    if not cash_acct or not debtors_acct:
        frappe.throw(_("Cannot find Cash or Receivable accounts."))

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = today()
    je.user_remark = "Deposit Return | Folio: {0} | Customer: {1} | Ref: {2}".format(
        folio_name, customer, reference_number or "")

    # Debit Cash (money leaving)
    je.append("accounts", {
        "account": cash_acct,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": amt,
    })
    # Credit Receivable (reduce advance)
    je.append("accounts", {
        "account": debtors_acct,
        "party_type": "Customer",
        "party": customer,
        "debit_in_account_currency": amt,
        "credit_in_account_currency": 0,
    })

    je.insert(ignore_permissions=True)
    je.submit()

    frappe.msgprint(
        _("Deposit return JE {0} created for {1}.").format(
            je.name, frappe.format_value(amt, {"fieldtype": "Currency"})),
        alert=True)
    return {"journal_entry": je.name, "amount": amt}


# ─────────────────────────────────────────────────────────────────────────────
# CHECKOUT VALIDATION — charges = invoices = payments
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def validate_checkout_billing(guest_stay_name, force_checkout=False):
    """
    Strict checkout:
      1. All charges must be billed (is_billed=1)
      2. All Sales Invoices must be fully paid (outstanding=0)
      3. If guest has excess deposit → block checkout, return deposit first
    Exceptions: Sponsored stays pass with warnings.
    """
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    folio_name = stay.guest_folio
    issues, warnings = [], []

    if not folio_name:
        return {"can_checkout": False, "issues": ["No folio linked."], "warnings": [],
                "is_early_checkout": False, "is_sponsored": False}

    folio = frappe.get_doc("Guest Folio", folio_name)
    billing_instr = folio.billing_instruction or stay.billing_instruction or ""

    is_sponsored = bool(
        folio.billing_customer and folio.billing_customer != folio.customer or
        billing_instr in ["Charge to Company", "Charge to Travel Agent", "Split Bill"]
    )

    is_early_checkout = (stay.departure_date and
                         getdate(str(stay.departure_date)) > getdate(today()))
    remaining_nights = date_diff(str(stay.departure_date), today()) if is_early_checkout else 0

    # ── The three pillars ─────────────────────────────────────────────────
    # 1. Charges
    total_charges = sum(flt(c.amount) for c in (folio.get("folio_charges") or [])
                        if not c.is_void)
    unbilled = [c for c in (folio.get("folio_charges") or [])
                if not c.is_void and not c.is_billed]
    unbilled_total = sum(flt(c.amount) for c in unbilled)

    # 2. Invoices (submitted, linked to this folio)
    all_sis = frappe.db.sql("""
        SELECT name, grand_total, outstanding_amount, is_return, docstatus
        FROM `tabSales Invoice`
        WHERE hotel_folio = %s AND docstatus = 1
    """, folio_name, as_dict=True)
    total_invoiced = sum(flt(si.grand_total) for si in all_sis if not si.is_return)
    total_credit_notes = sum(abs(flt(si.grand_total)) for si in all_sis if si.is_return)
    total_outstanding = sum(flt(si.outstanding_amount) for si in all_sis if not si.is_return)

    # 3. Payments
    total_paid = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(pe.paid_amount), 0)
        FROM `tabPayment Entry` pe
        WHERE pe.hotel_folio = %s AND pe.docstatus = 1
    """, folio_name)[0][0])

    # JEs (charge-to-credit)
    total_je = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(jea.debit_in_account_currency), 0)
        FROM `tabJournal Entry Account` jea
        JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE je.docstatus = 1 AND jea.party_type = 'Customer'
        AND jea.party = %s AND je.user_remark LIKE %s
    """, (folio.billing_customer or folio.customer,
          "%Folio: {0}%".format(folio_name)))[0][0])

    effective_paid = total_paid + total_je
    force = bool(int(force_checkout))

    if is_sponsored:
        if total_outstanding > 0.01:
            warnings.append(_("Outstanding {0} — billed to {1}.").format(
                frappe.format_value(total_outstanding, {"fieldtype": "Currency"}),
                folio.billing_customer or "Sponsor"))
        if unbilled:
            warnings.append(_("{0} unbilled charge(s) for sponsor.").format(len(unbilled)))
    else:
        # Check 1: All charges invoiced
        if unbilled and not force:
            issues.append(_("{0} charge(s) ({1}) not invoiced. Use 'Generate Invoice' first.").format(
                len(unbilled),
                frappe.format_value(unbilled_total, {"fieldtype": "Currency"})))

        # Check 2: All invoices paid
        if total_outstanding > 0.01 and not force:
            issues.append(_("Unpaid invoices: {0}. Settle payment or use 'Charge to Credit'.").format(
                frappe.format_value(total_outstanding, {"fieldtype": "Currency"})))

        # Check 3: Excess deposit — must return first
        if effective_paid > total_invoiced + 0.01 and total_invoiced > 0:
            excess = effective_paid - total_invoiced
            issues.append(_("Guest has excess deposit of {0}. Use 'Return Deposit' before checkout.").format(
                frappe.format_value(excess, {"fieldtype": "Currency"})))

    balance_due = flt(folio.balance_due)
    if balance_due < -0.005:
        warnings.append(_("Overpaid by {0}.").format(
            frappe.format_value(abs(balance_due), {"fieldtype": "Currency"})))

    early_checkout_info = None
    if is_early_checkout and remaining_nights > 0:
        nightly = flt(stay.nightly_rate)
        early_checkout_info = {
            "remaining_nights": remaining_nights,
            "nightly_rate": nightly,
            "potential_credit": nightly * remaining_nights,
            "message": _("Early checkout: {0} night(s) remain.").format(remaining_nights)
        }

    return {
        "can_checkout": len(issues) == 0,
        "is_sponsored": is_sponsored,
        "is_early_checkout": is_early_checkout,
        "early_checkout_info": early_checkout_info,
        "issues": issues, "warnings": warnings,
        "balance_due": balance_due,
        "total_charges": total_charges,
        "total_invoiced": total_invoiced,
        "total_paid": effective_paid,
        "total_outstanding": total_outstanding,
        "invoice_status": get_invoice_billing_status(folio.sales_invoice)
                          if folio.sales_invoice else None
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHARGE TO CREDIT — uses real ERPNext outstanding
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def charge_to_credit(folio_name, reason=""):
    """
    Hotel Manager: allow checkout with unpaid balance.
    Reads REAL outstanding from all submitted SIs linked to this folio.
    Creates JE: Debit Receivable (customer owes), Credit Income (cash stays accurate).
    """
    if "Hotel Manager" not in frappe.get_roles():
        frappe.throw(_("Only Hotel Manager can authorize charge-to-credit."))

    folio = frappe.get_doc("Guest Folio", folio_name)

    # Get REAL outstanding from ERPNext Sales Invoices
    all_sis = frappe.db.sql("""
        SELECT name, outstanding_amount
        FROM `tabSales Invoice`
        WHERE hotel_folio = %s AND docstatus = 1 AND is_return = 0
    """, folio_name, as_dict=True)

    total_outstanding = sum(flt(si.outstanding_amount) for si in all_sis)
    if total_outstanding <= 0.005:
        frappe.throw(_("No outstanding balance on invoices linked to this folio."))

    customer = folio.billing_customer or folio.customer
    company, income_acct, debtors_acct, _tax_tpl = _get_folio_accounts(folio)

    if not debtors_acct or not income_acct:
        frappe.throw(_("Cannot find Receivable or Income accounts for company."))

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = today()
    je.user_remark = "Charge to Credit | Folio: {0} | Customer: {1} | Amount: {2} | Reason: {3}".format(
        folio_name, customer, total_outstanding, reason or "Manager authorized")

    je.append("accounts", {
        "account": debtors_acct,
        "party_type": "Customer",
        "party": customer,
        "debit_in_account_currency": flt(total_outstanding),
        "credit_in_account_currency": 0,
    })
    je.append("accounts", {
        "account": income_acct,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": flt(total_outstanding),
    })

    je.insert(ignore_permissions=True)
    je.submit()

    frappe.msgprint(
        _("JE {0}: {1} charged to credit for {2}.").format(
            je.name,
            frappe.format_value(total_outstanding, {"fieldtype": "Currency"}),
            customer),
        alert=True)
    return {"journal_entry": je.name, "amount": total_outstanding}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _default_income(company):
    return (
        frappe.db.get_value("Account",
            {"company": company, "account_type": "Income Account",
             "is_group": 0, "disabled": 0}, "name") or
        frappe.db.get_value("Account",
            {"company": company, "root_type": "Income", "is_group": 0}, "name")
    )

def _default_debtors(company):
    return frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")

def _get_item(category):
    item_name = "Hotel - {0}".format(category)
    if frappe.db.exists("Item", item_name):
        if not frappe.db.get_value("Item", item_name, "stock_uom"):
            frappe.db.set_value("Item", item_name, "stock_uom", "Nos")
        return item_name
    if not frappe.db.exists("UOM", "Nos"):
        frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
    item = frappe.new_doc("Item")
    item.item_code = item_name; item.item_name = item_name
    item.item_group = _get_item_group("Hotel Services")
    item.is_stock_item = 0; item.stock_uom = "Nos"
    item.include_item_in_manufacturing = 0
    item.insert(ignore_permissions=True)
    return item_name

def _get_item_group(name):
    if frappe.db.exists("Item Group", name):
        return name
    frappe.get_doc({"doctype": "Item Group", "item_group_name": name,
                    "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
    return name


def _register_folio_si(folio_name, si_name):
    key = "folio_si_{0}".format(folio_name)
    existing = frappe.cache().get_value(key) or []
    if si_name not in existing:
        existing.append(si_name)
    frappe.cache().set_value(key, existing, expires_in_sec=3600)


def is_folio_generated_si(folio_name, si_name):
    primary = frappe.db.get_value("Guest Folio", folio_name, "sales_invoice")
    if primary == si_name:
        return True
    key = "folio_si_{0}".format(folio_name)
    cached = frappe.cache().get_value(key) or []
    return si_name in cached
