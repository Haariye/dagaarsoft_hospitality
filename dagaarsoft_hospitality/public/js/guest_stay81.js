// Guest Stay JS v6.0 — Redesigned
frappe.ui.form.on("Guest Stay", {
    onload(frm) {
        dh_apply_property(frm);
        const d = (frappe.boot && frappe.boot.hospitality_defaults) || {};
        if (frm.doc.docstatus === 0) {
            if (!frm.doc.property && d.property) frm.set_value("property", d.property);
            if (!frm.doc.rate_plan && d.rate_plan) frm.set_value("rate_plan", d.rate_plan);
        }
    },
    refresh(frm) {
        _set_status(frm); _set_filters(frm);
        if (frm.doc.docstatus !== 1) return;
        const s = frm.doc.stay_status;
        const isManager = frappe.user_roles.includes("Hotel Manager");

        if (s === "Expected") {
            frm.add_custom_button(__("✅ Check In"), () => _check_in(frm)).addClass("btn-success");
            frm.add_custom_button(__("Waive Deposit"), () => _waive_deposit(frm), __("Actions"));
        }
        if (s === "Checked In") {
            frm.add_custom_button(__("🧾 View Folio"), () =>
                frappe.set_route("Form","Guest Folio",frm.doc.guest_folio)).addClass("btn-primary");

            // Hotel Manager only buttons
            if (isManager) {
                frm.add_custom_button(__("Post Room Charges"), () => _post_room_charges(frm), __("Billing"));
                frm.add_custom_button(__("Generate Invoice"), () => _generate_invoice(frm), __("Billing"));
                frm.add_custom_button(__("Charge to Credit"), () => _charge_to_credit(frm), __("Billing"));
                frm.add_custom_button(__("Return Deposit"), () => _return_deposit(frm), __("Billing"));
            }

            frm.add_custom_button(__("Move Room"), () =>
                frappe.new_doc("Room Move",{guest_stay:frm.doc.name}), __("Actions"));
            frm.add_custom_button(__("Extend Stay"), () => _extend_stay(frm), __("Actions"));
            frm.add_custom_button(__("Transfer Billing"), () => _transfer_billing(frm), __("Actions"));
            frm.add_custom_button(__("Change Guest"), () => _change_customer(frm), __("Actions"));
            frm.add_custom_button(__("🚪 Check Out"), () => _checkout(frm)).addClass("btn-danger");
        }
        if (frm.doc.guest_folio)
            frm.add_custom_button(__("View Folio"),
                () => frappe.set_route("Form","Guest Folio",frm.doc.guest_folio), __("Links"));
        if (frm.doc.reservation)
            frm.add_custom_button(__("View Reservation"),
                () => frappe.set_route("Form","Reservation",frm.doc.reservation), __("Links"));

        // Cascade cancel — Hotel Manager only
        if (isManager) {
            frm.add_custom_button(__("Cancel All Linked"), () => {
                frappe.confirm(
                    __("This will cancel ALL linked Payment Entries, Sales Invoices, Deposits, Folio, and this Stay. This cannot be undone. Proceed?"),
                    () => {
                        frappe.call({
                            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.cascade_cancel_stay",
                            args: {stay_name: frm.doc.name},
                            freeze: true, freeze_message: __("Cancelling all linked documents..."),
                            callback(r) {
                                if (r.message) frappe.show_alert({
                                    message: __("{0} documents cancelled.", [r.message.count]),
                                    indicator: "orange"
                                });
                                frm.reload_doc();
                            }
                        });
                    }
                );
            }, __("Actions")).addClass("btn-danger");
        }
    },
    property(frm) { _set_filters(frm); _apply_prop_defaults(frm); },
    room_type(frm) { _set_filters(frm); _fetch_rate(frm); },
    room(frm) {
        if (!frm.doc.room) return;
        frappe.db.get_value("Room", frm.doc.room, ["room_type","property"], r => {
            if (!r) return;
            if (!frm.doc.room_type && r.room_type) frm.set_value("room_type", r.room_type);
            if (!frm.doc.property && r.property) frm.set_value("property", r.property);
            _fetch_rate(frm);
        });
    },
    rate_plan(frm) { _fetch_rate(frm); },
    billing_instruction(frm) { _set_bill_to_filter(frm); }
});

function _apply_prop_defaults(frm) {
    if (!frm.doc.property) return;
    frappe.db.get_value("Property", frm.doc.property,
        ["default_rate_plan","default_meal_plan"], r => {
        if (!r) return;
        if (!frm.doc.rate_plan && r.default_rate_plan)
            frm.set_value("rate_plan", r.default_rate_plan);
    });
}
function _set_bill_to_filter(frm) {
    const map = {"Charge to Company":"Commercial","Charge to Travel Agent":"Travel Agency"};
    const group = map[frm.doc.billing_instruction];
    if (group) frm.set_query("billing_customer", () => ({filters:{customer_group:group}}));
}
function _set_filters(frm) {
    if (!frm.doc.property) return;
    frm.set_query("room_type", () => ({filters:{property:frm.doc.property}}));
    frm.set_query("room", () => ({filters:{
        property:frm.doc.property,
        room_type:frm.doc.room_type||undefined,
        is_active:1, is_out_of_order:0
    }}));
    frm.set_query("rate_plan", () => ({filters:{property:frm.doc.property,is_active:1}}));
}
function _fetch_rate(frm) {
    if (!frm.doc.room_type) return;
    if (frm.doc.rate_plan) {
        frappe.db.get_value("Rate Plan Line",
            {parent:frm.doc.rate_plan,room_type:frm.doc.room_type}, "rate", r => {
            if (r && parseFloat(r.rate) > 0) frm.set_value("nightly_rate", r.rate);
            else _bar_rate(frm);
        });
    } else _bar_rate(frm);
}
function _bar_rate(frm) {
    frappe.db.get_value("Room Type", frm.doc.room_type, "bar_rate", r => {
        if (r && parseFloat(r.bar_rate) > 0) frm.set_value("nightly_rate", r.bar_rate);
    });
}
function _set_status(frm) {
    const c = {Expected:"blue","Checked In":"green","Checked Out":"grey",
               Cancelled:"red","No Show":"orange"};
    frm.page.set_indicator(__(frm.doc.stay_status||"Draft"), c[frm.doc.stay_status]||"grey");
    if (frm.doc.billing_customer && frm.doc.billing_customer !== frm.doc.customer)
        frm.dashboard.add_indicator(__("Sponsored: {0}",[frm.doc.billing_customer]),"orange");
}

// ── Check In ─────────────────────────────────────────────────────────────
function _check_in(frm) {
    if (!frm.doc.room) { frappe.msgprint(__("Room is required.")); return; }
    frappe.confirm(__("Check in {0} to Room {1}? First night charge will be posted.",[frm.doc.guest_name,frm.doc.room]), () => {
        frappe.call({
            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.do_checkin",
            args:{stay_name:frm.doc.name}, freeze:true, freeze_message:__("Checking in..."),
            callback(){frm.reload_doc();}
        });
    });
}

function _waive_deposit(frm) {
    frappe.prompt({fieldname:"reason",fieldtype:"Data",label:__("Reason"),reqd:1}, v => {
        frappe.call({
            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.waive_deposit",
            args:{stay_name:frm.doc.name,reason:v.reason},
            callback(){frm.reload_doc();}
        });
    }, __("Waive Deposit"), __("Waive"));
}

// ── Post Room Charges (Hotel Manager only) ───────────────────────────────
function _post_room_charges(frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.calculate_room_charges_for_stay",
        args:{guest_stay_name:frm.doc.name},
        callback(r) {
            if (!r.message) return;
            var res = r.message;
            if (res.pending_count === 0) {
                frappe.msgprint({title:__("Already Charged"),
                    message:__("All {0} night(s) already posted with invoices.",[res.already_posted_count]),
                    indicator:"orange"});
                return;
            }
            frappe.confirm(
                __("{0} pending night(s) at {1}/night. Post charges + create invoices?",[res.pending_count, fc(res.nightly_rate)]),
                () => {
                    frappe.call({
                        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.post_all_room_charges",
                        args:{guest_stay_name:frm.doc.name}, freeze:true,
                        callback(r2){
                            if(r2.message) frappe.show_alert({message:r2.message.message,indicator:"green"});
                            frm.reload_doc();
                        }
                    });
                }
            );
        }
    });
}

// ── Generate Invoice (Hotel Manager only — unified button) ───────────────
function _generate_invoice(frm) {
    if (!frm.doc.guest_folio) { frappe.msgprint(__("No folio linked.")); return; }
    var d = new frappe.ui.Dialog({
        title: __("Generate Invoice for Unbilled Charges"),
        fields: [
            {fieldname:"discount_pct", fieldtype:"Float", label:__("Discount %"), default:0},
            {fieldname:"discount_amount", fieldtype:"Currency", label:__("Discount Amount"), default:0}
        ],
        primary_action_label: __("Generate & Submit"),
        primary_action(v) {
            frappe.call({
                method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.generate_folio_invoice",
                args:{folio_name:frm.doc.guest_folio,
                      discount_pct:v.discount_pct||0, discount_amount:v.discount_amount||0},
                freeze:true,
                callback(r){ d.hide();
                    if(r.message) frappe.show_alert({message:__("Invoice {0} created",[r.message]),indicator:"green"});
                    frm.reload_doc();
                }
            });
        }
    });
    d.show();
}

// ── Charge to Credit (Hotel Manager only) ────────────────────────────────
function _charge_to_credit(frm) {
    if (!frm.doc.guest_folio) { frappe.msgprint(__("No folio linked.")); return; }
    var d = new frappe.ui.Dialog({
        title: __("Charge to Credit — Manager Authorization"),
        fields: [
            {fieldtype:"HTML", options:
                "<div style='background:#fff3cd;padding:12px;border-radius:6px;margin-bottom:12px'>"
                + "<p>This reads the <b>real outstanding</b> from all Sales Invoices linked to this folio.</p>"
                + "<p>A Journal Entry will be created so the guest can checkout with an unpaid balance.</p>"
                + "</div>"
            },
            {fieldname:"reason", fieldtype:"Small Text", label:__("Reason (required)"), reqd:1}
        ],
        primary_action_label: __("Authorize"),
        primary_action(v) {
            frappe.call({
                method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.charge_to_credit",
                args:{folio_name:frm.doc.guest_folio, reason:v.reason},
                freeze:true,
                callback(r){ d.hide();
                    if(r.message) frappe.show_alert({
                        message:__("JE {0} created. Amount: {1}",[r.message.journal_entry, fc(r.message.amount)]),
                        indicator:"green"});
                    frm.reload_doc();
                }
            });
        }
    });
    d.show();
}

// ── Return Deposit (Hotel Manager only) ──────────────────────────────────
function _return_deposit(frm) {
    if (!frm.doc.guest_folio) { frappe.msgprint(__("No folio linked.")); return; }
    var d = new frappe.ui.Dialog({
        title: __("Return Excess Deposit"),
        fields: [
            {fieldname:"amount", fieldtype:"Currency", label:__("Return Amount"), reqd:1},
            {fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
             options:"Cash\nBank Transfer\nCard"},
            {fieldname:"reference_number", fieldtype:"Data", label:__("Reference")}
        ],
        primary_action_label: __("Process Return"),
        primary_action(v) {
            frappe.call({
                method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.return_excess_deposit",
                args:{folio_name:frm.doc.guest_folio, amount:v.amount,
                      payment_mode:v.payment_mode, reference_number:v.reference_number||""},
                freeze:true,
                callback(r){ d.hide();
                    if(r.message) frappe.show_alert({
                        message:__("Deposit return JE {0} created.",[r.message.journal_entry]),
                        indicator:"green"});
                    frm.reload_doc();
                }
            });
        }
    });
    d.show();
}

// ── Extend Stay ──────────────────────────────────────────────────────────
function _extend_stay(frm) {
    var d = new frappe.ui.Dialog({
        title: __('Extend Stay'),
        fields: [
            {fieldtype:"HTML", options:
                "<p>Current departure: <b>" + (frm.doc.departure_date||"") + "</b> | Nights: <b>" + (frm.doc.num_nights||0) + "</b></p>"
            },
            {fieldname:"new_departure_date", fieldtype:"Date", label:__("New Departure Date"), reqd:1,
             default: frappe.datetime.add_days(frm.doc.departure_date, 1)},
            {fieldname:"reason", fieldtype:"Small Text", label:__("Reason")}
        ],
        primary_action_label: __("Extend"),
        primary_action(v) {
            frappe.call({
                method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.extend_stay",
                args:{stay_name:frm.doc.name, new_departure_date:v.new_departure_date, reason:v.reason||""},
                freeze:true,
                callback(r){ d.hide();
                    if(r.message) frappe.show_alert({message:__("Extended +{0} nights",[r.message.added_nights]),indicator:"green"});
                    frm.reload_doc();
                }
            });
        }
    });
    d.show();
}

// ── Checkout ─────────────────────────────────────────────────────────────
function _checkout(frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.validate_checkout_billing",
        args:{guest_stay_name:frm.doc.name},
        callback(r) {
            const check = r.message || {};
            if (check.is_sponsored) {
                const warnHtml = (check.warnings||[]).length
                    ? "<div style='background:#fff3cd;padding:8px;border-radius:4px;margin-top:8px'>"
                      + (check.warnings||[]).join("<br>") + "</div>" : "";
                frappe.confirm(
                    "<p><b>Sponsored Checkout</b><br>Billing to: <b>"+(frm.doc.billing_customer||"Sponsor")+"</b></p>"
                    + warnHtml + "<p>Proceed?</p>", () => _do_checkout(frm.doc.name, false, null, frm));
                return;
            }
            // Unbilled room charges — must bill first
            if (check.has_unbilled_room_charges && !check.can_checkout) {
                var dd = new frappe.ui.Dialog({
                    title: __("Unbilled Room Charges"),
                    fields: [
                        {fieldtype:"HTML", options:
                            "<div style='background:#fff3cd;padding:12px;border-radius:6px'>"
                            + "<p><b>" + (check.unbilled_room_nights||0) + " night(s)</b> of room charges are unbilled.</p>"
                            + "<p>Amount: <b>" + fc(check.unbilled_room_amount||0) + "</b></p>"
                            + "<p>You must generate a Sales Invoice for these room charges before checkout.</p>"
                            + "</div>"},
                        {fieldname:"discount_pct", fieldtype:"Float", label:__("Discount %"), default:0},
                        {fieldname:"discount_amount", fieldtype:"Currency", label:__("Discount Amount"), default:0}
                    ],
                    primary_action_label: __("Bill & Continue to Checkout"),
                    primary_action(v) {
                        frappe.call({
                            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.generate_folio_invoice",
                            args:{folio_name:frm.doc.guest_folio,
                                  discount_pct:v.discount_pct||0, discount_amount:v.discount_amount||0},
                            freeze:true, freeze_message:__("Generating invoice..."),
                            callback(r2) {
                                dd.hide();
                                if (r2.message) {
                                    frappe.show_alert({message:__("Invoice {0} created. Now checking out...",[r2.message]),indicator:"green"});
                                    // Re-validate and checkout
                                    setTimeout(function(){ _checkout(frm); }, 1000);
                                }
                            }
                        });
                    }
                });
                dd.show(); return;
            }
            if (check.is_early_checkout && check.early_checkout_info && !check.can_checkout) {
                var info = check.early_checkout_info;
                var dd2 = new frappe.ui.Dialog({
                    title: __("Early Checkout — Manager Required"),
                    fields: [
                        {fieldtype:"HTML", options:
                            "<div style='background:#fff3cd;padding:12px;border-radius:6px'>"
                            + "<p>" + info.message + "</p>"
                            + (check.issues.length ? "<p style='color:red'><b>Issues:</b><br>" + check.issues.join("<br>") + "</p>" : "")
                            + "</div>"},
                        {fieldname:"adjustment_note", fieldtype:"Small Text", label:__("Manager Note"), reqd:1}
                    ],
                    primary_action_label: __("Force Checkout"),
                    primary_action(v) {
                        if (!frappe.user_roles.includes("Hotel Manager")) {
                            frappe.msgprint(__("Only Hotel Manager can force checkout.")); return;
                        }
                        dd2.hide(); _do_checkout(frm.doc.name, true, v.adjustment_note, frm);
                    }
                });
                dd2.show(); return;
            }
            if (!check.can_checkout) {
                frappe.msgprint({title:__("Cannot Check Out"),
                    message:"<b>Issues:</b><br>"+(check.issues||[]).join("<br>"),
                    indicator:"red"}); return;
            }
            frappe.confirm(__("Check out {0} from Room {1}?",[frm.doc.guest_name,frm.doc.room]), () => {
                _do_checkout(frm.doc.name, false, null, frm);
            });
        }
    });
}

function _transfer_billing(frm) {
    var d = new frappe.ui.Dialog({
        title: __('Transfer Billing'),
        fields: [
            {fieldname:'billing_customer', fieldtype:'Link', options:'Customer',
             label:__('Bill To'), reqd:1, default: frm.doc.billing_customer || ''},
            {fieldname:'transfer_mode', fieldtype:'Select', label:__('Apply To'),
             options:'from_now\nall', default:'from_now'},
        ],
        primary_action_label: __('Transfer'),
        primary_action(v) {
            frappe.call({
                method:'dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.transfer_billing',
                args:{stay_name:frm.doc.name, billing_customer:v.billing_customer, transfer_mode:v.transfer_mode},
                callback(){d.hide(); frm.reload_doc();}
            });
        }
    });
    d.show();
}

function _change_customer(frm) {
    frappe.prompt({fieldname:'new_customer', fieldtype:'Link', options:'Customer',
        label:__('New Guest'), reqd:1}, v => {
        frappe.confirm(__('Update guest and cascade to linked docs?'), () => {
            frappe.call({
                method:'dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.update_customer_cascade',
                args:{stay_name:frm.doc.name, new_customer:v.new_customer},
                freeze:true, callback(){frm.reload_doc();}
            });
        });
    }, __('Change Guest'), __('Update'));
}

function _do_checkout(stay_name, force, adjustment_note, frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.do_checkout",
        args:{stay_name, force_checkout:force?1:0, adjustment_note:adjustment_note||""},
        freeze:true, freeze_message:__("Checking out..."),
        callback(){frm.reload_doc();}
    });
}

function fc(v) { return parseFloat(v||0).toLocaleString("en",{minimumFractionDigits:2}); }
