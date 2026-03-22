# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


class MaintenanceTicket(Document):

    def validate(self):
        if self.room and self.property:
            rp = frappe.db.get_value("Room", self.room, "property")
            if rp != self.property:
                frappe.throw(_("Room does not belong to this Property."))

    def on_submit(self):
        self.db_set("ticket_status", "Open")
        if self.room:
            frappe.db.set_value("Room", self.room, "room_status", "Maintenance")

    def on_cancel(self):
        self.db_set("ticket_status", "Cancelled")
        if self.room:
            # Only restore if room is still in Maintenance status from this ticket
            cur = frappe.db.get_value("Room", self.room, "room_status")
            if cur == "Maintenance":
                frappe.db.set_value("Room", self.room, "room_status", "Vacant Dirty")


@frappe.whitelist()
def resolve_ticket(ticket_name, resolution_notes=None):
    """Mark maintenance ticket as resolved."""
    ticket = frappe.get_doc("Maintenance Ticket", ticket_name)
    ticket.db_set("ticket_status", "Resolved")
    ticket.db_set("resolved_at", now_datetime())
    ticket.db_set("resolved_by", frappe.session.user)
    if resolution_notes:
        ticket.db_set("resolution_notes", resolution_notes)
    if ticket.room:
        frappe.db.set_value("Room", ticket.room, "room_status", "Vacant Dirty")
    frappe.msgprint(_("Ticket resolved. Room returned to service."), alert=True)
    return {"ok": True}


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
def on_cancel(doc, method=None): doc.on_cancel()
