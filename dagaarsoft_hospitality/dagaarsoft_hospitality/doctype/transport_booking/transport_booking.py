# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document


class TransportBooking(Document):

    def validate(self):
        pass

    def on_submit(self):
        self.db_set("booking_status", "Confirmed")
        if self.guest_stay and self.fare_amount:
            stay = frappe.db.get_value("Guest Stay", self.guest_stay,
                ["stay_status", "guest_folio"], as_dict=True)
            if stay and stay.stay_status == "Checked In" and stay.guest_folio and self.charge_to_folio:
                from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
                post_charge_to_folio(
                    stay.guest_folio,
                    "Transport: {0} to {1}".format(self.pickup_location or "", self.dropoff_location or ""),
                    self.fare_amount,
                    "Transport",
                    "Transport Booking",
                    self.name
                )

    def on_cancel(self):
        self.db_set("booking_status", "Cancelled")


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
