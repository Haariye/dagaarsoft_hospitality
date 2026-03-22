# DagaarSoft Hospitality

Enterprise Hotel, Restaurant & Hospitality Management for ERPNext v14, v15, v16.

## Installation

```bash
bench get-app https://github.com/Haariye/dagaarsoft_hospitality.git
bench --site your-site.local install-app dagaarsoft_hospitality
```

## Requirements

- Frappe Framework v14 / v15 / v16
- ERPNext v14 / v15 / v16

## Features

- Property, Room Type, Room management
- Reservation → Guest Stay → Guest Folio billing cycle
- Automatic room charge posting (Night Audit / Scheduler)
- Room Move with automatic rate-difference billing (upgrade surcharge / downgrade credit)
- Full Sales Invoice status tracking (Paid / Partly Paid / Unpaid / Overdue / Cancelled)
- Deposit collected on Folio at check-in
- Dual-customer billing: Guest + Bill-To (Company / Travel Agency / City Ledger)
- POSAwesome integration: Hotel Room & Restaurant Table fields on Sales Invoice
- Housekeeping, Maintenance, Minibar, Laundry, Banquet, Transport modules
- Night Audit with auto-scheduler fallback
- 12 reports, 4 workspaces, scheduled jobs
