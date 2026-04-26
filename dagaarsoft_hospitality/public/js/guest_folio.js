// Guest Folio JS v6.0 — Redesigned: unified billing, statement always visible
frappe.ui.form.on("Guest Folio", {
    refresh(frm) {
        _setup_indicators(frm);
        _lock_charge_table(frm);
        var isManager = frappe.user_roles.includes("Hotel Manager");

        if (frm.doc.docstatus === 1) {
            // Account Statement — ALWAYS visible regardless of folio status
            _add_statement_btn(frm);

            if (frm.doc.folio_status === "Open") {
                // Hotel Manager billing actions
                if (isManager) {
                    _add_room_charge_btn(frm);
                    _add_generate_invoice_btn(frm);
                }
                _add_settle_payment_btn(frm);
                _add_collect_deposit_btn(frm);
                if (isManager) {
                    _add_return_deposit_btn(frm);
                }
                _add_sync_deposits_btn(frm);
                _add_void_charge_btn(frm);
            }
        }

        if (frm.doc.sales_invoice) frm.add_custom_button(__("View Invoice"),
            () => frappe.set_route("Form","Sales Invoice",frm.doc.sales_invoice), __("Links"));
        if (frm.doc.guest_stay) frm.add_custom_button(__("View Stay"),
            () => frappe.set_route("Form","Guest Stay",frm.doc.guest_stay), __("Links"));
    }
});

function _lock_charge_table(frm) {
    var grid = frm.fields_dict.folio_charges && frm.fields_dict.folio_charges.grid;
    if (!grid) return;
    grid.wrapper.find(".grid-add-row,.grid-remove-rows").hide();
    grid.df.cannot_add_rows = true;
    grid.df.cannot_delete_rows = true;
    try { grid.refresh(); } catch(e) {}
}

function _setup_indicators(frm) {
    var bal = flt(frm.doc.balance_due);
    if (frm.doc.folio_status === "Closed") frm.page.set_indicator(__("Settled"), "green");
    else if (bal < -0.01) frm.page.set_indicator(__("Overpaid " + fc(Math.abs(bal))), "red");
    else if (bal > 0.01)  frm.page.set_indicator(__("Balance: " + fc(bal)), "orange");
    else frm.page.set_indicator(__("Open"), "blue");
    if (frm.doc.billing_customer && frm.doc.billing_customer !== frm.doc.customer)
        frm.dashboard.add_indicator(__("Bill To: {0}", [frm.doc.billing_customer]), "orange");
    if (frm.doc.sales_invoice_status) {
        var c = {"Fully Paid \u2713":"green","Unpaid":"red","Overdue":"red","Partly Paid":"orange","Cancelled":"grey"}[frm.doc.sales_invoice_status] || "blue";
        frm.dashboard.add_indicator(__("Invoice: {0}", [frm.doc.sales_invoice_status]), c);
    }
}

// ── Post Room Charges (Hotel Manager) ────────────────────────────────────
function _add_room_charge_btn(frm) {
    frm.add_custom_button(__("Post Room Charges"), function() {
        frappe.call({
            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.calculate_room_charges_for_stay",
            args: {guest_stay_name: frm.doc.guest_stay},
            callback: function(r) {
                if (!r.message) return;
                var res = r.message;
                if (res.pending_count === 0) {
                    frappe.msgprint({title: __("Already Charged"),
                        message: __("All {0} night(s) already posted with invoices.", [res.already_posted_count]),
                        indicator: "orange"});
                    return;
                }
                frappe.confirm(
                    __("{0} pending night(s) at {1}/night. Post charges + create invoices?",
                        [res.pending_count, fc(res.nightly_rate)]),
                    function() {
                        frappe.call({
                            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.post_all_room_charges",
                            args: {guest_stay_name: frm.doc.guest_stay}, freeze: true,
                            callback: function(r2) {
                                if (r2.message) frappe.show_alert({message: r2.message.message, indicator: "green"});
                                frm.reload_doc();
                            }
                        });
                    }
                );
            }
        });
    }, __("Billing"));
}

// ── Generate Invoice — unified (replaces old Generate Invoice + Bill Pending) ──
function _add_generate_invoice_btn(frm) {
    var unbilled = (frm.doc.folio_charges || []).filter(function(r){return !r.is_void && !r.is_billed;});
    if (!unbilled.length) return;

    var total = unbilled.reduce(function(s,c){return s+flt(c.amount);},0);
    frm.add_custom_button(__("Generate Invoice ({0})", [fc(total)]), function() {
        var rows = "";
        unbilled.forEach(function(c){
            rows += "<tr><td style='padding:4px 8px'>" + (c.posting_date||"") + "</td>"
                + "<td style='padding:4px 8px'>" + (c.description||c.charge_category) + "</td>"
                + "<td style='text-align:right;padding:4px 8px'>" + fc(c.amount) + "</td></tr>";
        });
        var d = new frappe.ui.Dialog({
            title: __("Generate Invoice — {0} unbilled charge(s)", [unbilled.length]),
            fields: [
                {fieldname:"info", fieldtype:"HTML", options:
                    "<table style='width:100%;font-size:12px;margin-bottom:8px'>"
                    + "<tr style='background:#f0f4f8;font-weight:600'><th style='padding:4px 8px'>Date</th><th style='padding:4px 8px'>Description</th><th style='text-align:right;padding:4px 8px'>Amount</th></tr>"
                    + rows
                    + "<tr style='border-top:1px solid #ccc;font-weight:bold'><td colspan='2' style='padding:4px 8px'>Total</td><td style='text-align:right;padding:4px 8px'>" + fc(total) + "</td></tr>"
                    + "</table>"
                },
                {fieldname:"discount_pct", fieldtype:"Float", label:__("Discount %"), default:0},
                {fieldname:"discount_amount", fieldtype:"Currency", label:__("Discount Amount"), default:0}
            ],
            primary_action_label: __("Generate & Submit"),
            primary_action: function(v) {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.generate_folio_invoice",
                    args: {folio_name:frm.doc.name, discount_pct:v.discount_pct||0, discount_amount:v.discount_amount||0},
                    freeze:true,
                    callback: function(r) {
                        d.hide();
                        if (r.message) frappe.show_alert({message:__("Invoice {0} created",[r.message]),indicator:"green"});
                        frm.reload_doc();
                    }
                });
            }
        });
        d.show();
    }, __("Billing"));
}

// ── Settle Payment ───────────────────────────────────────────────────────
function _add_settle_payment_btn(frm) {
    if (!frm.doc.sales_invoice) return;
    var bal = flt(frm.doc.balance_due);
    if (bal <= 0.01) return;

    frm.add_custom_button(__("Settle Payment"), function() {
        var d = new frappe.ui.Dialog({
            title: __("Settle Payment — Outstanding: {0}", [fc(bal)]),
            fields: [
                {fieldname:"amount", fieldtype:"Currency", label:__("Amount"), reqd:1, default:bal},
                {fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
                 options:"Cash\nCard\nBank Transfer\nOnline\nCity Ledger\nCheque"},
                {fieldname:"reference_number", fieldtype:"Data", label:__("Reference")}
            ],
            primary_action_label: __("Confirm Payment"),
            primary_action: function(v) {
                if (flt(v.amount) <= 0) { frappe.msgprint(__("Amount must be > 0")); return; }
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.settle_with_payment",
                    args: {folio_name:frm.doc.name, amount:v.amount, payment_mode:v.payment_mode, reference_number:v.reference_number},
                    freeze:true, callback: function() { d.hide(); frm.reload_doc(); }
                });
            }
        });
        d.show();
    }, __("Billing"));
}

// ── Collect Deposit ──────────────────────────────────────────────────────
function _add_collect_deposit_btn(frm) {
    frm.add_custom_button(__("Collect Deposit"), function() {
        var d = new frappe.ui.Dialog({
            title: __("Collect Deposit"),
            fields: [
                {fieldname:"amount", fieldtype:"Currency", label:__("Amount"), reqd:1},
                {fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
                 options:"Cash\nCard\nBank Transfer\nOnline\nCheque"},
                {fieldname:"reference_number", fieldtype:"Data", label:__("Reference")}
            ],
            primary_action_label: __("Collect"),
            primary_action: function(v) {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.collect_deposit",
                    args: {folio_name:frm.doc.name, amount:v.amount, payment_mode:v.payment_mode, reference_number:v.reference_number},
                    callback: function() { d.hide(); frm.reload_doc(); }
                });
            }
        });
        d.show();
    }, __("Billing"));
}

// ── Return Deposit (Hotel Manager) ───────────────────────────────────────
function _add_return_deposit_btn(frm) {
    frm.add_custom_button(__("Return Deposit"), function() {
        var d = new frappe.ui.Dialog({
            title: __("Return Excess Deposit"),
            fields: [
                {fieldname:"amount", fieldtype:"Currency", label:__("Return Amount"), reqd:1},
                {fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
                 options:"Cash\nBank Transfer\nCard"},
                {fieldname:"reference_number", fieldtype:"Data", label:__("Reference")}
            ],
            primary_action_label: __("Process Return"),
            primary_action: function(v) {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.return_excess_deposit",
                    args: {folio_name:frm.doc.name, amount:v.amount, payment_mode:v.payment_mode, reference_number:v.reference_number||""},
                    freeze:true,
                    callback: function(r) { d.hide();
                        if(r.message) frappe.show_alert({message:__("Return JE {0} created",[r.message.journal_entry]),indicator:"green"});
                        frm.reload_doc();
                    }
                });
            }
        });
        d.show();
    }, __("Billing"));
}

// ── Sync Reservation Deposits ────────────────────────────────────────────
function _add_sync_deposits_btn(frm) {
    frappe.call({
        method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.get_reservation_deposit_summary",
        args: {folio_name: frm.doc.name},
        callback: function(r) {
            if (!r.message || !r.message.reservation) return;
            var s = r.message;
            if (s.total_deposit_pes === 0) return;
            var label = s.pending_to_sync > 0
                ? __("Sync Reservation Deposit ({0})", [fc(s.pending_to_sync)])
                : __("Reservation Deposit Synced \u2713");
            var btn = frm.add_custom_button(label, function() {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.sync_reservation_deposits_to_folio",
                    args: {folio_name: frm.doc.name}, freeze: true,
                    callback: function() { frm.reload_doc(); }
                });
            }, __("Billing"));
            if (s.pending_to_sync > 0) btn.addClass("btn-warning");
        }
    });
}

// ── Void Charge ──────────────────────────────────────────────────────────
function _add_void_charge_btn(frm) {
    frm.add_custom_button(__("Void Charge"), function() {
        var active = (frm.doc.folio_charges || []).filter(function(r){return !r.is_void && !r.is_billed;});
        if (!active.length) { frappe.msgprint(__("No voidable charges.")); return; }
        var items = active.map(function(r){return {label: r.posting_date + " | " + r.description + " | " + fc(r.amount), value: r.name};});
        var d = new frappe.ui.Dialog({
            title: __("Void Charge"),
            fields: [
                {fieldname:"row_select", fieldtype:"Select", label:__("Charge to Void"), reqd:1,
                 options: items.map(function(i){return i.label;}).join("\n")},
                {fieldname:"void_reason", fieldtype:"Data", label:__("Reason"), reqd:1}
            ],
            primary_action_label: __("Void"),
            primary_action: function(v) {
                var idx = items.findIndex(function(i){return i.label === v.row_select;});
                var rn  = items[idx] ? items[idx].value : null;
                if (!rn) return;
                frappe.call({
                    method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.void_charge",
                    args:{folio_name:frm.doc.name, row_name:rn, void_reason:v.void_reason},
                    callback:function(){d.hide(); frm.reload_doc();}
                });
            }
        });
        d.show();
    }, __("Billing"));
}

// ── Account Statement — always visible ───────────────────────────────────
function _add_statement_btn(frm) {
    frm.add_custom_button(__("Account Statement"), function() {
        frappe.call({
            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.get_folio_summary",
            args: {folio_name: frm.doc.name},
            callback: function(r) {
                if (!r.message) return;
                var s = r.message;
                var statusBadge = frm.doc.folio_status !== "Open"
                    ? "<div style='background:#e2e8f0;padding:6px 12px;border-radius:4px;margin-bottom:10px;font-size:11px;color:#4a5568'>Folio Status: <b>" + frm.doc.folio_status + "</b></div>"
                    : "";
                var chargeRows = "";
                (s.charges_breakdown || []).forEach(function(c) {
                    chargeRows += "<tr><td style='padding:5px 8px'>" + c.category + "</td>"
                        + "<td style='text-align:right;padding:5px 8px;font-weight:500'>" + fc(flt(c.amount)) + "</td>"
                        + "<td style='text-align:right;padding:5px 8px;color:#718096;font-size:11px'>" + (c.count||0) + " line(s)</td></tr>";
                });
                var unbilledAmt = flt(s.unbilled_total || 0);
                var unbilledRow = unbilledAmt > 0.01
                    ? "<tr style='background:#fffbeb;border-top:1px dashed #f6ad55'>"
                      + "<td style='padding:5px 8px;color:#744210' colspan='2'>&#9888; Unbilled</td>"
                      + "<td style='text-align:right;padding:5px 8px;color:#c05621;font-weight:bold'>" + fc(unbilledAmt) + "</td></tr>"
                    : "";
                var ledgerTableHtml = "";
                var ledger = s.ledger || [];
                if (ledger.length) {
                    var lrows = "";
                    ledger.forEach(function(e) {
                        var bg = (e.type === "Payment Entry" || e.is_return) ? "background:#f0fff4" : "";
                        var bal = flt(e.balance);
                        var bCol = bal > 0.01 ? "#c53030" : bal < -0.01 ? "#276749" : "#4a5568";
                        var refLink = e.type === "Sales Invoice"
                            ? "<a href='/app/sales-invoice/" + e.name + "' target='_blank' style='color:#3182ce'>" + e.name + "</a>"
                              + (e.is_return ? " <span style='background:#c6f6d5;color:#276749;padding:1px 4px;border-radius:2px;font-size:10px'>CR</span>" : "")
                            : "<a href='/app/payment-entry/" + e.name + "' target='_blank' style='color:#276749'>" + e.name + "</a>";
                        var balCell = fc(Math.abs(bal)) + (bal < -0.01 ? " CR" : "");
                        lrows += "<tr style='" + bg + ";border-bottom:1px solid #f0f0f0'>"
                            + "<td style='padding:5px 8px;color:#718096'>" + (e.date||"") + "</td>"
                            + "<td style='padding:5px 8px'>" + refLink + "</td>"
                            + "<td style='padding:5px 8px;color:#4a5568'>" + (e.description||"") + "</td>"
                            + "<td style='text-align:right;padding:5px 8px;color:#c53030;font-weight:500'>" + (e.debit > 0 ? fc(e.debit) : "") + "</td>"
                            + "<td style='text-align:right;padding:5px 8px;color:#276749;font-weight:500'>" + (e.credit > 0 ? fc(e.credit) : "") + "</td>"
                            + "<td style='text-align:right;padding:5px 8px;font-weight:600;color:" + bCol + "'>" + balCell + "</td></tr>";
                    });
                    var totD = fc(flt(s.total_debit||0));
                    var totC = fc(flt(s.total_credit||0));
                    ledgerTableHtml = "<table style='width:100%;border-collapse:collapse;font-size:12px'>"
                        + "<thead><tr style='background:#edf2f7;font-weight:600;font-size:11px'>"
                        + "<th style='padding:6px 8px;text-align:left'>Date</th>"
                        + "<th style='padding:6px 8px;text-align:left'>Reference</th>"
                        + "<th style='padding:6px 8px;text-align:left'>Description</th>"
                        + "<th style='padding:6px 8px;text-align:right;color:#c53030'>Debit</th>"
                        + "<th style='padding:6px 8px;text-align:right;color:#276749'>Credit</th>"
                        + "<th style='padding:6px 8px;text-align:right'>Balance</th>"
                        + "</tr></thead><tbody>" + lrows + "</tbody>"
                        + "<tfoot style='border-top:2px solid #cbd5e0;background:#f7fafc;font-weight:bold'>"
                        + "<tr><td colspan='3' style='padding:6px 8px'>Totals</td>"
                        + "<td style='text-align:right;padding:6px 8px;color:#c53030'>" + totD + "</td>"
                        + "<td style='text-align:right;padding:6px 8px;color:#276749'>" + totC + "</td>"
                        + "<td></td></tr></tfoot></table>";
                } else {
                    ledgerTableHtml = "<p style='color:#a0aec0;font-size:12px'>No financial transactions yet.</p>";
                }
                var trueBalance = flt(s.true_balance || 0);
                var balColor = trueBalance > 0.01 ? "#c53030" : "#276749";
                var billToHtml = (s.billing_customer && s.billing_customer !== s.customer)
                    ? "<div style='margin-top:6px'><span style='background:#feebc8;color:#c05621;padding:2px 8px;border-radius:3px;font-size:11px'>Billed to: " + s.billing_customer + "</span></div>" : "";

                frappe.msgprint({title:__("Guest Account Statement"), wide:true, message:
                    "<div style='font-family:Arial,sans-serif;font-size:13px'>"
                    + statusBadge
                    + "<div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;gap:12px'>"
                    + "<div><div style='font-size:16px;font-weight:bold'>" + (s.guest||"") + "</div>"
                    + "<div style='color:#718096;margin-top:2px'>Room " + (s.room||"") + " | " + (s.arrival||"") + " &rarr; " + (s.departure||"") + " (" + (s.nights||0) + " nights)</div>"
                    + billToHtml + "</div>"
                    + "<div style='text-align:center;background:#f0fff4;border:2px solid #9ae6b4;border-radius:8px;padding:12px 20px;min-width:160px'>"
                    + "<div style='font-size:10px;color:#276749;text-transform:uppercase;letter-spacing:1px;font-weight:600'>Total Charges</div>"
                    + "<div style='font-size:26px;font-weight:bold;color:#276749;margin-top:2px'>" + fc(flt(s.total_charges||0)) + "</div>"
                    + (unbilledAmt > 0.01 ? "<div style='font-size:10px;color:#c05621;margin-top:2px'>" + fc(unbilledAmt) + " unbilled</div>" : "")
                    + "</div></div>"
                    + "<div style='margin-bottom:16px'>"
                    + "<div style='font-size:11px;font-weight:700;color:#4a5568;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;padding-bottom:4px;border-bottom:2px solid #e2e8f0'>Charges Breakdown</div>"
                    + "<table style='width:100%;border-collapse:collapse'><tbody>" + chargeRows + unbilledRow + "</tbody>"
                    + "<tfoot><tr style='border-top:1px solid #e2e8f0;font-weight:bold;background:#f7fafc'>"
                    + "<td style='padding:6px 8px'>Total</td><td style='text-align:right;padding:6px 8px'>" + fc(flt(s.total_charges||0)) + "</td><td></td></tr></tfoot></table></div>"
                    + "<div style='margin-bottom:12px'>"
                    + "<div style='font-size:11px;font-weight:700;color:#4a5568;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;padding-bottom:4px;border-bottom:2px solid #e2e8f0'>Financial Transactions</div>"
                    + ledgerTableHtml + "</div>"
                    + "<div style='background:#fff5f5;border:1px solid #fed7d7;border-radius:6px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center'>"
                    + "<div><div style='font-weight:700;font-size:14px'>Outstanding Balance</div>"
                    + "<div style='color:#718096;font-size:11px;margin-top:2px'>Debit " + fc(flt(s.total_debit||0)) + " - Credit " + fc(flt(s.total_credit||0)) + "</div></div>"
                    + "<div style='font-size:24px;font-weight:bold;color:" + balColor + "'>" + fc(Math.abs(trueBalance)) + (trueBalance < -0.01 ? " CR" : "") + "</div>"
                    + "</div></div>"
                });
            }
        });
    }, __("Billing"));
}

function fc(v) { return parseFloat(v || 0).toLocaleString("en", {minimumFractionDigits: 2}); }
function flt(v) { return parseFloat(v || 0); }
