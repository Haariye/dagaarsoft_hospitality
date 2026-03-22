# -*- coding: utf-8 -*-
"""
Housekeeping Task v3
FIX: When room is cleaned, updates BOTH room_status AND housekeeping_status.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


# Full status mapping: task_type -> (housekeeping_status, room_status or None)
STATUS_MAP = {
    "Cleaning":     ("Clean", "Vacant Clean"),
    "Inspection":   ("Inspected", "Vacant Clean"),
    "Turndown":     ("Clean", None),          # Occupied room turndown — don't change room_status
    "Deep Clean":   ("Clean", "Vacant Clean"),
    "Linen Change": ("Clean", None),
}


class HousekeepingTask(Document):

    def validate(self):
        if self.room and self.property:
            rp = frappe.db.get_value("Room", self.room, "property")
            if rp != self.property:
                frappe.throw(_("Room does not belong to this Property."))

    def on_submit(self):
        if self.task_status == "Completed":
            self._update_room_status()
            self.db_set("completed_at", now_datetime())
            self.db_set("completed_by", frappe.session.user)

    def _update_room_status(self):
        """FIX: Update both housekeeping_status AND room_status."""
        hs, rs = STATUS_MAP.get(self.task_type, ("Clean", None))
        room = frappe.get_doc("Room", self.room)

        updates = {"housekeeping_status": hs}
        # Only update room_status if it makes sense (don't mark occupied room as Vacant)
        if rs and room.room_status in ("Vacant Dirty", "Dirty", "Out of Order"):
            updates["room_status"] = rs
        elif rs and room.room_status not in ("Occupied",):
            updates["room_status"] = rs

        frappe.db.set_value("Room", self.room, updates)
        frappe.msgprint(
            _("Room {0}: Housekeeping → {1}{2}").format(
                self.room, hs,
                ", Status → {0}".format(rs) if rs and "room_status" in updates else ""
            ), alert=True
        )


def validate(doc, method=None): doc.validate()
def on_submit(doc, method=None): doc.on_submit()


@frappe.whitelist()
def quick_update_status(task_name, new_status):
    """One-tap status update from mobile/housekeeping board."""
    task = frappe.get_doc("Housekeeping Task", task_name)
    task.db_set("task_status", new_status)
    if new_status == "Completed":
        hs, rs = STATUS_MAP.get(task.task_type, ("Clean", None))
        room = frappe.get_doc("Room", task.room)
        updates = {"housekeeping_status": hs}
        if rs and room.room_status not in ("Occupied",):
            updates["room_status"] = rs
        frappe.db.set_value("Room", task.room, updates)
        frappe.db.set_value("Housekeeping Task", task_name, {
            "completed_at": now_datetime(),
            "completed_by": frappe.session.user
        })
    return {"status": "ok", "new_status": new_status}


@frappe.whitelist()
def get_tasks_for_date(task_date, property_name=None, assigned_to=None):
    """Return all tasks for a given date for the housekeeper board."""
    filters = {"task_date": task_date, "docstatus": ["!=", 2]}
    if property_name:
        filters["property"] = property_name
    if assigned_to:
        filters["assigned_to"] = assigned_to
    tasks = frappe.get_all("Housekeeping Task",
        filters=filters,
        fields=["name", "room", "task_type", "task_status", "priority",
                "assigned_to", "scheduled_time", "notes", "completed_at", "completed_by"],
        order_by="room asc"
    )
    for t in tasks:
        rs = frappe.db.get_value("Room", t.room,
            ["room_status", "housekeeping_status", "floor", "wing"], as_dict=True)
        if rs:
            t.update(rs)
    return tasks


@frappe.whitelist()
def bulk_assign_tasks(property_name, task_date, task_type="Cleaning"):
    """Auto-generate housekeeping tasks for all rooms needing attention."""
    dirty_rooms = frappe.get_all("Room",
        filters={
            "property": property_name,
            "is_active": 1,
            "housekeeping_status": ["in", ["Dirty", "Inspected"]],
            "is_out_of_order": 0
        },
        fields=["name", "floor", "wing"]
    )
    created = 0
    for r in dirty_rooms:
        if frappe.db.exists("Housekeeping Task", {
            "room": r.name, "task_date": task_date,
            "task_type": task_type, "docstatus": ["!=", 2]
        }):
            continue
        task = frappe.new_doc("Housekeeping Task")
        task.property = property_name
        task.room = r.name
        task.task_type = task_type
        task.task_date = task_date
        task.task_status = "Pending"
        task.priority = "Normal"
        task.insert(ignore_permissions=True)
        task.submit()
        created += 1
    frappe.msgprint(_("{0} housekeeping tasks created.").format(created), alert=True)
    return {"created": created}
