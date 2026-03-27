// Reservation JS v4 — Full availability popup, room auto-populate, deposit gate, filters
frappe.ui.form.on("Reservation", {
    refresh(frm) {
        dh_apply_property(frm);
        _set_status(frm);
        if (frm.doc.docstatus === 1) {
            let s = frm.doc.reservation_status;
            if (s === "Confirmed") {
                // Show check-in button only if no stay yet
                let has_stay = false;
                frappe.db.get_value("Guest Stay", {reservation: frm.doc.name, stay_status: ["!=","Cancelled"]}, "name", r => {
                    if (r && r.name) {
                        frm.page.set_indicator(__("Stay Created"), "green");
                    } else {
                        frm.add_custom_button(__("✅ Create Guest Stay & Check In"), () => {
                            _create_stay(frm);
                        }).css("background","#48bb78").css("color","white").css("font-weight","bold");
                    }
                });
                frm.add_custom_button(__("💰 Record / Add Deposit"), () => {
                    _deposit_dialog(frm);
                }, __("Billing"));
                frm.add_custom_button(__("🔄 Refresh Deposit Status"), () => {
                    frappe.call({method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.hotel_deposit.hotel_deposit.update_reservation_deposit_status", args:{reservation_name: frm.doc.name}, callback(){frm.reload_doc();}});
                }, __("Billing"));
            }
            frm.add_custom_button(__("Guest Stays"), () => {
                frappe.set_route("List","Guest Stay",{reservation:frm.doc.name});
            }, __("Links"));
            if (frm.doc.hotel_deposit) {
                frm.add_custom_button(__("View Deposit"), () => {
                    frappe.set_route("Form","Hotel Deposit",frm.doc.hotel_deposit);
                }, __("Links"));
            }
        }
        // Availability popup auto on draft if dates set
        if (frm.doc.docstatus === 0 && frm.doc.property && frm.doc.arrival_date && frm.doc.departure_date) {
            frm.add_custom_button(__("🔍 Check Availability & Assign Rooms"), () => {
                _availability_popup(frm);
            }).css("background","#4299e1").css("color","white");
        }
    },

    property(frm) { _set_room_type_filters(frm); },
    arrival_date(frm) { _calc_nights(frm); _suggest_availability(frm); },
    departure_date(frm) { _calc_nights(frm); _suggest_availability(frm); },
    rate_plan(frm) { _fetch_rates_for_lines(frm); },
});

frappe.ui.form.on("Reservation Room Line", {
    room_type(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.room_type || !frm.doc.property) return;
        // Filter rooms to this property+type
        frm.fields_dict.reservation_rooms.grid.get_field("room").get_query = function(doc, cdt2, cdn2) {
            let r2 = locals[cdt2][cdn2];
            return { filters: { property: doc.property, room_type: r2.room_type, is_active:1, is_out_of_order:0 } };
        };
        // Auto-fetch rate
        _fetch_rate_for_row(frm, cdt, cdn);
    },
    room(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.room) return;
        frappe.db.get_value("Room", row.room, ["room_status","room_type"], v => {
            if (v) {
                frappe.model.set_value(cdt, cdn, "room_status", v.room_status);
                if (!row.room_type) frappe.model.set_value(cdt, cdn, "room_type", v.room_type);
                _fetch_rate_for_row(frm, cdt, cdn);
            }
        });
    }
});

function _set_room_type_filters(frm) {
    frm.fields_dict.reservation_rooms.grid.get_field("room_type").get_query = function() {
        return { filters: { property: frm.doc.property } };
    };
    frm.fields_dict.reservation_rooms.grid.get_field("room").get_query = function(doc, cdt, cdn) {
        let row = locals[cdt][cdn];
        return { filters: { property: doc.property, room_type: row.room_type||undefined, is_active:1, is_out_of_order:0 } };
    };
}

function _calc_nights(frm) {
    if (frm.doc.arrival_date && frm.doc.departure_date) {
        let n = frappe.datetime.get_day_diff(frm.doc.departure_date, frm.doc.arrival_date);
        frm.set_value("num_nights", n > 0 ? n : 0);
    }
}

function _suggest_availability(frm) {
    if (frm.doc.property && frm.doc.arrival_date && frm.doc.departure_date && frm.doc.docstatus === 0) {
        setTimeout(() => _availability_popup(frm), 500);
    }
}

function _fetch_rate_for_row(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row.room_type) return;
    let rate_plan = frm.doc.rate_plan;
    if (!rate_plan) {
        frappe.db.get_value("Property", frm.doc.property, "default_rate_plan", r => {
            if (r) rate_plan = r.default_rate_plan;
            _do_fetch_rate(cdt, cdn, row.room_type, rate_plan);
        });
    } else {
        _do_fetch_rate(cdt, cdn, row.room_type, rate_plan);
    }
}

function _do_fetch_rate(cdt, cdn, room_type, rate_plan) {
    if (rate_plan) {
        frappe.call({
            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.rate_plan.rate_plan.get_rate_for_room_type",
            args: { rate_plan, room_type },
            callback(r) {
                if (r.message) frappe.model.set_value(cdt, cdn, "rate", r.message);
                else _fallback_bar_rate(cdt, cdn, room_type);
            }
        });
    } else {
        _fallback_bar_rate(cdt, cdn, room_type);
    }
}

function _fallback_bar_rate(cdt, cdn, room_type) {
    frappe.db.get_value("Room Type", room_type, "bar_rate", r => {
        if (r && r.bar_rate) frappe.model.set_value(cdt, cdn, "rate", r.bar_rate);
    });
}

function _fetch_rates_for_lines(frm) {
    (frm.doc.reservation_rooms || []).forEach((row, i) => {
        if (row.room_type) {
            _do_fetch_rate("Reservation Room Line", row.name, row.room_type, frm.doc.rate_plan);
        }
    });
}

function _availability_popup(frm) {
    if (!frm.doc.property || !frm.doc.arrival_date || !frm.doc.departure_date) {
        frappe.msgprint(__("Please fill Property, Arrival and Departure dates first."));
        return;
    }
    let nights = frappe.datetime.get_day_diff(frm.doc.departure_date, frm.doc.arrival_date);
    if (nights <= 0) return;

    // Fetch all room types for this property
    frappe.call({
        method: "frappe.client.get_list",
        args: { doctype:"Room Type", filters:{property:frm.doc.property}, fields:["name","room_type_name","bar_rate","max_occupancy","bed_type"], limit:50 },
        callback(rt_res) {
            let room_types = rt_res.message || [];
            // For each type, check availability
            let checks = room_types.map(rt =>
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.reservation.reservation.get_available_rooms",
                    args: { property:frm.doc.property, room_type:rt.name, arrival_date:frm.doc.arrival_date, departure_date:frm.doc.departure_date, exclude_reservation:frm.doc.name||"" }
                })
            );
            Promise.all(checks).then(results => {
                let html = `<div style="font-family:Arial;padding:10px">
                  <h4 style="color:#2d3748">Available Rooms — ${frm.doc.arrival_date} → ${frm.doc.departure_date} (${nights} nights)</h4>`;
                let any = false;
                room_types.forEach((rt, i) => {
                    let rooms = (results[i].message || []);
                    if (!rooms.length) return;
                    any = true;
                    html += `<div style="margin-bottom:16px">
                      <h5 style="color:#2b6cb0;margin-bottom:8px">${rt.room_type_name||rt.name}
                        <span style="font-size:12px;color:#718096">${rt.bed_type||""} | Max ${rt.max_occupancy||"?"} guests</span>
                        <span style="float:right;color:#276749;font-weight:bold">Rate: ${fmt_cur(rt.bar_rate)}/night → Total: ${fmt_cur(rt.bar_rate*nights)}</span>
                      </h5>
                      <div style="display:flex;flex-wrap:wrap;gap:8px">`;
                    rooms.forEach(r => {
                        let bg = r.room_status === "Vacant Clean" ? "#f0fff4" : "#fffff0";
                        let border = r.room_status === "Vacant Clean" ? "#68d391" : "#f6e05e";
                        html += `<div class="avail-room" data-room="${r.name}" data-type="${rt.name}" data-rate="${rt.bar_rate}"
                          style="border:2px solid ${border};background:${bg};border-radius:8px;padding:10px 14px;cursor:pointer;min-width:100px;text-align:center"
                          onmouseover="this.style.borderColor='#4299e1'" onmouseout="this.style.borderColor='${border}'">
                          <div style="font-size:16px;font-weight:bold;color:#2d3748">${r.name}</div>
                          <div style="font-size:11px;color:#718096">${r.floor||""} ${r.wing||""}</div>
                          <div style="font-size:11px;color:#276749">${r.room_status}</div>
                        </div>`;
                    });
                    html += `</div></div>`;
                });
                if (!any) html += `<p style="color:#c53030">❌ No rooms available for these dates.</p>`;
                html += `<p style="color:#718096;font-size:12px;margin-top:12px">Click a room to add it to the reservation.</p></div>`;

                let dlg = new frappe.ui.Dialog({
                    title: __("Room Availability"),
                    size: "large",
                    fields: [{ fieldtype:"HTML", options: html }],
                    primary_action_label: __("Done"),
                    primary_action() { dlg.hide(); frm.save(); }
                });
                dlg.show();
                // Click to populate room line
                dlg.$wrapper.find(".avail-room").on("click", function() {
                    let room = $(this).data("room");
                    let rtype = $(this).data("type");
                    let rate = parseFloat($(this).data("rate")) || 0;
                    // Check if room_type already in table
                    let existing = (frm.doc.reservation_rooms||[]).find(r => r.room_type === rtype);
                    if (existing) {
                        frappe.model.set_value("Reservation Room Line", existing.name, "room", room);
                        frappe.model.set_value("Reservation Room Line", existing.name, "rate", rate);
                    } else {
                        let row = frm.add_child("reservation_rooms");
                        frappe.model.set_value("Reservation Room Line", row.name, {
                            room_type: rtype, room: room, rate: rate, adults: frm.doc.adults||1
                        });
                    }
                    frm.refresh_field("reservation_rooms");
                    frappe.show_alert({message: __("Room {0} added", [room]), indicator:"green"});
                    $(this).css("border-color","#9f7aea").css("background","#faf5ff");
                });
            });
        }
    });
}

function _create_stay(frm) {
    // Validate reservation rooms have rooms assigned
    let rooms = frm.doc.reservation_rooms || [];
    if (!rooms.length) { frappe.msgprint(__("Please assign rooms first.")); return; }
    let missing = rooms.filter(r => !r.room);
    if (missing.length) { frappe.msgprint(__("All room lines must have a room assigned.")); return; }
    frappe.set_route("Form","Guest Stay","new-guest-stay-" + frm.doc.name);
}

function _deposit_dialog(frm) {
    let nights = frm.doc.num_nights || 1;
    let suggested = 0;
    (frm.doc.reservation_rooms||[]).forEach(l => { suggested += flt(l.rate||0) * nights; });

    frappe.db.get_value("Property", frm.doc.property, ["deposit_pct","deposit_required"], pv => {
        let pct = (pv && pv.deposit_pct) || 30;
        let required = pv && pv.deposit_required;
        suggested = suggested * pct / 100;

        let d = new frappe.ui.Dialog({
            title: __("Advance Deposit — {0}", [frm.doc.name]),
            fields: [
                { fieldname:"info", fieldtype:"HTML", options: required ?
                    `<div style="background:#ebf8ff;padding:10px;border-radius:6px;margin-bottom:10px">
                    <strong>Deposit Required:</strong> ${pct}% of estimated stay value.<br>
                    Checkin is blocked until deposit is recorded or waived by manager.</div>` :
                    `<div style="background:#f0fff4;padding:8px;border-radius:6px;margin-bottom:10px">Deposit is optional for this property.</div>`
                },
                { fieldname:"deposit_amount", fieldtype:"Currency", label:__("Deposit Amount"), reqd:1, default:suggested },
                { fieldname:"payment_mode", fieldtype:"Select", label:__("Payment Mode"), reqd:1,
                  options:"Cash\nCard\nBank Transfer\nOnline\nCheque" },
                { fieldname:"reference_number", fieldtype:"Data", label:__("Receipt / Reference No") },
                { fieldname:"no_deposit", fieldtype:"Check", label:__("Proceed Without Deposit (waive)") }
            ],
            primary_action_label: __("Create Payment Entry & Record Deposit"),
            secondary_action_label: __("Proceed Without Deposit"),
            secondary_action() {
                d.hide();
                _waive_deposit_dialog(frm);
            },
            primary_action(v) {
                if (v.no_deposit) { d.hide(); _waive_deposit_dialog(frm); return; }
                frappe.call({
                    method: "frappe.client.insert",
                    args: { doc: {
                        doctype:"Hotel Deposit", property:frm.doc.property,
                        reservation:frm.doc.name, customer:frm.doc.customer,
                        deposit_amount:v.deposit_amount, payment_mode:v.payment_mode,
                        reference_number:v.reference_number, deposit_status:"Draft",
                        deposit_date:frappe.datetime.get_today()
                    }},
                    callback(r) {
                        if (!r.message) return;
                        frappe.call({
                            method:"frappe.client.submit", args:{doc:r.message},
                            callback(sr) {
                                if (!sr.message) return;
                                frappe.db.set_value("Reservation", frm.doc.name, {
                                    hotel_deposit:sr.message.name,
                                    deposit_status:"Paid",
                                    deposit_paid:v.deposit_amount
                                });
                                frappe.show_alert({message:__("✓ Deposit recorded. Payment Entry created."),indicator:"green"});
                                d.hide(); frm.reload_doc();
                            }
                        });
                    }
                });
            }
        });
        d.show();
    });
}

function _waive_deposit_dialog(frm) {
    // Get all stays for this reservation
    frappe.db.get_list("Guest Stay", {filters:{reservation:frm.doc.name,stay_status:"Expected"}, fields:["name"]}).then(stays => {
        if (!stays.length) { frappe.msgprint(__("No expected stays found.")); return; }
        let d = new frappe.ui.Dialog({
            title: __("Waive Deposit Requirement"),
            fields: [
                { fieldname:"reason", fieldtype:"Data", label:__("Reason for Waiver"), reqd:1 }
            ],
            primary_action_label: __("Confirm Waiver & Allow Checkin"),
            primary_action(v) {
                let calls = stays.map(s => frappe.call({
                    method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.guest_stay.guest_stay.waive_deposit",
                    args:{stay_name:s.name, reason:v.reason}
                }));
                Promise.all(calls).then(() => {
                    frappe.show_alert({message:__("Deposit waived. Checkin is now allowed."),indicator:"orange"});
                    d.hide(); frm.reload_doc();
                });
            }
        });
        d.show();
    });
}

function _set_status(frm) {
    const c = {"Draft":"gray","Confirmed":"blue","Checked In":"green","Checked Out":"gray","Cancelled":"red","No Show":"orange"};
    frm.page.set_indicator(frm.doc.reservation_status||"Draft", c[frm.doc.reservation_status]||"gray");
}
function fmt_cur(v) { return parseFloat(v||0).toLocaleString("en",{minimumFractionDigits:2}); }
function flt(v) { return parseFloat(v||0); }
