import frappe
from frappe import _
from frappe.utils import flt, today
from frappe.model.document import Document


def _has_col(doctype, fieldname):
    try:
        frappe.db.sql("SELECT `{0}` FROM `tab{1}` LIMIT 1".format(fieldname, doctype))
        return True
    except Exception:
        return False


class REDeposit(Document):

    def validate(self):
        if not self.tenant and self.lease:
            self.tenant = frappe.db.get_value("RE Lease", self.lease, "tenant")
        if not self.unit and self.lease:
            self.unit = frappe.db.get_value("RE Lease", self.lease, "unit")

    def on_submit(self):
        lease_doc = frappe.get_doc("RE Lease", self.lease)
        tenant    = frappe.get_doc("RE Tenant", lease_doc.tenant)
        customer  = tenant.customer
        if not customer:
            frappe.throw(_("Tenant has no ERPNext Customer linked. Cannot create Payment Entry."))
        company = lease_doc.company or frappe.defaults.get_defaults().get("company")

        paid_to = (
            frappe.db.get_value("Mode of Payment Account",
                {"parent": "Cash", "company": company}, "default_account") or
            frappe.db.get_value("Account",
                {"company": company, "account_type": "Cash", "is_group": 0}, "name")
        )
        paid_from = frappe.db.get_value("Account",
            {"company": company, "account_type": "Receivable", "is_group": 0}, "name")

        if not paid_to:
            frappe.throw(_("No Cash account found for company {0}. Please configure a Mode of Payment.").format(company))

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type    = "Receive"
        pe.party_type      = "Customer"
        pe.party           = customer
        pe.company         = company
        pe.posting_date    = today()
        pe.mode_of_payment = "Cash"
        pe.paid_from       = paid_from
        pe.paid_to         = paid_to
        pe.paid_amount     = flt(self.amount)
        pe.received_amount = flt(self.amount)
        pe.reference_no    = self.name
        pe.reference_date  = today()
        pe.remarks         = "Deposit — {0} | {1}".format(self.deposit_type or "", self.lease)

        if _has_col("Payment Entry", "re_lease"):
            pe.re_lease    = self.lease
            pe.re_unit     = self.unit
            pe.re_property = frappe.db.get_value("RE Lease", self.lease, "property") or ""

        # HRMS override fix: EmployeePaymentEntry lacks party_account
        if not getattr(pe, "party_account", None):
            pe.party_account = paid_from
        try:
            pe.set_missing_values()
        except AttributeError:
            pass

        pe.insert(ignore_permissions=True)
        pe.submit()
        self.db_set("payment_entry", pe.name)

        # Update lease deposit_paid
        total_paid = flt(frappe.db.sql(
            "SELECT SUM(amount) FROM `tabRE Deposit` WHERE lease=%s AND docstatus=1",
            self.lease)[0][0] or 0)
        security_dep = flt(frappe.db.get_value("RE Lease", self.lease, "security_deposit") or 0)
        dep_status = "Paid" if total_paid >= security_dep else "Partially Paid"
        frappe.db.set_value("RE Lease", self.lease, {
            "deposit_paid":   total_paid,
            "deposit_status": dep_status,
        }, update_modified=False)
        frappe.msgprint(_("Payment Entry {0} created for deposit.").format(pe.name), alert=True)

    def on_cancel(self):
        # Cancel the linked PE if it exists
        if self.payment_entry and frappe.db.exists("Payment Entry", self.payment_entry):
            pe_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if pe_status == 1:
                try:
                    pe = frappe.get_doc("Payment Entry", self.payment_entry)
                    pe.cancel()
                except Exception as e:
                    frappe.log_error(str(e), "RE Deposit Cancel - PE Cancel Error")
