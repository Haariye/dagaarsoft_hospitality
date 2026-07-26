import frappe

def run():
    for dt in ["Payment Entry", "Sales Invoice", "Journal Entry", "Hotel Deposit", "Housekeeping Task", "Room Move", "Guest Folio", "Guest Stay", "Reservation"]:
        for d in frappe.get_all(dt, filters={"docstatus": 2}, fields=["name"]):
            try:
                frappe.delete_doc(dt, d.name, force=True, ignore_permissions=True, delete_permanently=True)
                print(f"Deleted {dt}: {d.name}")
            except Exception as e:
                print(f"Skip {dt} {d.name}: {e}")
    frappe.db.commit()
    print("Done")