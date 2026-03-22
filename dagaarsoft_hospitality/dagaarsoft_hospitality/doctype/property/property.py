import frappe
from frappe.model.document import Document

class Property(Document):
    def validate(self):
        if not self.property_code:
            self.property_code = self.name or ""

def validate(doc, method=None): doc.validate()
