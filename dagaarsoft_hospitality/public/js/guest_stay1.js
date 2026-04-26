// Guest Stay JS v5.1 - FIX 7,8,9,10,11
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
        if (s === "Expected") {
            frm.add_custom_button(__("✅ Check In"), () => _check_in(frm)).addClass("btn-success");
            frm.add_custom_button(__("Waive Deposit"), () => _waive_deposit(frm), __("Actions"));
        }
        if (s === "Checked In") {
            frm.add_custom_button(__("🧾 View Folio"), () =>
                frappe.set_route("Form","Guest Folio",frm.doc.guest_folio)).addClass("btn-primary");
            frm.add_custom_button(__("Post Room Charges"), () => _post_room_charges(frm), __("Billing"));
            frm.add_custom_button(__("Move Room"), () =>
                frappe.new_doc("Room Move",{guest_stay:frm.doc.name}), __("Actions"));
            frm.add_custom_button(__("Transfer Billing"), () => _transfer_billing(frm), __("Actions"));
            frm.add_custom_button(__("Change Guest"), () => _change_customer(frm), __("Actions"));
            // FIX 8+9: Enhanced checkout button
            frm.add_custom_button(__("🚪 Check Out"), () => _checkout(frm)).addClass("btn-danger");
        }
        if (frm.doc.guest_folio)
            frm.add_custom_button(__("View Folio"),
                () => frappe.set_route("Form","Guest Folio",frm.doc.guest_folio), __("Links"));
        if (frm.doc.reservation)
            frm.add_custom_button(__("View Reservation"),
                () => frappe.set_route("Form","Reservation",frm.doc.reservation), __("Links"));
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
        if (!frm.doc.meal_plan && r.default_meal_plan)
            frm.set_value("meal_plan", r.default_meal_plan);
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
    frm.page.set_indicator(__(frm.doc.stay_status||"Draft"),
        c[frm.doc.stay_status]||"grey");
    if (frm.doc.billing_customer && frm.doc.billing_customer !== frm.doc.customer)
        frm.dashboard.add_indicator(__("Sponsored: {0}",[frm.doc.billing_customer]),"orange");
}
function _check_in(frm) {
    if (!frm.doc.room) { frappe.msgprint(__("Room is required.")); return; }
    frappe.confirm(__("Check in {0} to Room {1}?",[frm.doc.guest_name,frm.doc.room]), () => {
        frappe.call({
            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.do_checkin",
            args:{stay_name:frm.doc.name}, freeze:true,
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
function _post_room_charges(frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.post_all_room_charges",
        args:{guest_stay_name:frm.doc.name}, freeze:true,
        callback(r){
            if(r.message) frappe.show_alert({message:r.message.message,indicator:"green"});
        }
    });
}

// FIX 8+9: Enhanced checkout - shows early checkout dialog if needed
function _checkout(frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.utils.billing.validate_checkout_billing",
        args:{guest_stay_name:frm.doc.name},
        callback(r) {
            const check = r.message || {};

            // FIX 9: Sponsored — show info and confirm directly
            if (check.is_sponsored) {
                const warnHtml = (check.warnings||[]).length
                    ? `<div style="background:#fff3cd;padding:8px;border-radius:4px;margin-top:8px">
                       ${(check.warnings||[]).join("<br>")}</div>` : "";
                frappe.confirm(
                    `<p><b>Sponsored Checkout</b><br>Billing to: <b>${frm.doc.billing_customer||"Sponsor"}</b></p>`
                    + warnHtml + "<p>Proceed with checkout?</p>", () => {
                    _do_checkout(frm.doc.name, false, null, frm);
                });
                return;
            }

            // FIX 8: Early checkout with manager adjustment dialog
            if (check.is_early_checkout && check.early_checkout_info) {
                const info = check.early_checkout_info;
                if (!check.can_checkout) {
                    // Issues exist AND it's early — give manager override
                    const d = new frappe.ui.Dialog({
                        title: __("Early Checkout — Manager Adjustment Required"),
                        fields: [
                            {fieldtype:"HTML", options:`
                              <div style="background:#fff3cd;padding:12px;border-radius:6px;margin-bottom:12px">
                                <h5 style="margin:0 0 6px">⚠ Early Checkout Details</h5>
                                <p>${info.message}</p>
                                ${check.issues.length ? `<p style="color:red"><b>Issues:</b><br>${check.issues.join("<br>")}</p>` : ""}
                                ${check.warnings.length ? `<p style="color:#856404">${check.warnings.join("<br>")}</p>` : ""}
                              </div>`},
                            {fieldname:"adjustment_note", fieldtype:"Small Text",
                             label:__("Manager Adjustment Note (required for early checkout)"), reqd:1},
                        ],
                        primary_action_label: __("Force Checkout (Hotel Manager)"),
                        primary_action(v) {
                            if (!frappe.user_roles.includes("Hotel Manager")) {
                                frappe.msgprint(__("Only Hotel Manager can force early checkout."));
                                return;
                            }
                            d.hide();
                            _do_checkout(frm.doc.name, true, v.adjustment_note, frm);
                        }
                    });
                    d.show();
                    return;
                }
                // Can checkout, but early — just warn
                frappe.confirm(
                    `<p>${info.message}</p>`
                    + (check.warnings.length ? `<p>${check.warnings.join("<br>")}</p>` : "")
                    + "<p>Proceed with early checkout?</p>", () => {
                    _do_checkout(frm.doc.name, false, null, frm);
                });
                return;
            }

            // Normal checkout
            if (!check.can_checkout) {
                frappe.msgprint({
                    title:__("Cannot Check Out"),
                    message:"<b>Resolve these issues first:</b><br>"+(check.issues||[]).join("<br>"),
                    indicator:"red"});
                return;
            }
            const warnHtml = (check.warnings||[]).length
                ? "<br><br><b style='color:#c05621'>Warnings:</b><br>"+(check.warnings||[]).join("<br>")
                : "";
            frappe.confirm(
                __("Check out {0} from Room {1}?",[frm.doc.guest_name,frm.doc.room]) + warnHtml, () => {
                _do_checkout(frm.doc.name, false, null, frm);
            });
        }
    });
}

function _transfer_billing(frm) {
    const d = new frappe.ui.Dialog({
        title: __('Transfer Billing to Third Party'),
        fields: [
            {fieldname:'billing_customer', fieldtype:'Link', options:'Customer',
             label:__('Bill To (Company / Travel Agency)'), reqd:1,
             default: frm.doc.billing_customer || ''},
            {fieldname:'transfer_mode', fieldtype:'Select',
             label:__('Apply To'),
             options:'from_now\nall',
             default:'from_now',
             description:__('from_now = future charges only | all = include existing unbilled charges')},
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
    frappe.prompt({
        fieldname:'new_customer', fieldtype:'Link', options:'Customer',
        label:__('New Primary Guest Customer'), reqd:1
    }, v => {
        frappe.confirm(
            __('Update guest to {0} and cascade to all related documents (Folio, Deposits, Draft Invoices)?',
                [v.new_customer]),
            () => {
                frappe.call({
                    method:'dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.update_customer_cascade',
                    args:{stay_name:frm.doc.name, new_customer:v.new_customer},
                    freeze:true,
                    callback(r){
                        if(r.message) frappe.show_alert({
                            message:__('Updated {0} document(s)',[r.message.changed]),
                            indicator:'green'});
                        frm.reload_doc();
                    }
                });
            }
        );
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