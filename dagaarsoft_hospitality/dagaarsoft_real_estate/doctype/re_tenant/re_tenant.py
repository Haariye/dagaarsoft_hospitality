import frappe
from frappe.model.document import Document

class RETenant(Document):
    def before_save(self):
        self.total_stays = frappe.db.count("RE Lease", {"tenant": self.name, "docstatus": 1})
