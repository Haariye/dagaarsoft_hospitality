// Guest Folio JS v5
frappe.ui.form.on("Guest Folio", {
    refresh(frm) {
        _setup_indicators(frm);
        _lock_charge_table(frm);
        if (frm.doc.docstatus === 1 && frm.doc.folio_status === "Open") {
            _add_room_charge_btn(frm);
            _add_billing_btns(frm);
        }
        if (frm.doc.sales_invoice) frm.add_custom_button(__("View Invoice"),
            () => frappe.set_route("Form","Sales Invoice",frm.doc.sales_invoice), __("Links"));
        if (frm.doc.guest_stay) frm.add_custom_button(__("View Stay"),
            () => frappe.set_route("Form","Guest Stay",frm.doc.guest_stay), __("Links"));
    }
});
function _lock_charge_table(frm) {
    const grid = frm.fields_dict.folio_charges && frm.fields_dict.folio_charges.grid;
    if (!grid) return;
    grid.wrapper.find(".grid-add-row,.grid-remove-rows").hide();
    grid.df.cannot_add_rows = true; grid.df.cannot_delete_rows = true;
    try { grid.refresh(); } catch(e) {}
}
function _setup_indicators(frm) {
    const bal = flt(frm.doc.balance_due);
    if (frm.doc.folio_status === "Closed") frm.page.set_indicator(__("Settled"), "green");
    else if (bal < -0.01) frm.page.set_indicator(__("Overpaid " + fc(Math.abs(bal))), "red");
    else if (bal > 0.01) frm.page.set_indicator(__("Balance: " + fc(bal)), "orange");
    else frm.page.set_indicator(__("Open"), "blue");
    if (frm.doc.billing_customer && frm.doc.billing_customer !== frm.doc.customer)
        frm.dashboard.add_indicator(__("Bill To: {0}", [frm.doc.billing_customer]), "orange");
    if (frm.doc.sales_invoice_status) {
        const c = {"Fully Paid \u2713":"green","Unpaid":"red","Overdue":"red","Partly Paid":"orange","Cancelled":"grey"}[frm.doc.sales_invoice_status] || "blue";
        frm.dashboard.add_indicator(__("Invoice: {0}", [frm.doc.sales_invoice_status]), c);
    }
}
function _add_room_charge_btn(frm) {
    frm.add_custom_button(__("Post Room Charges"), () => {
        frappe.call({
            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.calculate_room_charges_for_stay",
            args: {guest_stay_name: frm.doc.guest_stay},
            callback(r) {
                if (!r.message) return;
                const res = r.message;
                if (res.pending_count === 0) {
                    frappe.msgprint({title: __("Already Charged"),
                        message: __("All {0} night(s) already posted.", [res.already_posted_count]),
                        indicator: "orange"});
                    return;
                }
                const rows = res.charges.filter(c => !c.already_posted).map(c =>
                    `<tr><td>${c.date}</td><td style="text-align:right">${fc(c.amount)}</td></tr>`).join("");
                const d = new frappe.ui.Dialog({
                    title: __("Post Room Charges"),
                    fields: [{fieldtype:"HTML", options:
                        `<p>Rate: <b>${fc(res.nightly_rate)}/night</b> | Pending: <b>${res.pending_count}</b></p>
                         <table style="width:100%">${rows}</table>`}],
                    primary_action_label: __("Post {0} Night(s)", [res.pending_count]),
                    primary_action() {
                        frappe.call({
                            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.calculate_and_post_room_charges",
                            args: {folio_name: frm.doc.name}, freeze: true,
                            callback(r2) { d.hide(); if(r2.message) frappe.show_alert({message:r2.message.message,indicator:"green"}); frm.reload_doc(); }
                        });
                    }
                });
                d.show();
            }
        });
    }, __("Billing"));
}
function _add_billing_btns(frm) {
    const bal = flt(frm.doc.balance_due);
    if (!frm.doc.sales_invoice) {
        frm.add_custom_button(__("Generate Invoice"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Generate Sales Invoice"),
                fields: [
                    {fieldname:"info", fieldtype:"HTML", options:
                        `<div style="background:#ebf8ff;padding:10px;border-radius:4px;margin-bottom:8px">
                         ${frm.doc.billing_customer && frm.doc.billing_customer !== frm.doc.customer ?
                           "<p>Bill To: <b>" + frm.doc.billing_customer + "</b></p>" : ""}
                         <p>Total Charges: <b>${fc(frm.doc.total_charges)}</b></p></div>`},
                    {fieldname:"discount_pct", fieldtype:"Float", label:__("Discount %"), default:0},
                    {fieldname:"discount_amount", fieldtype:"Currency", label:__("Discount Amount"), default:0}
                ],
                primary_action_label: __("Generate & Submit"),
                primary_action(v) {
                    frappe.call({
                        method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.generate_invoice",
                        args: {folio_name:frm.doc.name, submit_invoice:1,
                               discount_pct:v.discount_pct||0, discount_amount:v.discount_amount||0},
                        freeze:true, freeze_message:__("Creating invoice..."),
                        callback(r) { d.hide(); if(r.message) frappe.show_alert({message:__("Invoice {0} created",[r.message]),indicator:"green"}); frm.reload_doc(); }
                    });
                }
            });
            d.show();
        }, __("Billing"));
    }
    if (frm.doc.sales_invoice && bal > 0.01) {
        frm.add_custom_button(__("Settle Payment"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Settle Payment - Outstanding: {0}", [fc(bal)]),
                fields: [
                    {fieldname:"amount", fieldtype:"Currency", label:__("Amount"), reqd:1, default:bal},
                    {fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
                     options:"Cash\nCard\nBank Transfer\nOnline\nCity Ledger\nCheque"},
                    {fieldname:"reference_number", fieldtype:"Data", label:__("Reference")}
                ],
                primary_action_label: __("Confirm Payment"),
                primary_action(v) {
                    if (flt(v.amount) <= 0) { frappe.msgprint(__("Amount must be > 0")); return; }
                    frappe.call({
                        method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.settle_with_payment",
                        args: {folio_name:frm.doc.name, amount:v.amount, payment_mode:v.payment_mode, reference_number:v.reference_number},
                        freeze:true, callback() { d.hide(); frm.reload_doc(); }
                    });
                }
            });
            d.show();
        }, __("Billing"));
    }
    frm.add_custom_button(__("Collect Deposit"), () => {
        const d = new frappe.ui.Dialog({
            title: __("Collect Deposit"),
            fields: [
                {fieldname:"amount", fieldtype:"Currency", label:__("Amount"), reqd:1},
                {fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
                 options:"Cash\nCard\nBank Transfer\nOnline\nCheque"},
                {fieldname:"reference_number", fieldtype:"Data", label:__("Reference")}
            ],
            primary_action_label: __("Collect"),
            primary_action(v) {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.collect_deposit",
                    args: {folio_name:frm.doc.name, amount:v.amount, payment_mode:v.payment_mode, reference_number:v.reference_number},
                    callback() { d.hide(); frm.reload_doc(); }
                });
            }
        });
        d.show();
    }, __("Billing"));
    frm.add_custom_button(__("Folio Summary"), () => {
        frappe.call({
            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.get_folio_summary",
            args: {folio_name: frm.doc.name},
            callback(r) {
                if (!r.message) return;
                const s = r.message;
                const rows = (s.charges_breakdown||[]).map(c =>
                    `<tr><td>${c.category}</td><td style="text-align:right">${fc(c.amount)}</td></tr>`).join("");
                const credit = s.balance_due < -0.01 ?
                    `<p style="color:red;font-weight:bold">OVERPAID ${fc(Math.abs(s.balance_due))} - Issue Refund Journal Entry</p>` : "";
                frappe.msgprint({title:__("Folio Summary"), wide:true, message:`
                    <h4>${s.guest||""} - Room ${s.room||""}</h4>
                    <p style="color:#666">${s.arrival||""} to ${s.departure||""} (${s.nights||0} nights)</p>
                    ${s.billing_customer && s.billing_customer!==s.customer ? `<p>Bill To: <b>${s.billing_customer}</b></p>` : ""}
                    <table style="width:100%;border-collapse:collapse;margin-top:8px">
                      <thead><tr style="background:#f0f4f8"><th>Category</th><th style="text-align:right">Amount</th></tr></thead>
                      <tbody>${rows}</tbody>
                      <tfoot>
                        <tr><td><b>Total Charges</b></td><td style="text-align:right"><b>${fc(s.total_charges)}</b></td></tr>
                        <tr><td style="color:green">Payments</td><td style="text-align:right;color:green">(${fc(s.total_payments)})</td></tr>
                        <tr style="background:#fff5f5"><td><b>Balance Due</b></td><td style="text-align:right;font-size:16px"><b style="color:${s.balance_due>0.01?"red":s.balance_due<-0.01?"red":"green"}">${fc(s.balance_due)}</b></td></tr>
                      </tfoot>
                    </table>${credit}`});
            }
        });
    }, __("Billing"));
    frm.add_custom_button(__("Void Charge"), () => {
        const active = (frm.doc.folio_charges||[]).filter(r => !r.is_void && !r.is_billed);
        if (!active.length) { frappe.msgprint(__("No voidable charges.")); return; }
        const items = active.map(r => ({label:`${r.posting_date} | ${r.description} | ${fc(r.amount)}`, value:r.name}));
        const d = new frappe.ui.Dialog({
            title: __("Void Charge"),
            fields: [
                {fieldname:"row_select", fieldtype:"Select", label:__("Charge to Void"), reqd:1,
                 options:items.map(i=>i.label).join("\n")},
                {fieldname:"void_reason", fieldtype:"Data", label:__("Reason"), reqd:1}
            ],
            primary_action_label: __("Void"),
            primary_action(v) {
                const idx = items.findIndex(i => i.label === v.row_select);
                const rn  = items[idx] ? items[idx].value : null;
                if (!rn) return;
                frappe.call({method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_folio.guest_folio.void_charge",
                    args:{folio_name:frm.doc.name, row_name:rn, void_reason:v.void_reason},
                    callback(){d.hide(); frm.reload_doc();}});
            }
        });
        d.show();
    }, __("Billing"));
}
function fc(v) { return parseFloat(v||0).toLocaleString("en",{minimumFractionDigits:2}); }
function flt(v) { return parseFloat(v||0); }
