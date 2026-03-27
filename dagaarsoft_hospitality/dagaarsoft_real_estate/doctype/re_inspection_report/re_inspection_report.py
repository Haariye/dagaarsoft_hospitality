import frappe
from frappe.utils import flt
from frappe.model.document import Document
class REInspectionReport(Document):
    def validate(self):
        self.total_repair_cost = sum(
            flt(i.estimated_repair_cost) for i in (self.get("items") or [])
            if i.repair_needed)
    def on_submit(self):
        frappe.db.set_value("RE Unit", self.unit, "last_inspection_date", self.inspection_date)
