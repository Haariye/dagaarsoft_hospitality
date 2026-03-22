import frappe
from frappe import _
from frappe.model.document import Document


class RatePlan(Document):

    def validate(self):
        if self.valid_from and self.valid_to:
            if self.valid_from > self.valid_to:
                frappe.throw(_("Valid To must be after Valid From."))
        # Ensure only one default per property
        if self.is_default:
            existing = frappe.db.get_value("Rate Plan",
                {"property": self.property, "is_default": 1, "name": ["!=", self.name or ""]},
                "name")
            if existing:
                frappe.db.set_value("Rate Plan", existing, "is_default", 0)
                frappe.msgprint(_("Previous default rate plan {0} unset.").format(existing), alert=True)


@frappe.whitelist()
def get_rate_for_room_type(rate_plan, room_type):
    """Fetch rate for a room type from a rate plan."""
    rate = frappe.db.get_value("Rate Plan Line",
        {"parent": rate_plan, "room_type": room_type}, "rate")
    return flt(rate) if rate else 0


@frappe.whitelist()
def get_default_rate_plan(property_name):
    return frappe.db.get_value("Property", property_name, "default_rate_plan")


def flt(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def validate(doc, method=None): doc.validate()
