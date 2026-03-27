import frappe
from frappe import _
from frappe.model.document import Document
class REMaintenanceRequest(Document):
    def on_submit(self):
        frappe.db.set_value("RE Unit", self.unit, "status", "Under Maintenance")
    def validate(self):
        if self.status == "Completed" and not self.completion_date:
            from frappe.utils import today
            self.completion_date = today()
        if self.status == "Completed":
            frappe.db.set_value("RE Unit", self.unit, "status", "Available")
