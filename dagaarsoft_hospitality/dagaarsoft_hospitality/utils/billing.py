import frappe
from frappe import _
from frappe.utils import flt, today, date_diff, getdate, add_days, nowtime


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _charge_exists(folio_name, reference_doctype, reference_name):
    """FIX 5+6: Universal dedup check - never post the same reference twice."""
    return frappe.db.exists("Folio Charge Line", {
        "parent": folio_name,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "is_void": 0
    })


def _room_charge_exists_for_date(folio_name, stay_name, posting_date):
    """FIX 5: Check if room charge already posted for this specific date."""
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
# SALES INVOICE CREATION FROM FOLIO
# ─────────────────────────────────────────────────────────────────────────────

def create_sales_invoice_from_folio(folio_name, submit=False, discount_pct=0,
                                     discount_amount=0, bill_to_override=None):
    folio = frappe.get_doc("Guest Folio", folio_name)

    # FIX 5: Prevent duplicate invoices for same folio
    if folio.sales_invoice and frappe.db.exists("Sales Invoice", folio.sales_invoice):
        si_status = frappe.db.get_value("Sales Invoice", folio.sales_invoice, "docstatus")
        if si_status in (0, 1):
            frappe.throw(_("Invoice {0} already exists for this Folio. Cancel it first.").format(
                folio.sales_invoice))

    invoice_to = bill_to_override or folio.billing_customer or folio.customer
    if not invoice_to:
        frappe.throw(_("Folio has no Customer linked."))

    prop = None
    if folio.property:
        prop = frappe.db.get_value("Property", folio.property,
            ["company", "income_account", "debtors_account",
             "default_tax_template", "allow_discount", "discount_role", "max_discount_pct"],
            as_dict=True)
    company = (prop.company if prop else None) or frappe.defaults.get_defaults().get("company")
    income_acct  = (getattr(prop, "income_account",  None) if prop else None) or _default_income(company)
    debtors_acct = (getattr(prop, "debtors_account", None) if prop else None) or _default_debtors(company)

    if flt(discount_pct) > 0 or flt(discount_amount) > 0:
        if prop and not prop.allow_discount:
            frappe.throw(_("Discounts not allowed for this property."))
        if prop and prop.discount_role and prop.discount_role not in frappe.get_roles():
            frappe.throw(_("Only '{0}' role can apply discounts.").format(prop.discount_role))
        if prop and prop.max_discount_pct and flt(discount_pct) > flt(prop.max_discount_pct):
            frappe.throw(_("Max discount is {0}%.").format(prop.max_discount_pct))

    si = frappe.new_doc("Sales Invoice")
    si.customer     = invoice_to
    si.company      = company
    si.posting_date = today()
    si.due_date     = today()
    si.debit_to     = debtors_acct
    gname = frappe.db.get_value("Customer", folio.customer, "customer_name") or folio.customer
    bname = frappe.db.get_value("Customer", invoice_to,    "customer_name") or invoice_to
    si.remarks = "Folio: {0} | Stay: {1} | Room: {2} | Guest: {3}{4}".format(
        folio_name, folio.guest_stay or "", folio.room or "", gname,
        " | Bill To: {0}".format(bname) if invoice_to != folio.customer else "")
    si.hotel_folio = folio_name
    si.hotel_stay  = folio.guest_stay
    si.hotel_room  = folio.room

    # FIX 5: Collect ONLY unbilled, non-void charges
    room_charges, other_charges = [], []
    for c in (folio.get("folio_charges") or []):
        if c.is_void or c.is_billed:
            continue
        if c.charge_category in ("Room Rate", "Room Rate Adjustment", "Room Rate Credit"):
            room_charges.append(c)
        else:
            other_charges.append(c)

    if room_charges:
        total_room = sum(flt(c.amount) for c in room_charges)
        nights = len([c for c in room_charges if c.charge_category == "Room Rate"])
        dates  = sorted({str(c.posting_date) for c in room_charges if c.posting_date})
        dr     = ("{0} to {1}".format(dates[0], dates[-1]) if len(dates) > 1
                  else (dates[0] if dates else ""))
        rate   = flt(folio.nightly_rate) or (total_room / nights if nights else 0)
        desc   = "Room Charge - Room {0} - {1} night(s): {2}".format(folio.room, nights, dr)
        ic  = _get_item("Room Rate")
        uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
        r = si.append("items", {})
        r.item_code = ic; r.item_name = desc; r.description = desc
        r.qty = nights or 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
        r.rate = rate; r.amount = total_room; r.income_account = income_acct

    for c in other_charges:
        ic  = _get_item(c.charge_category)
        uom = frappe.db.get_value("Item", ic, "stock_uom") or "Nos"
        r = si.append("items", {})
        r.item_code = ic
        r.item_name = r.description = c.description or c.charge_category
        r.qty = flt(c.qty) or 1; r.uom = uom; r.stock_uom = uom; r.conversion_factor = 1
        r.rate = flt(c.rate) or flt(c.amount); r.amount = flt(c.amount)
        r.income_account = income_acct

    if not si.get("items"):
        frappe.throw(_("No unbilled charges on Folio {0}.").format(folio_name))

    if flt(discount_pct) > 0:
        si.additional_discount_percentage = flt(discount_pct)
        si.apply_discount_on = "Grand Total"
    elif flt(discount_amount) > 0:
        si.discount_amount = flt(discount_amount)
        si.apply_discount_on = "Grand Total"

    if prop and prop.default_tax_template:
        si.taxes_and_charges = prop.default_tax_template

    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)

    if submit:
        si.submit()
        # Mark all collected charges as billed
        for c in room_charges + other_charges:
            frappe.db.set_value("Folio Charge Line", c.name, "is_billed", 1)
        _auto_apply_deposits(invoice_to, si.name, folio)

    # FIX 11: Immediately sync folio status
    frappe.db.set_value("Guest Folio", folio_name, {
        "sales_invoice": si.name,
        "sales_invoice_status": si.status
    }, update_modified=False)
    return si.name


def _auto_apply_deposits(customer, si_name, folio):
    for dep in frappe.get_all("Hotel Deposit",
        {"customer": customer, "deposit_status": ["in", ["Received"]], "docstatus": 1},
        ["name", "deposit_amount", "applied_amount", "refund_amount"]):
        if flt(dep.deposit_amount) - flt(dep.applied_amount) - flt(dep.refund_amount) <= 0:
            continue
        try:
            apply_deposit_to_invoice(dep.name, si_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Auto Deposit Apply Error")


def apply_payment_to_invoice(si_name, amount, payment_mode="Cash",
                              reference_number=None, company=None):
    si  = frappe.get_doc("Sales Invoice", si_name)
    co  = si.company or company
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
    pe.hotel_stay  = getattr(si, "hotel_stay",  None)
    pe.hotel_room  = getattr(si, "hotel_room",  None)
    pe.payment_type = "Receive"; pe.party_type = "Customer"; pe.party = si.customer
    pe.company = co; pe.posting_date = today()
    pe.paid_amount = amt; pe.received_amount = amt
    pe.reference_no = reference_number or si_name; pe.reference_date = today()
    pe.mode_of_payment = payment_mode
    pe.paid_from = paid_from; pe.paid_to = paid_to
    ref = pe.append("references", {})
    ref.reference_doctype = "Sales Invoice"
    ref.reference_name    = si_name
    ref.allocated_amount  = amt
    pe.set_missing_values(); pe.insert(ignore_permissions=True); pe.submit()
    return pe.name


# ─────────────────────────────────────────────────────────────────────────────
# ROOM CHARGE POSTING  (FIX 5: dedup by date+stay)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def calculate_room_charges_for_stay(guest_stay_name):
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    if not stay.arrival_date or not stay.departure_date:
        frappe.throw(_("Stay needs arrival and departure dates."))
    rate = flt(stay.nightly_rate) or flt(
        frappe.db.get_value("Room Type", stay.room_type, "bar_rate") or 0)
    posted_dates = set(); posted_count = 0
    if stay.guest_folio:
        rows = frappe.db.get_all("Folio Charge Line",
            {"parent": stay.guest_folio, "charge_category": "Room Rate",
             "reference_name": guest_stay_name, "is_void": 0}, ["posting_date"])
        posted_count = len(rows)
        posted_dates = {str(r.posting_date) for r in rows}
    charges = []
    cur = getdate(stay.arrival_date); out = getdate(stay.departure_date)
    while cur < out:
        ds = str(cur)
        charges.append({"date": ds,
                        "description": "Room Charge - {0} - {1}".format(stay.room, ds),
                        "amount": rate, "already_posted": ds in posted_dates})
        cur = add_days(cur, 1)
    total_nights = len(charges)
    pending = max(total_nights - posted_count, 0)
    return {"charges": charges, "total": rate * total_nights, "nights": total_nights,
            "nightly_rate": rate, "pending_count": pending,
            "already_posted_count": posted_count, "pending_amount": rate * pending,
            "room": stay.room, "guest_name": stay.guest_name}


@frappe.whitelist()
def post_all_room_charges(guest_stay_name):
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    if not stay.guest_folio:
        frappe.throw(_("No folio linked to this stay."))
    result = calculate_room_charges_for_stay(guest_stay_name)
    if result["pending_count"] == 0:
        return {"posted": 0, "total_amount": 0,
                "message": _("All {0} night(s) already charged.").format(
                    result["already_posted_count"])}
    posted = 0
    for c in result["charges"]:
        if c["already_posted"]:
            continue
        # FIX 5: Double-check at DB level before inserting
        if _room_charge_exists_for_date(stay.guest_folio, guest_stay_name, c["date"]):
            continue
        folio = frappe.get_doc("Guest Folio", stay.guest_folio)
        if folio.folio_status != "Open":
            continue
        line = folio.append("folio_charges", {})
        line.description       = c["description"]; line.qty = 1
        line.rate              = flt(c["amount"]); line.amount = flt(c["amount"])
        line.charge_category   = "Room Rate"; line.posting_date = c["date"]
        line.posting_time      = nowtime()
        line.reference_doctype = "Guest Stay"; line.reference_name = guest_stay_name
        line.posted_by         = frappe.session.user; line.is_read_only = 1
        line.guest_stay        = guest_stay_name
        folio.save(ignore_permissions=True)
        posted += 1
    return {"posted": posted, "total_amount": result["nightly_rate"] * posted,
            "skipped": result["already_posted_count"],
            "message": _("{0} night(s) charged. {1} already existed.").format(
                posted, result["already_posted_count"])}


# ─────────────────────────────────────────────────────────────────────────────
# CHECKOUT VALIDATION  (FIX 8+9)
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def validate_checkout_billing(guest_stay_name, force_checkout=False):
    """
    FIX 8: Allow early checkout with Hotel Manager adjustment.
    FIX 9: Sponsored (billing_customer) checkout always allowed.
    """
    stay = frappe.get_doc("Guest Stay", guest_stay_name)
    folio_name = stay.guest_folio
    issues, warnings = [], []

    if not folio_name:
        return {"can_checkout": False, "issues": ["No folio linked."], "warnings": [],
                "is_early_checkout": False, "is_sponsored": False}

    folio = frappe.get_doc("Guest Folio", folio_name)
    billing_instr = folio.billing_instruction or stay.billing_instruction or ""

    # FIX 9: Sponsored = has billing_customer different from guest
    is_sponsored = bool(
        folio.billing_customer and folio.billing_customer != folio.customer or
        billing_instr in ["Charge to Company", "Charge to Travel Agent", "Split Bill"]
    )

    # FIX 8: Early checkout detection
    from frappe.utils import getdate, today as _today
    is_early_checkout = (stay.departure_date and
                         getdate(str(stay.departure_date)) > getdate(_today()))
    remaining_nights = 0
    if is_early_checkout:
        from frappe.utils import date_diff
        remaining_nights = date_diff(str(stay.departure_date), _today())

    balance_due = flt(folio.balance_due)
    unbilled = [c for c in (folio.get("folio_charges") or [])
                if not c.is_void and not c.is_billed]

    if is_sponsored:
        # Sponsored checkout: always allowed, just warn about outstanding
        if balance_due > 0.01:
            warnings.append(_("Outstanding balance {0} — will be billed to {1}.").format(
                frappe.format_value(balance_due, {"fieldtype": "Currency"}),
                folio.billing_customer or "Sponsor"))
        if unbilled:
            warnings.append(_("{0} unbilled charge(s) will be included in sponsor invoice.").format(
                len(unbilled)))
    else:
        # Regular guest: must be settled
        if unbilled and not force_checkout:
            issues.append(_("{0} charge(s) not yet invoiced. Generate invoice first.").format(
                len(unbilled)))
        if folio.sales_invoice:
            info = get_invoice_billing_status(folio.sales_invoice)
            st = info["status"]
            if st in ("Unpaid", "Partly Paid", "Overdue") and not force_checkout:
                issues.append(_("Invoice {0} has outstanding balance: {1}").format(
                    folio.sales_invoice,
                    frappe.format_value(info["outstanding"], {"fieldtype": "Currency"})))

    if balance_due < -0.005:
        warnings.append(_("Guest OVERPAID by {0}. Refund before checkout.").format(
            frappe.format_value(abs(balance_due), {"fieldtype": "Currency"})))

    # FIX 8: Early checkout info
    early_checkout_info = None
    if is_early_checkout and remaining_nights > 0:
        nightly = flt(stay.nightly_rate)
        pre_charged = len([c for c in (folio.get("folio_charges") or [])
                           if c.charge_category == "Room Rate" and not c.is_void])
        early_checkout_info = {
            "remaining_nights": remaining_nights,
            "nightly_rate": nightly,
            "potential_credit": nightly * remaining_nights,
            "nights_already_charged": pre_charged,
            "message": _(
                "Early checkout: {0} night(s) remain. "
                "Hotel Manager can void future room charges "
                "or apply credit of {1}.").format(
                    remaining_nights,
                    frappe.format_value(nightly * remaining_nights, {"fieldtype": "Currency"}))
        }

    return {
        "can_checkout": len(issues) == 0,
        "is_sponsored": is_sponsored,
        "is_early_checkout": is_early_checkout,
        "early_checkout_info": early_checkout_info,
        "issues": issues, "warnings": warnings,
        "balance_due": balance_due,
        "invoice_status": get_invoice_billing_status(folio.sales_invoice)
                          if folio.sales_invoice else None
    }


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
