# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import now_datetime, today, flt
from frappe.model.document import Document


class ShiftHandover(Document):

    def validate(self):
        if not self.handover_date:
            self.handover_date = today()
        self._compute_shift_summary()

    def _compute_shift_summary(self):
        """Auto-compute cash, payments, check-ins/outs for this shift."""
        if not self.property or not self.shift_start:
            return
        # Count check-ins during shift
        checkins = frappe.db.count("Guest Stay", {
            "property": self.property,
            "actual_checkin": [">=", str(self.shift_start)],
        })
        self.total_checkins = checkins

        # Count check-outs
        checkouts = frappe.db.count("Guest Stay", {
            "property": self.property,
            "actual_checkout": [">=", str(self.shift_start)],
        })
        self.total_checkouts = checkouts

    def on_submit(self):
        self.db_set("handover_status", "Completed")
        self.db_set("handed_over_at", now_datetime())
        frappe.msgprint(_("Shift handover completed."), alert=True)


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()
