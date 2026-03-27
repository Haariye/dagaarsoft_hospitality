import frappe
from frappe.utils import flt
from frappe.model.document import Document
class REUtilityBill(Document):
    def validate(self):
        if self.current_reading and self.previous_reading:
            self.consumption = flt(self.current_reading) - flt(self.previous_reading)
        if not self.tenant_portion:
            self.tenant_portion = flt(self.bill_amount)
