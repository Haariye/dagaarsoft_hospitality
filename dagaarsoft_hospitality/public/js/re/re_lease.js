// RE Lease Form
frappe.ui.form.on("RE Lease", {
    refresh(frm) {
        _re_lease_status_indicator(frm);
        _re_lease_filters(frm);

        if (frm.doc.docstatus === 1) {
            const st = frm.doc.lease_status;

            if (["Active","Expiring Soon"].includes(st)) {
                // Rent Schedule actions
                frm.add_custom_button(__("Generate All Due Invoices"), () =>
                    _generate_all_due(frm)).addClass("btn-primary");

                frm.add_custom_button(__("Collect Deposit"), () =>
                    _collect_deposit(frm), __("Billing"));
                frm.add_custom_button(__("Receive Payment"), () =>
                    _receive_payment(frm, null), __("Billing"));
                frm.add_custom_button(__("Utility Bill"), () => {
                    frappe.new_doc("RE Utility Bill", {
                        lease: frm.doc.name,
                        unit: frm.doc.unit,
                        tenant: frm.doc.tenant,
                        bill_date: frappe.datetime.get_today(),
                    });
                }, __("Billing"));
                frm.add_custom_button(__("Issue Notice"), () =>
                    _issue_notice(frm), __("Actions"));
                frm.add_custom_button(__("Renew Lease"), () =>
                    _renew_lease(frm), __("Actions"));
                frm.add_custom_button(__("Move In"), () => {
                    frappe.new_doc("RE Move In", {
                        lease: frm.doc.name,
                        unit: frm.doc.unit,
                        tenant: frm.doc.tenant,
                        move_in_date: frm.doc.start_date,
                    });
                }, __("Actions"));
                frm.add_custom_button(__("Move Out"), () => {
                    frappe.new_doc("RE Move Out", {
                        lease: frm.doc.name,
                        unit: frm.doc.unit,
                        tenant: frm.doc.tenant,
                        move_out_date: frappe.datetime.get_today(),
                    });
                }, __("Actions"));
                frm.add_custom_button(__("Maintenance"), () => {
                    frappe.new_doc("RE Maintenance Request", {
                        lease: frm.doc.name,
                        unit: frm.doc.unit,
                        property: frm.doc.property,
                        tenant: frm.doc.tenant,
                        request_date: frappe.datetime.get_today(),
                    });
                }, __("Actions"));
            }

            // Financial summary
            frm.add_custom_button(__("Account Statement"), () =>
                _show_statement(frm), __("Reports"));
        }

        // Highlight overdue lines
        _highlight_schedule(frm);
    },

    unit(frm) {
        if (!frm.doc.unit) return;
        frappe.db.get_value("RE Unit",
            frm.doc.unit,
            ["monthly_rent","security_deposit_amount","rent_includes_utility",
             "property","furnishing"], r => {
            if (!r) return;
            if (!frm.doc.monthly_rent && r.monthly_rent)
                frm.set_value("monthly_rent", r.monthly_rent);
            if (!frm.doc.security_deposit && r.security_deposit_amount)
                frm.set_value("security_deposit", r.security_deposit_amount);
            if (r.property && !frm.doc.property)
                frm.set_value("property", r.property);
            frm.set_value("rent_includes_utility", r.rent_includes_utility || 0);
        });
    },

    tenant(frm) {
        if (!frm.doc.tenant) return;
        // Check tenant has a customer linked
        frappe.db.get_value("RE Tenant", frm.doc.tenant, "customer", r => {
            if (!r || !r.customer) {
                frappe.msgprint({
                    title: __("Warning"),
                    message: __("Tenant {0} has no ERPNext Customer linked. Invoices cannot be created.", [frm.doc.tenant]),
                    indicator: "orange"
                });
            }
        });
    },

    start_date(frm) { _update_term(frm); },
    end_date(frm) { _update_term(frm); },
});

// Rent schedule row actions
frappe.ui.form.on("RE Rent Schedule Line", {
    // Invoice button per row handled via custom button
});

function _update_term(frm) {
    if (frm.doc.start_date && frm.doc.end_date) {
        const months = Math.round(
            frappe.datetime.get_day_diff(frm.doc.end_date, frm.doc.start_date) / 30.44);
        frm.set_value("lease_term_months", months);
    }
}

function _re_lease_filters(frm) {
    frm.set_query("unit", () => ({
        filters: {
            property: frm.doc.property || undefined,
            status: ["in", ["Available","Occupied"]]
        }
    }));
    frm.set_query("tenant", () => ({ filters: {} }));
}

function _re_lease_status_indicator(frm) {
    const colors = {
        "Active": "green", "Draft": "grey", "Expiring Soon": "orange",
        "Expired": "red", "Terminated": "red", "Renewed": "blue"
    };
    frm.page.set_indicator(__(frm.doc.lease_status || "Draft"),
        colors[frm.doc.lease_status] || "grey");
    if (frm.doc.monthly_rent) {
        frm.dashboard.add_indicator(
            __("Rent: {0}/mo", [fmt_money(frm.doc.monthly_rent)]), "blue");
    }
    if (frm.doc.rent_includes_utility) {
        frm.dashboard.add_indicator(__("Utilities Included"), "green");
    }
    // Deposit status
    const depColors = {"Paid":"green","Partially Paid":"orange","Pending":"red","Refunded":"grey"};
    if (frm.doc.deposit_status) {
        frm.dashboard.add_indicator(
            __("Deposit: {0}", [frm.doc.deposit_status]),
            depColors[frm.doc.deposit_status] || "grey");
    }
}

function _highlight_schedule(frm) {
    const today = frappe.datetime.get_today();
    (frm.doc.rent_schedule || []).forEach(row => {
        if (row.status === "Pending" && row.due_date < today) {
            // Mark overdue in grid
            const $row = frm.fields_dict.rent_schedule.grid.get_row(row.name);
            if ($row) $row.row.css("background", "#fff5f5");
        }
    });
}

function _generate_all_due(frm) {
    const today = frappe.datetime.get_today();
    const due = (frm.doc.rent_schedule || []).filter(r =>
        r.status === "Pending" && r.due_date <= today);
    if (!due.length) {
        frappe.msgprint(__("No pending invoices due today or earlier."));
        return;
    }
    frappe.confirm(
        __("Generate {0} invoice(s) for due periods?", [due.length]),
        () => {
            let chain = Promise.resolve();
            due.forEach(row => {
                chain = chain.then(() => frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease.generate_rent_invoice",
                    args: {lease_name: frm.doc.name, schedule_row_name: row.name, submit_invoice: 1},
                }));
            });
            chain.then(() => {
                frappe.show_alert({message: __("{0} invoice(s) generated.", [due.length]), indicator: "green"});
                frm.reload_doc();
            });
        }
    );
}

function _collect_deposit(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Collect Security Deposit"),
        fields: [
            {fieldname:"deposit_type","fieldtype":"Select","label":__("Type"),
             options:"Security Deposit\nAdvance Rent\nKey Deposit",
             default:"Security Deposit", reqd:1},
            {fieldname:"amount","fieldtype":"Currency","label":__("Amount"),
             default: frm.doc.security_deposit, reqd:1},
            {fieldname:"payment_mode","fieldtype":"Select","label":__("Payment Mode"),
             options:"Cash\nBank Transfer\nCard\nCheque", reqd:1},
            {fieldname:"notes","fieldtype":"Data","label":__("Reference")},
        ],
        primary_action_label: __("Collect"),
        primary_action(v) {
            frappe.new_doc("RE Deposit", {
                lease: frm.doc.name,
                tenant: frm.doc.tenant,
                unit: frm.doc.unit,
                deposit_type: v.deposit_type,
                amount: v.amount,
                notes: v.notes,
            });
            d.hide();
        }
    });
    d.show();
}

function _receive_payment(frm, schedule_row_name) {
    const d = new frappe.ui.Dialog({
        title: __("Receive Rent Payment"),
        fields: [
            {fieldname:"amount","fieldtype":"Currency","label":__("Amount"),
             default: frm.doc.monthly_rent, reqd:1},
            {fieldname:"payment_mode","fieldtype":"Select","label":__("Payment Mode"),
             options:"Cash\nBank Transfer\nCard\nCheque\nCity Ledger", reqd:1},
            {fieldname:"reference_number","fieldtype":"Data","label":__("Reference No")},
        ],
        primary_action_label: __("Confirm"),
        primary_action(v) {
            frappe.call({
                method: "dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease.receive_payment",
                args: {
                    lease_name: frm.doc.name,
                    amount: v.amount,
                    payment_mode: v.payment_mode,
                    reference_number: v.reference_number,
                    schedule_row_name: schedule_row_name || "",
                },
                freeze: true,
                callback(r) { d.hide(); frm.reload_doc(); }
            });
        }
    });
    d.show();
}

function _issue_notice(frm) {
    frappe.new_doc("RE Notice", {
        lease: frm.doc.name,
        unit: frm.doc.unit,
        tenant: frm.doc.tenant,
        notice_date: frappe.datetime.get_today(),
    });
}

function _renew_lease(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Renew Lease"),
        fields: [
            {fieldname:"new_end_date","fieldtype":"Date","label":__("New End Date"),
             reqd:1},
            {fieldname:"new_rent","fieldtype":"Currency","label":__("New Monthly Rent"),
             default: frm.doc.monthly_rent},
            {fieldname:"notes","fieldtype":"Text","label":__("Notes")},
        ],
        primary_action_label: __("Create Renewal Lease"),
        primary_action(v) {
            frappe.call({
                method: "frappe.model.mapper.make_mapped_doc",
                args: {
                    method: "dagaarsoft_hospitality.dagaarsoft_real_estate.doctype.re_lease.re_lease.make_renewal",
                    source_name: frm.doc.name,
                    args: {new_end_date: v.new_end_date, new_rent: v.new_rent}
                },
                callback(r) {
                    if (r.message) {
                        frappe.set_route("Form", "RE Lease", r.message);
                    }
                }
            });
            d.hide();
        }
    });
    d.show();
}

function _show_statement(frm) {
    frappe.call({
        method: "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.reports.get_lease_statement",
        args: {lease_name: frm.doc.name},
        callback(r) {
            if (!r.message) return;
            const s = r.message;
            // Build ledger table
            let rows = "";
            (s.ledger || []).forEach(e => {
                const bColor = e.balance > 0.01 ? "#c53030" : "#276749";
                rows += `<tr style="border-bottom:1px solid #eee">
                    <td style="padding:5px 8px">${e.date}</td>
                    <td style="padding:5px 8px">${e.type}</td>
                    <td style="padding:5px 8px">${e.description}</td>
                    <td style="text-align:right;padding:5px 8px;color:#c53030">${e.debit > 0 ? fmt_money(e.debit) : ""}</td>
                    <td style="text-align:right;padding:5px 8px;color:#276749">${e.credit > 0 ? fmt_money(e.credit) : ""}</td>
                    <td style="text-align:right;padding:5px 8px;font-weight:bold;color:${bColor}">${fmt_money(Math.abs(e.balance))}${e.balance < -0.01 ? " CR" : ""}</td>
                </tr>`;
            });
            const balColor = s.balance > 0.01 ? "#c53030" : "#276749";
            frappe.msgprint({
                title: __("Lease Account Statement"),
                wide: true,
                message: `
                <div style="font-family:Arial;font-size:13px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:12px">
                    <div>
                      <b>${s.tenant_name}</b> — ${s.unit}<br>
                      <span style="color:#666">${s.start_date} to ${s.end_date}</span>
                    </div>
                    <div style="text-align:right;background:#f0fff4;padding:10px 16px;border-radius:6px">
                      <div style="font-size:11px;color:#276749">Monthly Rent</div>
                      <div style="font-size:20px;font-weight:bold;color:#276749">${fmt_money(s.monthly_rent)}</div>
                    </div>
                  </div>
                  <table style="width:100%;border-collapse:collapse">
                    <thead><tr style="background:#edf2f7;font-weight:bold;font-size:11px">
                      <th style="padding:6px 8px;text-align:left">Date</th>
                      <th style="padding:6px 8px;text-align:left">Type</th>
                      <th style="padding:6px 8px;text-align:left">Description</th>
                      <th style="padding:6px 8px;text-align:right;color:#c53030">Debit</th>
                      <th style="padding:6px 8px;text-align:right;color:#276749">Credit</th>
                      <th style="padding:6px 8px;text-align:right">Balance</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                    <tfoot style="border-top:2px solid #cbd5e0;font-weight:bold">
                      <tr>
                        <td colspan="3" style="padding:7px 8px">Total</td>
                        <td style="text-align:right;padding:7px 8px;color:#c53030">${fmt_money(s.total_debit)}</td>
                        <td style="text-align:right;padding:7px 8px;color:#276749">${fmt_money(s.total_credit)}</td>
                        <td style="text-align:right;padding:7px 8px;color:${balColor};font-size:16px">${fmt_money(Math.abs(s.balance))}${s.balance < -0.01 ? " CR" : ""}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>`
            });
        }
    });
}

function fmt_money(v) {
    return parseFloat(v||0).toLocaleString("en", {minimumFractionDigits:2});
}
