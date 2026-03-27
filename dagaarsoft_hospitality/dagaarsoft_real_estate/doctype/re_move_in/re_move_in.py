import frappe
from frappe.model.document import Document
class REMoveIn(Document):
    def on_submit(self):
        frappe.db.set_value("RE Lease", self.lease, "move_in_date", self.move_in_date)
        frappe.db.set_value("RE Unit", self.unit, "status", "Occupied")
