import frappe
from frappe.model.document import Document
class RENotice(Document):
    def on_submit(self):
        self.db_set("status", "Sent")
        # If renewal accepted - update lease end date
    def validate(self):
        if self.notice_type == "Renewal Offer" and not self.new_end_date:
            frappe.throw(frappe._("New End Date required for Renewal Offer."))
        if self.notice_type == "Rent Increase" and not self.new_rent_amount:
            frappe.throw(frappe._("New Rent Amount required for Rent Increase notice."))
