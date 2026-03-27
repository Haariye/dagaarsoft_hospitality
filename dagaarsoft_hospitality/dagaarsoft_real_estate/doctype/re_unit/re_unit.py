import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document

class REUnit(Document):
    def validate(self):
        if not self.security_deposit_amount and self.deposit_months and self.monthly_rent:
            self.security_deposit_amount = flt(self.monthly_rent) * int(self.deposit_months)
        if self.fixed_asset:
            asset = frappe.db.get_value("Asset", self.fixed_asset, "gross_purchase_amount")
            if asset:
                self.asset_value = flt(asset)

    def on_update(self):
        # Refresh property unit counts
        if self.property:
            prop = frappe.get_doc("RE Property", self.property)
            prop.save(ignore_permissions=True)
