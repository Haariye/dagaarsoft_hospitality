import frappe
from frappe import _
from frappe.utils import flt


def _has_col(doctype, fieldname):
    try:
        frappe.db.sql("SELECT `{0}` FROM `tab{1}` LIMIT 1".format(fieldname, doctype))
        return True
    except Exception:
        return False


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": _("Lease"),          "fieldname": "name",           "fieldtype": "Link",     "options": "RE Lease",    "width": 160},
        {"label": _("Property"),        "fieldname": "property",       "fieldtype": "Link",     "options": "RE Property", "width": 140},
        {"label": _("Unit"),            "fieldname": "unit",           "fieldtype": "Link",     "options": "RE Unit",     "width": 120},
        {"label": _("Tenant"),          "fieldname": "tenant_name",    "fieldtype": "Data",                               "width": 160},
        {"label": _("Start Date"),      "fieldname": "start_date",     "fieldtype": "Date",                               "width": 100},
        {"label": _("End Date"),        "fieldname": "end_date",       "fieldtype": "Date",                               "width": 100},
        {"label": _("Months"),          "fieldname": "lease_term_months", "fieldtype": "Int",                             "width": 70},
        {"label": _("Monthly Rent"),    "fieldname": "monthly_rent",   "fieldtype": "Currency",                           "width": 120},
        {"label": _("Status"),          "fieldname": "lease_status",   "fieldtype": "Data",                               "width": 110},
        {"label": _("Security Deposit"),"fieldname": "security_deposit","fieldtype": "Currency",                          "width": 120},
        {"label": _("Deposit Paid"),    "fieldname": "deposit_paid",   "fieldtype": "Currency",                           "width": 110},
        {"label": _("Invoiced (SI)"),   "fieldname": "si_total",       "fieldtype": "Currency",                           "width": 120},
        {"label": _("Received (PE)"),   "fieldname": "pe_total",       "fieldtype": "Currency",                           "width": 120},
        {"label": _("Balance"),         "fieldname": "balance",        "fieldtype": "Currency",                           "width": 120},
        {"label": _("Util. Included"),  "fieldname": "rent_includes_utility", "fieldtype": "Check",                       "width": 100},
    ]

    cond = ["rl.docstatus <= 1"]
    vals = {}
    if filters.get("property"):
        cond.append("rl.property = %(property)s")
        vals["property"] = filters["property"]
    if filters.get("tenant"):
        cond.append("rl.tenant = %(tenant)s")
        vals["tenant"] = filters["tenant"]
    if filters.get("unit"):
        cond.append("rl.unit = %(unit)s")
        vals["unit"] = filters["unit"]
    if filters.get("lease_status"):
        cond.append("rl.lease_status = %(lease_status)s")
        vals["lease_status"] = filters["lease_status"]
    if filters.get("from_date"):
        cond.append("rl.start_date >= %(from_date)s")
        vals["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        cond.append("rl.start_date <= %(to_date)s")
        vals["to_date"] = filters["to_date"]

    where = " AND ".join(cond)

    leases = frappe.db.sql("""
        SELECT
            rl.name,
            rl.property,
            rl.unit,
            rl.tenant,
            rl.start_date,
            rl.end_date,
            rl.lease_term_months,
            rl.monthly_rent,
            rl.lease_status,
            rl.security_deposit,
            rl.deposit_paid,
            rl.rent_includes_utility,
            IFNULL(rt.tenant_name, rl.tenant) AS tenant_name
        FROM `tabRE Lease` rl
        LEFT JOIN `tabRE Tenant` rt ON rt.name = rl.tenant
        WHERE {0}
        ORDER BY rl.start_date DESC
    """.format(where), vals, as_dict=True)

    if not leases:
        return columns, []

    # Collect all SI/PE totals in two bulk queries instead of per-row loop
    lease_names = [r.name for r in leases]
    placeholders = ", ".join(["%s"] * len(lease_names))

    # SI totals
    si_totals = {}
    use_si_col = _has_col("Sales Invoice", "re_lease")
    if use_si_col:
        rows = frappe.db.sql("""
            SELECT re_lease, IFNULL(SUM(grand_total), 0) AS total
            FROM `tabSales Invoice`
            WHERE re_lease IN ({0}) AND docstatus = 1 AND is_return = 0
            GROUP BY re_lease
        """.format(placeholders), lease_names, as_dict=True)
        si_totals = {r.re_lease: flt(r.total) for r in rows}
    else:
        # Fallback: match via remarks — one query per lease (slow but safe)
        for ln in lease_names:
            total = flt(frappe.db.sql(
                "SELECT IFNULL(SUM(grand_total),0) FROM `tabSales Invoice` "
                "WHERE remarks LIKE %s AND docstatus=1 AND is_return=0",
                ["%" + ln + "%"])[0][0])
            si_totals[ln] = total

    # PE totals
    pe_totals = {}
    use_pe_col = _has_col("Payment Entry", "re_lease")
    if use_pe_col:
        rows = frappe.db.sql("""
            SELECT re_lease, IFNULL(SUM(paid_amount), 0) AS total
            FROM `tabPayment Entry`
            WHERE re_lease IN ({0}) AND docstatus = 1
            GROUP BY re_lease
        """.format(placeholders), lease_names, as_dict=True)
        pe_totals = {r.re_lease: flt(r.total) for r in rows}
    else:
        for ln in lease_names:
            total = flt(frappe.db.sql(
                "SELECT IFNULL(SUM(paid_amount),0) FROM `tabPayment Entry` "
                "WHERE remarks LIKE %s AND docstatus=1",
                ["%" + ln + "%"])[0][0])
            pe_totals[ln] = total

    # Deposit totals (always from RE Deposit — no custom field needed)
    dep_rows = frappe.db.sql("""
        SELECT lease, IFNULL(SUM(amount), 0) AS total
        FROM `tabRE Deposit`
        WHERE lease IN ({0}) AND docstatus = 1
        GROUP BY lease
    """.format(placeholders), lease_names, as_dict=True)
    dep_totals = {r.lease: flt(r.total) for r in dep_rows}

    data = []
    grand = {"monthly_rent": 0, "security_deposit": 0, "deposit_paid": 0,
             "si_total": 0, "pe_total": 0, "balance": 0}

    for row in leases:
        ln       = row.name
        si_total = flt(si_totals.get(ln, 0))
        pe_total = flt(pe_totals.get(ln, 0)) + flt(dep_totals.get(ln, 0))
        balance  = si_total - pe_total

        r = {
            "name":               ln,
            "property":           row.property or "",
            "unit":               row.unit or "",
            "tenant_name":        row.tenant_name or "",
            "start_date":         row.start_date,
            "end_date":           row.end_date,
            "lease_term_months":  row.lease_term_months or 0,
            "monthly_rent":       flt(row.monthly_rent),
            "lease_status":       row.lease_status or "",
            "security_deposit":   flt(row.security_deposit),
            "deposit_paid":       flt(row.deposit_paid),
            "si_total":           si_total,
            "pe_total":           pe_total,
            "balance":            balance,
            "rent_includes_utility": row.rent_includes_utility or 0,
        }
        data.append(r)
        for k in ["monthly_rent", "security_deposit", "deposit_paid",
                  "si_total", "pe_total", "balance"]:
            grand[k] += flt(r[k])

    if data:
        data.append({
            "name": "TOTAL", "property": "", "unit": "", "tenant_name": "",
            "start_date": None, "end_date": None, "lease_term_months": None,
            "lease_status": "", "rent_includes_utility": 0, **grand
        })

    report_summary = [
        {"value": len(data) - 1,       "label": _("Leases"),         "datatype": "Int",      "indicator": "blue"},
        {"value": grand["monthly_rent"],"label": _("Monthly Total"),  "datatype": "Currency", "indicator": "blue"},
        {"value": grand["si_total"],    "label": _("Total Invoiced"), "datatype": "Currency", "indicator": "orange"},
        {"value": grand["pe_total"],    "label": _("Total Received"), "datatype": "Currency", "indicator": "green"},
        {"value": grand["balance"],     "label": _("Net Balance"),    "datatype": "Currency",
         "indicator": "red" if grand["balance"] > 0 else "green"},
    ]
    return columns, data, None, None, report_summary
