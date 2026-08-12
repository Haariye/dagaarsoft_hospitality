frappe.ui.form.on("Hospitality Settings", {
    refresh(frm) {
        var isAdmin = frappe.user_roles.includes("System Manager");
        var isManager = frappe.user_roles.includes("Hotel Manager");

        // Purge All Hotel Transactions — System Administrator only
        if (isAdmin) {
            frm.add_custom_button(__("⚠ Purge All Hotel Data"), function() {
                var d = new frappe.ui.Dialog({
                    title: __("⚠ DANGER — Purge All Hotel Transactions"),
                    fields: [
                        {fieldtype:"HTML", options:
                            "<div style='background:#fff5f5;border:2px solid #fc8181;padding:16px;border-radius:8px;margin-bottom:12px'>"
                            + "<h4 style='color:#c53030;margin:0 0 8px'>This will permanently delete:</h4>"
                            + "<ul style='color:#742a2a;margin:0'>"
                            + "<li>All Reservations, Guest Stays, Guest Folios</li>"
                            + "<li>All Hotel Deposits, Room Moves, Laundry Tickets</li>"
                            + "<li>All hotel-linked Sales Invoices, Payment Entries, Journal Entries</li>"
                            + "<li>All Night Audit Runs, Housekeeping Tasks, Service Requests</li>"
                            + "</ul>"
                            + "<p style='color:#c53030;font-weight:bold;margin:8px 0 0'>Property, Room, Room Type, Rate Plan records are SAFE — they will NOT be deleted.</p>"
                            + "</div>"
                        },
                        {fieldname:"password", fieldtype:"Password", label:__("Your Password"), reqd:1},
                        {fieldname:"confirm_text", fieldtype:"Data", label:__("Type: DELETE ALL HOTEL DATA"), reqd:1,
                         description:"Type exactly: DELETE ALL HOTEL DATA"}
                    ],
                    primary_action_label: __("PURGE ALL DATA"),
                    primary_action: function(v) {
                        if (v.confirm_text !== "DELETE ALL HOTEL DATA") {
                            frappe.msgprint({message:__("Confirmation text doesn't match."),indicator:"red"});
                            return;
                        }
                        frappe.call({
                            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.admin_utils.purge_all_hotel_transactions",
                            args: {password: v.password, confirm_text: v.confirm_text},
                            freeze: true, freeze_message: __("Purging all hotel data..."),
                            callback: function(r) {
                                d.hide();
                                if (r.message) {
                                    var msg = "<b>Deleted:</b><br>" + (r.message.deleted || []).join("<br>");
                                    if (r.message.errors && r.message.errors.length) {
                                        msg += "<br><br><b>Errors:</b><br>" + r.message.errors.join("<br>");
                                    }
                                    frappe.msgprint({title:__("Purge Complete"), message:msg, indicator:"green"});
                                }
                                frm.reload_doc();
                            }
                        });
                    }
                });
                // Style the button red
                d.$wrapper.find('.btn-primary').css({'background-color':'#c53030','border-color':'#c53030'});
                d.show();
            }, __("Admin")).addClass("btn-danger");
        }

        // Billing Integrity Check — Hotel Manager
        if (isManager) {
            frm.add_custom_button(__("Check Billing Integrity"), function() {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.admin_utils.check_billing_integrity",
                    freeze: true, freeze_message: __("Scanning all stays..."),
                    callback: function(r) {
                        if (!r.message) return;
                        var res = r.message;
                        if (!res.issues_found) {
                            frappe.msgprint({title:__("All Clear ✓"),
                                message:__("{0} stays checked. No billing gaps or duplicates found.",[res.total_stays_checked]),
                                indicator:"green"});
                            return;
                        }
                        var rows = "";
                        (res.issues || []).forEach(function(i) {
                            var fixBtn = i.missing_dates
                                ? " <button class='btn btn-xs btn-warning dg-fix-btn' data-stay='" + i.stay + "'>Fix</button>"
                                : "";
                            rows += "<tr><td>" + i.room + "</td><td>" + i.guest + "</td>"
                                + "<td>" + i.stay + "</td><td>" + i.issue + fixBtn + "</td></tr>";
                        });
                        frappe.msgprint({title:__("Billing Issues Found"), wide:true, indicator:"orange",
                            message: "<p>" + res.issues_found + " issue(s) in " + res.total_stays_checked + " stays:</p>"
                                + "<table class='table table-bordered table-sm'>"
                                + "<tr><th>Room</th><th>Guest</th><th>Stay</th><th>Issue</th></tr>"
                                + rows + "</table>"
                        });
                        // Bind fix buttons
                        setTimeout(function() {
                            $(".dg-fix-btn").on("click", function() {
                                var stayName = $(this).data("stay");
                                frappe.call({
                                    method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.admin_utils.fix_missing_charges",
                                    args: {stay_name: stayName}, freeze: true,
                                    callback: function(r2) {
                                        if (r2.message) frappe.show_alert({message:r2.message.message, indicator:"green"});
                                    }
                                });
                            });
                        }, 500);
                    }
                });
            }, __("Admin"));
        }
    }
});
