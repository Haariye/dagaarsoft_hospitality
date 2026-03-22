# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


class ServiceRequest(Document):

    def validate(self):
        if not self.request_time:
            self.request_time = now_datetime()

    def on_submit(self):
        self.db_set("request_status", "Open")

    def on_cancel(self):
        self.db_set("request_status", "Cancelled")


@frappe.whitelist()
def complete_request(request_name, resolution=None):
    """Complete a service request and optionally post charge to folio."""
    req = frappe.get_doc("Service Request", request_name)
    req.db_set("request_status", "Completed")
    req.db_set("completed_at", now_datetime())
    req.db_set("completed_by", frappe.session.user)
    if resolution:
        req.db_set("resolution_notes", resolution)

    # If charge applicable and guest is in-house, post to folio
    if req.charge_amount and req.guest_stay:
        stay = frappe.db.get_value("Guest Stay", req.guest_stay,
            ["stay_status", "guest_folio"], as_dict=True)
        if stay and stay.stay_status == "Checked In" and stay.guest_folio:
            from dagaarsoft_hospitality.dagaarsoft_hospitality.utils.folio_utils import post_charge_to_folio
            post_charge_to_folio(
                stay.guest_folio,
                "Service: {0} — {1}".format(req.service_type or "Request", req.name),
                req.charge_amount,
                "Miscellaneous",
                "Service Request",
                req.name
            )
    frappe.msgprint(_("Service request completed."), alert=True)
    return {"ok": True}


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
