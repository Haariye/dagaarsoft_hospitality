import frappe
from frappe import _
from frappe.utils import flt, today, date_diff, getdate, add_days
from frappe.model.document import Document


class RELease(Document):

    def validate(self):
        self._validate_dates()
        self._calculate_term()
        self._validate_unit()
        if not self.company:
            self.company = frappe.defaults.get_defaults().get("company")
        if not self.currency:
            self.currency = frappe.db.get_value("Company", self.company, "default_currency")
        if not self.security_deposit and self.monthly_rent:
            unit = frappe.db.get_value("RE Unit", self.unit,
                ["deposit_months", "security_deposit_amount"], as_dict=True) if self.unit else None
            if unit and unit.security_deposit_amount:
                self.security_deposit = unit.security_deposit_amount
            elif unit and unit.deposit_months:
                self.security_deposit = flt(self.monthly_rent) * int(unit.deposit_months)
        self._build_rent_schedule()

    def _validate_dates(self):
        if self.start_date and self.end_date:
            if getdate(self.start_date) >= getdate(self.end_date):
                frappe.throw(_("End Date must be after Start Date."))

    def _calculate_term(self):
        if self.start_date and self.end_date:
            self.lease_term_months = round(date_diff(self.end_date, self.start_date) / 30.44)

    def _validate_unit(self):
        if not self.unit:
            return
        unit_status = frappe.db.get_value("RE Unit", self.unit, "status")
        if unit_status == "Occupied" and self.lease_status == "Draft":
            existing = frappe.db.exists("RE Lease", {
                "unit": self.unit,
                "lease_status": ["in", ["Active", "Expiring Soon"]],
                "docstatus": 1,
                "name": ["!=", self.name]
            })
            if existing:
                frappe.throw(_("Unit {0} already has an active lease: {1}").format(
                    self.unit, existing))

    def _build_rent_schedule(self):
        """Generate rent schedule lines — preserve already invoiced/paid lines."""
        if not self.start_date or not self.end_date or not self.monthly_rent:
            return
        existing_locked = {r.name for r in (self.get("rent_schedule") or [])
                           if r.status in ("Paid", "Invoiced", "Overdue")}
        if existing_locked:
            return  # Don't rebuild if any locked lines exist
        self.set("rent_schedule", [])
        cur = getdate(self.start_date)
        end = getdate(self.end_date)
        period = 1
        due_day = int(self.rent_day_of_month or 1)
        from dateutil.relativedelta import relativedelta
        while cur < end:
            due = cur.replace(day=min(due_day, 28))
            self.append("rent_schedule", {
                "period":   cur.strftime("%B %Y"),
                "due_date": str(due),
                "amount":   flt(self.monthly_rent),
                "status":   "Pending",
            })
            cur = cur + relativedelta(months=1)
            period += 1
            if period > 360:
                break

    def on_submit(self):
        self.db_set("lease_status", "Active")
        self.db_set("created_by", frappe.session.user)
        self.db_set("confirmed_on", frappe.utils.now_datetime())
        frappe.db.set_value("RE Unit", self.unit, {
            "status": "Occupied",
            "current_tenant": self.tenant,
            "current_lease": self.name,
        })
        frappe.msgprint(_("Lease {0} activated for Unit {1}.").format(
            self.name, self.unit), alert=True)

    def on_cancel(self):
        self.db_set("lease_status", "Terminated")
        self.db_set("cancelled_by", frappe.session.user)
        frappe.db.set_value("RE Unit", self.unit, {
            "status": "Vacant - Cleaning",
            "current_tenant": "",
            "current_lease": "",
        })


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()


def _has_custom_field(doctype, fieldname):
    """Check if a custom field actually exists as a DB column."""
    try:
        frappe.db.sql("SELECT `{0}` FROM `tab{1}` LIMIT 1".format(fieldname, doctype))
        return True
    except Exception:
        return False


def _si_where_clause(lease_name):
    """Build SI WHERE safely — falls back to remarks if re_lease column missing."""
    if _has_custom_field("Sales Invoice", "re_lease"):
        return "re_lease = %s AND docstatus = 1", [lease_name]
    # Fallback: match via remarks
    return "remarks LIKE %s AND docstatus = 1", ["%" + lease_name + "%"]


def _pe_where_clause(lease_name):
    """Build PE WHERE safely — falls back to remarks if re_lease column missing."""
    if _has_custom_field("Payment Entry", "re_lease"):
        return "re_lease = %s AND docstatus = 1", [lease_name]
    return "remarks LIKE %s AND docstatus = 1", ["%" + lease_name + "%"]


@frappe.whitelist()
def generate_rent_invoice(lease_name, schedule_row_name, submit_invoice=0):
    """Create a Sales Invoice for a specific rent schedule line."""
    lease = frappe.get_doc("RE Lease", lease_name)
    tenant_doc = frappe.get_doc("RE Tenant", lease.tenant)
    customer = tenant_doc.customer
    if not customer:
        frappe.throw(_("Tenant {0} has no ERPNext Customer linked. Please link a Customer first.").format(lease.tenant))

    row = None
    for r in lease.get("rent_schedule") or []:
        if r.name == schedule_row_name:
            row = r
            break
    if not row:
        frappe.throw(_("Rent schedule line not found."))
    if row.status in ("Invoiced", "Paid"):
        frappe.throw(_("Period '{0}' is already {1}.").format(row.period, row.status))

    # Check for duplicate (issue 4)
    existing_si = frappe.db.get_value("RE Rent Schedule Line", schedule_row_name, "sales_invoice")
    if existing_si and frappe.db.exists("Sales Invoice", existing_si):
        si_status = frappe.db.get_value("Sales Invoice", existing_si, "docstatus")
        if si_status in (0, 1):
            frappe.throw(_("Invoice {0} already exists for this period.").format(existing_si))

    company = lease.company or frappe.defaults.get_defaults().get("company")
    income_acct = (
        frappe.db.get_single_value("RE Settings", "rent_income_account") or
        frappe.db.get_value("Account",
            {"company": company, "account_type": "Income Account", "is_group": 0}, "name")
    )
    debtors_acct = frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
    currency = lease.currency or frappe.db.get_value("Company", company, "default_currency")

    si = frappe.new_doc("Sales Invoice")
    si.customer     = customer
    si.company      = company
    # ISSUE 3 FIX: always use today() as posting_date; due_date = today() too (not old row.due_date)
    si.posting_date = today()
    si.due_date     = today()
    si.debit_to     = debtors_acct
    si.currency     = currency
    si.remarks      = "Rent — {0} | {1} | {2}".format(lease_name, lease.unit, row.period)

    # Set custom fields if they exist
    if _has_custom_field("Sales Invoice", "re_lease"):
        si.re_lease    = lease_name
        si.re_unit     = lease.unit
        si.re_property = lease.property

    _ensure_uom("Month")
    _ensure_item_group("Real Estate")

    r_line = si.append("items", {})
    r_line.item_code         = _get_or_create_rent_item()
    r_line.item_name         = "Rent — {0} ({1})".format(lease.unit, row.period)
    r_line.description       = r_line.item_name
    r_line.qty               = 1
    r_line.uom               = "Month"
    r_line.stock_uom         = "Month"
    r_line.conversion_factor = 1
    r_line.rate              = flt(row.amount)
    r_line.amount            = flt(row.amount)
    r_line.income_account    = income_acct

    for charge in (lease.get("charges") or []):
        if charge.frequency == "Monthly":
            c = si.append("items", {})
            c.item_code         = _get_or_create_charge_item(charge.charge_type)
            c.item_name         = charge.description or charge.charge_type
            c.description       = c.item_name
            c.qty               = 1
            c.uom               = "Month"
            c.stock_uom         = "Month"
            c.conversion_factor = 1
            c.rate              = flt(charge.amount)
            c.amount            = flt(charge.amount)
            c.income_account    = charge.income_account or income_acct

    si.set_missing_values()
    si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True)

    if int(submit_invoice):
        si.submit()

    frappe.db.set_value("RE Rent Schedule Line", schedule_row_name, {
        "status": "Invoiced",
        "sales_invoice": si.name
    })
    frappe.msgprint(_("Rent Invoice {0} created for {1}.").format(si.name, row.period), alert=True)
    return si.name


@frappe.whitelist()
def receive_payment(lease_name, amount, payment_mode="Cash",
                    reference_number=None, schedule_row_name=None):
    """Create a Payment Entry for rent received."""
    lease = frappe.get_doc("RE Lease", lease_name)
    tenant_doc = frappe.get_doc("RE Tenant", lease.tenant)
    customer = tenant_doc.customer
    if not customer:
        frappe.throw(_("Tenant has no ERPNext Customer linked."))
    company = lease.company or frappe.defaults.get_defaults().get("company")

    paid_to = (
        frappe.db.get_value("Mode of Payment Account",
            {"parent": payment_mode, "company": company}, "default_account") or
        frappe.db.get_value("Account",
            {"company": company, "account_type": "Cash", "is_group": 0}, "name")
    )
    paid_from = frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")

    if not paid_to:
        frappe.throw(_("Could not find a cash/bank account for Mode of Payment: {0}. Please configure it in ERPNext.").format(payment_mode))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type    = "Receive"
    pe.party_type      = "Customer"
    pe.party           = customer
    pe.company         = company
    pe.posting_date    = today()
    pe.mode_of_payment = payment_mode
    pe.paid_from       = paid_from
    pe.paid_to         = paid_to
    pe.paid_amount     = flt(amount)
    pe.received_amount = flt(amount)
    pe.reference_no    = reference_number or lease_name
    pe.reference_date  = today()
    pe.remarks         = "Rent Payment — {0} | {1}".format(lease_name, lease.unit)

    if _has_custom_field("Payment Entry", "re_lease"):
        pe.re_lease    = lease_name
        pe.re_unit     = lease.unit
        pe.re_property = lease.property

    if schedule_row_name:
        si_name = frappe.db.get_value("RE Rent Schedule Line", schedule_row_name, "sales_invoice")
        if si_name and frappe.db.exists("Sales Invoice", si_name):
            si_doc = frappe.get_doc("Sales Invoice", si_name)
            if flt(si_doc.outstanding_amount) > 0:
                ref = pe.append("references", {})
                ref.reference_doctype = "Sales Invoice"
                ref.reference_name    = si_name
                ref.allocated_amount  = min(flt(amount), flt(si_doc.outstanding_amount))

    # HRMS override fix: EmployeePaymentEntry lacks party_account — set it manually
    debtors_acct_for_pe = frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
    if not getattr(pe, "party_account", None):
        pe.party_account = debtors_acct_for_pe
    pe.paid_from = debtors_acct_for_pe

    try:
        pe.set_missing_values()
    except AttributeError:
        pass  # HRMS EmployeePaymentEntry may lack some attrs — safe to skip

    pe.insert(ignore_permissions=True)
    pe.submit()

    if schedule_row_name:
        frappe.db.set_value("RE Rent Schedule Line", schedule_row_name, {
            "status": "Paid",
            "payment_entry": pe.name,
            "paid_date": today()
        })

    frappe.msgprint(_("Payment Entry {0} created.").format(pe.name), alert=True)
    return pe.name


def _ensure_uom(uom_name):
    if not frappe.db.exists("UOM", uom_name):
        frappe.get_doc({"doctype": "UOM", "uom_name": uom_name}).insert(ignore_permissions=True)


def _get_or_create_rent_item():
    name = "Rent - Monthly"
    if frappe.db.exists("Item", name):
        return name
    _ensure_uom("Month")
    _ensure_item_group("Real Estate")
    item = frappe.new_doc("Item")
    item.item_code = name; item.item_name = name
    item.item_group = "Real Estate"; item.is_stock_item = 0
    item.stock_uom = "Month"; item.include_item_in_manufacturing = 0
    item.insert(ignore_permissions=True)
    return name


def _get_or_create_charge_item(charge_type):
    name = "RE Charge - {0}".format(charge_type)
    if frappe.db.exists("Item", name):
        return name
    _ensure_uom("Month")
    _ensure_item_group("Real Estate")
    item = frappe.new_doc("Item")
    item.item_code = name; item.item_name = name
    item.item_group = "Real Estate"; item.is_stock_item = 0
    item.stock_uom = "Month"; item.include_item_in_manufacturing = 0
    item.insert(ignore_permissions=True)
    return name


def _ensure_item_group(name):
    if not frappe.db.exists("Item Group", name):
        frappe.get_doc({"doctype": "Item Group", "item_group_name": name,
                        "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)


@frappe.whitelist()
def make_renewal(source_name, new_end_date, new_rent=None):
    """Create a renewal lease from existing lease."""
    src = frappe.get_doc("RE Lease", source_name)
    new_lease = frappe.new_doc("RE Lease")
    new_lease.property           = src.property
    new_lease.unit               = src.unit
    new_lease.tenant             = src.tenant
    new_lease.owner              = src.owner
    new_lease.company            = src.company
    new_lease.currency           = src.currency
    new_lease.start_date         = src.end_date
    new_lease.end_date           = new_end_date
    new_lease.monthly_rent       = flt(new_rent) if new_rent else flt(src.monthly_rent)
    new_lease.security_deposit   = flt(src.security_deposit)
    new_lease.rent_includes_utility = src.rent_includes_utility
    new_lease.rent_day_of_month  = src.rent_day_of_month
    new_lease.grace_period_days  = src.grace_period_days
    new_lease.notice_period_days = src.notice_period_days
    new_lease.auto_generate_invoices = src.auto_generate_invoices
    new_lease.renewal_reminder_days  = src.renewal_reminder_days
    for c in (src.get("charges") or []):
        new_lease.append("charges", {
            "charge_type": c.charge_type,
            "description": c.description,
            "amount":      flt(new_rent) / flt(src.monthly_rent) * flt(c.amount)
                           if new_rent and src.monthly_rent else flt(c.amount),
            "frequency":   c.frequency,
        })
    new_lease.insert(ignore_permissions=True)
    frappe.db.set_value("RE Lease", source_name, "lease_status", "Renewed")
    return new_lease.name
