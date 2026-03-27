import frappe
from frappe.model.document import Document
class REMoveOut(Document):
    def on_submit(self):
        frappe.db.set_value("RE Lease", self.lease, "move_out_date", self.move_out_date)
        frappe.db.set_value("RE Lease", self.lease, "lease_status", "Expired")
        frappe.db.set_value("RE Unit", self.unit, {
            "status": "Vacant - Cleaning",
            "current_tenant": "", "current_lease": ""
        })
