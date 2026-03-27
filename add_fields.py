import frappe; frappe.init(site="uat.dagaartech.com"); frappe.connect()

fields = [
    dict(fieldname="default_posa_charge_category", label="Default POSA Charge Category", fieldtype="Select", options="F&B\nRestaurant\nMinibar\nRoom Service\nMiscellaneous", default="F&B", insert_after="allow_posa_room_charge"),
    dict(fieldname="enable_restaurant_table_field", label="Show Restaurant Table in POSA", fieldtype="Check", default="1", insert_after="default_posa_charge_category"),
    dict(fieldname="room_service_enabled", label="Room Service Enabled", fieldtype="Check", default="1", insert_after="enable_restaurant_table_field"),
    dict(fieldname="auto_night_audit", label="Auto Night Audit at 00:05 Daily", fieldtype="Check", default="1", insert_after="cascade_cancel_linked_transactions"),
    dict(fieldname="deposit_collection_point", label="Deposit Collected On", fieldtype="Select", options="Folio\nReservation", default="Folio", insert_after="deposit_required"),
    dict(fieldname="waive_deposit_role", label="Waive Deposit Role", fieldtype="Link", options="Role", default="Hotel Manager", insert_after="manager_override_role"),
    dict(fieldname="night_audit_reminder_email", label="Night Audit Alert Email", fieldtype="Data", options="Email", insert_after="auto_night_audit"),
]

dt = frappe.get_doc("DocType", "Hospitality Settings")
existing = [f.fieldname for f in dt.fields]
added = []

for field in fields:
    fn = field["fieldname"]
    if fn in existing:
        print("SKIP:", fn)
        continue
    after = field.pop("insert_after", None)
    idx = next((i+1 for i,f in enumerate(dt.fields) if f.fieldname == after), len(dt.fields))
    row = dt.append("fields", field)
    dt.fields.remove(row)
    dt.fields.insert(idx, row)
    added.append(fn)
    print("ADD:", fn)

if added:
    dt.save(ignore_permissions=True)
    defaults = dict(default_posa_charge_category="F&B", enable_restaurant_table_field=1, room_service_enabled=1, auto_night_audit=1, deposit_collection_point="Folio", waive_deposit_role="Hotel Manager")
    [frappe.db.set_single_value("Hospitality Settings", k, v) for k,v in defaults.items() if k in added]
    frappe.db.commit()
    print("Done. Added:", added)
else:
    print("Nothing added.")
