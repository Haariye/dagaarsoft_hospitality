
import frappe
from frappe.model.document import Document
from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.room_utils import get_billing_info_for_room

class POSAHotelRoom(Document):
    def validate(self):
        if self.room:
            info = get_billing_info_for_room(self.room)
            self.guest_stay = info.get("guest_stay")
            self.guest_folio = info.get("guest_folio")
            self.customer = info.get("customer")
            self.guest_name = info.get("guest_name")
            self.billing_instruction = info.get("billing_instruction")
            self.balance_due = frappe.db.get_value("Guest Folio", self.guest_folio, "balance_due") or 0
