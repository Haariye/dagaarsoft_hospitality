// Night Audit Run JS v3 — User friendly with full preview
frappe.ui.form.on("Night Audit Run", {
    refresh(frm) {
        if (frm.doc.docstatus === 0) {
            // BIG prominent preview button
            frm.add_custom_button(__("🔍 Preview Audit (Review Before Running)"), () => {
                if (!frm.doc.property || !frm.doc.audit_date) {
                    frappe.msgprint(__("Please set Property and Audit Date first."));
                    return;
                }
                _show_audit_preview(frm);
            }).css("background", "#ebf8ff").css("color", "#2b6cb0").css("font-weight", "bold");
        }
        if (frm.doc.docstatus === 1 && frm.doc.audit_status === "Completed") {
            frm.page.set_indicator(__("✓ Completed"), "green");
            _show_completed_summary(frm);
        }
    },

    audit_date(frm) {
        if (frm.doc.property && frm.doc.audit_date) {
            _check_if_already_run(frm);
        }
    }
});

function _check_if_already_run(frm) {
    frappe.db.get_value("Night Audit Run",
        { property: frm.doc.property, audit_date: frm.doc.audit_date, audit_status: "Completed" },
        "name",
        r => {
            if (r && r.name) {
                frm.page.set_indicator(__("⚠ Audit already completed today"), "orange");
                frappe.show_alert({
                    message: __("Night Audit already completed for this date!"),
                    indicator: "orange"
                });
            }
        }
    );
}

function _show_audit_preview(frm) {
    let d = frappe.msgprint(__("Loading audit preview..."));
    frappe.call({
        method: "dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.night_audit_run.night_audit_run.preview_night_audit",
        args: { property_name: frm.doc.property, audit_date: frm.doc.audit_date },
        callback(r) {
            if (d) d.$wrapper.closest(".modal").modal("hide");
            let p = r.message;
            if (!p) return;

            let charge_rows = (p.rooms_to_charge || []).map(s =>
                `<tr style="background:#f0fff4">
                  <td style="padding:6px 10px">${s.room}</td>
                  <td style="padding:6px 10px">${s.guest}</td>
                  <td style="padding:6px 10px">${s.nights_so_far} night(s)</td>
                  <td style="padding:6px 10px;text-align:right;color:#276749"><strong>${fmt_cur(s.nightly_rate)}</strong></td>
                </tr>`
            ).join("");

            let already_rows = (p.already_charged || []).map(s =>
                `<tr style="background:#fffbeb;color:#744210">
                  <td style="padding:6px 10px">${s.room}</td>
                  <td style="padding:6px 10px">${s.guest}</td>
                  <td colspan="2" style="padding:6px 10px">Already charged tonight ✓</td>
                </tr>`
            ).join("");

            let no_show_rows = (p.no_shows || []).map(s =>
                `<tr style="background:#fff5f5;color:#c53030">
                  <td style="padding:6px 10px">${s.guest_name}</td>
                  <td style="padding:6px 10px">${s.room_type}</td>
                  <td colspan="2" style="padding:6px 10px">Will be flagged as No-Show</td>
                </tr>`
            ).join("");

            let alreadyRun = p.already_run;

            let html = `
            <div style="font-family:Arial;padding:10px;max-height:70vh;overflow-y:auto">
              <h3 style="color:#2d3748">🌙 Night Audit Preview — ${p.audit_date}</h3>
              ${alreadyRun ? '<div style="background:#fff3cd;padding:10px;border-radius:6px;margin-bottom:10px">⚠️ <strong>Audit already completed for this date!</strong></div>' : ''}

              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:15px">
                <div style="background:#ebf8ff;padding:12px;border-radius:8px;text-align:center">
                  <div style="font-size:24px;font-weight:bold;color:#2b6cb0">${p.rooms_to_charge.length}</div>
                  <div style="color:#4a5568;font-size:12px">Rooms to Charge</div>
                </div>
                <div style="background:#f0fff4;padding:12px;border-radius:8px;text-align:center">
                  <div style="font-size:24px;font-weight:bold;color:#276749">${fmt_cur(p.total_to_charge)}</div>
                  <div style="color:#4a5568;font-size:12px">Revenue to Post</div>
                </div>
                <div style="background:#faf5ff;padding:12px;border-radius:8px;text-align:center">
                  <div style="font-size:24px;font-weight:bold;color:#553c9a">${p.occupancy.pct}%</div>
                  <div style="color:#4a5568;font-size:12px">Occupancy (${p.occupancy.occupied}/${p.occupancy.total})</div>
                </div>
              </div>

              ${charge_rows ? `
              <h4 style="color:#276749">Rooms Being Charged Tonight</h4>
              <table style="width:100%;border-collapse:collapse;margin-bottom:15px">
              <thead><tr style="background:#c6f6d5"><th style="padding:8px">Room</th><th>Guest</th><th>Nights</th><th style="text-align:right">Rate</th></tr></thead>
              <tbody>${charge_rows}</tbody>
              </table>` : '<p style="color:#718096">No rooms to charge tonight.</p>'}

              ${already_rows ? `
              <h4 style="color:#744210">Already Charged</h4>
              <table style="width:100%;border-collapse:collapse;margin-bottom:15px">
              <tbody>${already_rows}</tbody></table>` : ""}

              ${no_show_rows ? `
              <h4 style="color:#c53030">No-Shows to Flag</h4>
              <table style="width:100%;border-collapse:collapse;margin-bottom:15px">
              <thead><tr style="background:#fed7d7"><th style="padding:8px">Guest</th><th>Room Type</th><th colspan="2">Action</th></tr></thead>
              <tbody>${no_show_rows}</tbody></table>` : ""}

              <div style="background:#ebf8ff;padding:10px;border-radius:6px;margin-top:10px">
                <strong>Tomorrow:</strong> ${p.arrivals_tomorrow} arrivals | ${p.departures_tomorrow} departures
              </div>
            </div>`;

            let dlg = new frappe.ui.Dialog({
                title: __("Night Audit Preview"),
                size: "large",
                fields: [{ fieldtype: "HTML", options: html }],
                primary_action_label: alreadyRun ? __("Already Run") : __("✓ Run Night Audit Now"),
                primary_action() {
                    if (alreadyRun) { dlg.hide(); return; }
                    dlg.hide();
                    frm.save_or_update().then(() => {
                        frm.amend_doc ? frm.amend_doc() : frm.submit();
                    });
                }
            });
            if (alreadyRun) dlg.get_primary_btn().prop("disabled", true);
            dlg.show();
        }
    });
}

function _show_completed_summary(frm) {
    let html = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:10px 0">
      <div style="background:#f0fff4;padding:10px;border-radius:6px;text-align:center">
        <div style="font-size:20px;font-weight:bold;color:#276749">${frm.doc.rooms_charged||0}</div>
        <div style="font-size:11px;color:#666">Rooms Charged</div>
      </div>
      <div style="background:#ebf8ff;padding:10px;border-radius:6px;text-align:center">
        <div style="font-size:20px;font-weight:bold;color:#2b6cb0">${fmt_cur(frm.doc.total_revenue)}</div>
        <div style="font-size:11px;color:#666">Revenue Posted</div>
      </div>
      <div style="background:#fff5f5;padding:10px;border-radius:6px;text-align:center">
        <div style="font-size:20px;font-weight:bold;color:#c53030">${frm.doc.no_shows_flagged||0}</div>
        <div style="font-size:11px;color:#666">No-Shows</div>
      </div>
      <div style="background:#faf5ff;padding:10px;border-radius:6px;text-align:center">
        <div style="font-size:20px;font-weight:bold;color:#553c9a">${frm.doc.occupancy_pct||0}%</div>
        <div style="font-size:11px;color:#666">Occupancy</div>
      </div>
    </div>`;
    frm.get_field("notes").$wrapper.before(html);
}

function fmt_cur(v) {
    return parseFloat(v || 0).toLocaleString("en", { minimumFractionDigits: 2 });
}
