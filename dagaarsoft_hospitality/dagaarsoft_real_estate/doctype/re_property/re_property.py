import frappe
from frappe.model.document import Document

class REProperty(Document):
    def before_save(self):
        self._update_unit_counts()

    def _update_unit_counts(self):
        total = frappe.db.count("RE Unit", {"property": self.name, "is_active": 1})
        occupied = frappe.db.count("RE Unit", {"property": self.name, "status": "Occupied", "is_active": 1})
        available = frappe.db.count("RE Unit", {"property": self.name, "status": "Available", "is_active": 1})
        self.total_units = total
        self.occupied_units = occupied
        self.available_units = available
