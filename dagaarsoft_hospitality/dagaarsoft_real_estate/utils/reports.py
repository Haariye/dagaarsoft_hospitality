import frappe
from frappe import _
from frappe.utils import flt, today


def _has_col(doctype, fieldname):
    """Check if a DB column exists — handles missing custom fields gracefully."""
    try:
        frappe.db.sql("SELECT `{0}` FROM `tab{1}` LIMIT 1".format(fieldname, doctype))
        return True
    except Exception:
        return False


def _si_filter(lease_name):
    if _has_col("Sales Invoice", "re_lease"):
        return "re_lease = %s AND docstatus = 1", [lease_name]
    return "remarks LIKE %s AND docstatus = 1", ["%" + lease_name + "%"]


def _pe_filter(lease_name):
    if _has_col("Payment Entry", "re_lease"):
        return "re_lease = %s AND docstatus = 1", [lease_name]
    return "remarks LIKE %s AND docstatus = 1", ["%" + lease_name + "%"]


@frappe.whitelist()
def get_lease_statement(lease_name):
    """Build full Debit/Credit/Balance ledger for a lease."""
    lease = frappe.get_doc("RE Lease", lease_name)
    tenant = frappe.get_doc("RE Tenant", lease.tenant)
    tenant_name = frappe.db.get_value("Customer", tenant.customer, "customer_name") \
        if tenant.customer else tenant.tenant_name

    ledger = []

    # Sales Invoices
    si_where, si_vals = _si_filter(lease_name)
    sis = frappe.db.sql("""
        SELECT name, grand_total, posting_date, status, is_return, return_against
        FROM `tabSales Invoice`
        WHERE {0}
        ORDER BY posting_date, creation
    """.format(si_where), si_vals, as_dict=True)

    for si in sis:
        gt   = abs(flt(si.grand_total))
        is_cr = bool(si.is_return)
        ledger.append({
            "date":        str(si.posting_date or ""),
            "type":        "Credit Note" if is_cr else "Sales Invoice",
            "description": si.name + (" [against {0}]".format(si.return_against) if is_cr else ""),
            "debit":       0 if is_cr else gt,
            "credit":      gt if is_cr else 0,
        })

    # Payment Entries
    pe_where, pe_vals = _pe_filter(lease_name)
    pes = frappe.db.sql("""
        SELECT name, paid_amount, posting_date, mode_of_payment, reference_no
        FROM `tabPayment Entry`
        WHERE {0}
        ORDER BY posting_date, creation
    """.format(pe_where), pe_vals, as_dict=True)

    for pe in pes:
        ledger.append({
            "date":        str(pe.posting_date or ""),
            "type":        "Payment — {0}".format(pe.mode_of_payment or ""),
            "description": pe.name + (" [{0}]".format(pe.reference_no) if pe.reference_no else ""),
            "debit":       0,
            "credit":      flt(pe.paid_amount),
        })

    # RE Deposits paid (always from RE Deposit table — no custom field needed)
    deposits = frappe.db.sql("""
        SELECT name, deposit_amount, deposit_date, deposit_type, payment_entry
        FROM `tabRE Deposit`
        WHERE lease = %s AND docstatus = 1
        ORDER BY deposit_date
    """, lease_name, as_dict=True)
    for dep in deposits:
        ledger.append({
            "date":        str(dep.deposit_date or ""),
            "type":        "Deposit — {0}".format(dep.deposit_type or ""),
            "description": dep.name + (" | PE: " + dep.payment_entry if dep.payment_entry else ""),
            "debit":       0,
            "credit":      flt(dep.deposit_amount),
        })

    ledger.sort(key=lambda x: x["date"])
    running = total_debit = total_credit = 0
    for e in ledger:
        running      += e["debit"] - e["credit"]
        total_debit  += e["debit"]
        total_credit += e["credit"]
        e["balance"]  = running

    return {
        "lease":       lease_name,
        "tenant_name": tenant_name,
        "unit":        lease.unit,
        "property":    lease.property,
        "start_date":  str(lease.start_date or ""),
        "end_date":    str(lease.end_date or ""),
        "monthly_rent": flt(lease.monthly_rent),
        "ledger":      ledger,
        "total_debit": total_debit,
        "total_credit":total_credit,
        "balance":     running,
    }


@frappe.whitelist()
def create_tenant_customer(tenant_name):
    """Create an ERPNext Customer from a RE Tenant."""
    tenant = frappe.get_doc("RE Tenant", tenant_name)
    if tenant.customer:
        return tenant.customer
    if not frappe.db.exists("Customer Group", "Real Estate Tenant"):
        frappe.get_doc({"doctype": "Customer Group",
                        "customer_group_name": "Real Estate Tenant",
                        "parent_customer_group": "All Customer Groups"}).insert(ignore_permissions=True)
    customer = frappe.new_doc("Customer")
    customer.customer_name  = tenant.tenant_name
    customer.customer_type  = "Company" if tenant.tenant_type == "Company" else "Individual"
    customer.customer_group = "Real Estate Tenant"
    customer.mobile_no      = tenant.phone
    customer.email_id       = tenant.email
    customer.insert(ignore_permissions=True)
    frappe.db.set_value("RE Tenant", tenant_name, "customer", customer.name)
    return customer.name


@frappe.whitelist()
def create_maintenance_invoice(maintenance_name):
    """Create a Sales Invoice for maintenance charged to tenant."""
    mnt = frappe.get_doc("RE Maintenance Request", maintenance_name)
    if mnt.tenant_invoice and frappe.db.exists("Sales Invoice", mnt.tenant_invoice):
        frappe.throw(_("Invoice {0} already exists for this maintenance.").format(mnt.tenant_invoice))
    lease = frappe.db.get_value("RE Unit", mnt.unit, "current_lease")
    if not lease:
        frappe.throw(_("No active lease for unit {0}.").format(mnt.unit))
    lease_doc = frappe.get_doc("RE Lease", lease)
    tenant    = frappe.get_doc("RE Tenant", lease_doc.tenant)
    if not tenant.customer:
        frappe.throw(_("Tenant has no ERPNext Customer linked."))
    company = lease_doc.company or frappe.defaults.get_defaults().get("company")
    income_acct  = frappe.db.get_value("Account",
        {"company": company, "account_type": "Income Account", "is_group": 0}, "name")
    debtors_acct = frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
    si = frappe.new_doc("Sales Invoice")
    si.customer     = tenant.customer; si.company = company
    si.posting_date = today(); si.due_date = today()
    si.debit_to     = debtors_acct
    si.remarks      = "Maintenance — {0} | {1}".format(maintenance_name, mnt.unit or "")
    if _has_col("Sales Invoice", "re_lease"):
        si.re_lease = lease; si.re_unit = mnt.unit; si.re_property = mnt.property
    from dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease import (
        _get_or_create_charge_item, _ensure_item_group)
    _ensure_item_group("Real Estate")
    r = si.append("items", {})
    r.item_code = _get_or_create_charge_item("Maintenance")
    r.item_name = r.description = "Maintenance: {0}".format(
        (mnt.description or "")[:80])
    r.qty = 1; r.uom = "Nos"; r.stock_uom = "Nos"; r.conversion_factor = 1
    r.rate = flt(mnt.actual_cost); r.amount = flt(mnt.actual_cost)
    r.income_account = income_acct
    si.set_missing_values(); si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True); si.submit()
    return si.name


@frappe.whitelist()
def create_utility_invoice(utility_name):
    """Create a Sales Invoice for a utility bill — prevents duplicates."""
    util = frappe.get_doc("RE Utility Bill", utility_name)
    # Duplicate prevention (issue 4)
    if util.sales_invoice and frappe.db.exists("Sales Invoice", util.sales_invoice):
        frappe.throw(_("Invoice {0} already exists for this utility bill.").format(util.sales_invoice))
    if util.included_in_rent:
        frappe.throw(_("This utility is included in the rent — no separate invoice needed."))

    lease_doc = frappe.get_doc("RE Lease", util.lease)
    tenant    = frappe.get_doc("RE Tenant", lease_doc.tenant)
    if not tenant.customer:
        frappe.throw(_("Tenant has no ERPNext Customer linked."))
    company = lease_doc.company or frappe.defaults.get_defaults().get("company")
    income_acct  = frappe.db.get_value("Account",
        {"company": company, "account_type": "Income Account", "is_group": 0}, "name")
    debtors_acct = frappe.db.get_value("Account",
        {"company": company, "account_type": "Receivable", "is_group": 0}, "name")
    si = frappe.new_doc("Sales Invoice")
    si.customer     = tenant.customer; si.company = company
    si.posting_date = today()
    si.due_date     = str(util.due_date) if util.due_date else today()
    si.debit_to     = debtors_acct
    si.remarks      = "Utility — {0} | {1} | {2}".format(
        util.utility_type, util.bill_period or "", util.lease)
    if _has_col("Sales Invoice", "re_lease"):
        si.re_lease    = util.lease
        si.re_unit     = util.unit
        si.re_property = frappe.db.get_value("RE Unit", util.unit, "property") if util.unit else ""
    from dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease import (
        _get_or_create_charge_item, _ensure_item_group, _ensure_uom)
    _ensure_item_group("Real Estate"); _ensure_uom("Month")
    r = si.append("items", {})
    r.item_code = _get_or_create_charge_item(util.utility_type)
    r.item_name = r.description = "{0} — {1}".format(util.utility_type, util.bill_period or "")
    r.qty = 1; r.uom = "Month"; r.stock_uom = "Month"; r.conversion_factor = 1
    r.rate = flt(util.tenant_portion); r.amount = flt(util.tenant_portion)
    r.income_account = income_acct
    si.set_missing_values(); si.calculate_taxes_and_totals()
    si.insert(ignore_permissions=True); si.submit()
    # Save invoice back to utility bill
    frappe.db.set_value("RE Utility Bill", utility_name, "sales_invoice", si.name)
    return si.name
