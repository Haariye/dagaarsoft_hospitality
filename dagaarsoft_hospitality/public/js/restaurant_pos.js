// Restaurant POS JS v4 — items stored as JSON, no child table
frappe.ui.form.on("Restaurant POS", {
    refresh(frm) {
        _setup_status(frm);
        if (frm.doc.docstatus === 1) {
            if (frm.doc.sales_invoice)
                frm.add_custom_button(__("View Invoice"), () => frappe.set_route("Form","Sales Invoice",frm.doc.sales_invoice), __("Links"));
            if (frm.doc.folio_charge_ref)
                frm.add_custom_button(__("View Folio"), () => frappe.set_route("Form","Guest Folio",frm.doc.folio_charge_ref), __("Links"));
            return;
        }
        if (frm.doc.docstatus !== 0) return;

        frm.add_custom_button(__("🖥 Open POS Screen"), () => _open_pos(frm))
            .css("background","#48bb78").css("color","white").css("font-weight","bold");

        if (frm.doc.order_type === "Dine In")
            frm.add_custom_button(__("🗺 Table Map"), () => _table_map(frm), __("Actions"));

        if (frm.doc.name && !frm.doc.__islocal)
            frm.add_custom_button(__("🖨 Print KOT"), () => _print_kot(frm), __("Actions"));
    },
    order_type(frm) {
        frm.set_df_property("room_number","reqd", frm.doc.order_type === "Room Service" ? 1 : 0);
    },
    room_number(frm) {
        if (frm.doc.order_type === "Room Service" && frm.doc.room_number) {
            frappe.call({
                method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.fetch_guest_by_room",
                args:{room_number:frm.doc.room_number},
                callback(r) {
                    if (r.message) {
                        frm.set_value("guest_stay", r.message.name);
                        frm.set_value("customer", r.message.customer);
                        frm.set_value("guest_name_display", r.message.guest_name);
                        frappe.show_alert({message:__("Guest: {0}",[r.message.guest_name]),indicator:"green"});
                    }
                }
            });
        }
    }
});

// ─── POS Screen ──────────────────────────────────────────────────────────────
let _cart = {};

function _open_pos(frm) {
    // Load existing items from items_json
    try { _cart = {}; let saved = JSON.parse(frm.doc.items_json || "[]");
        saved.forEach(i => { if (!i.is_void) _cart[i.item_code] = Object.assign({}, i); });
    } catch(e) { _cart = {}; }

    let d = new frappe.ui.Dialog({
        title: `🍽 POS — ${frm.doc.outlet || ""} | ${frm.doc.order_type}`,
        size: "extra-large",
        fields: [{fieldtype:"HTML", fieldname:"pos_html", options: _pos_html(frm)}],
        primary_action_label: __("💾 Save Order"),
        primary_action() {
            _sync_to_server(frm, d);
        }
    });
    d.show();

    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.get_item_groups",
        callback(r) { if (r.message) _render_cats(r.message, frm, d); }
    });
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.get_menu_items",
        args:{outlet:frm.doc.outlet},
        callback(r) { if (r.message) _render_items(r.message, frm, d); }
    });
}

function _pos_html(frm) {
    let hdr = frm.doc.order_type === "Dine In" ? `Table: ${frm.doc.table_display||"—"}` :
              frm.doc.order_type === "Room Service" ? `Room: ${frm.doc.room_number||"—"} ${frm.doc.guest_name_display||""}` :
              frm.doc.order_type;
    return `<div style="display:grid;grid-template-columns:1fr 340px;gap:0;height:580px">
      <div style="padding:12px;overflow-y:auto;border-right:1px solid #e2e8f0">
        <div id="pos-cats" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px"></div>
        <input id="pos-search" placeholder="🔍 Search..." style="width:100%;padding:8px;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:10px;font-size:13px">
        <div id="pos-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px">
          <span style="color:#718096">Loading...</span>
        </div>
      </div>
      <div style="padding:12px;display:flex;flex-direction:column;background:#f8fafc">
        <div style="font-weight:600;color:#2d3748;margin-bottom:8px;font-size:13px">${hdr}</div>
        <div id="pos-cart" style="flex:1;overflow-y:auto"></div>
        <div style="border-top:2px solid #e2e8f0;padding-top:8px;margin-top:8px">
          <div style="display:flex;justify-content:space-between;font-size:13px;color:#718096;margin-bottom:4px">
            <span>Subtotal</span><span id="pos-sub">0.00</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:18px;font-weight:bold">
            <span>Total</span><span id="pos-total" style="color:#2b6cb0">0.00</span>
          </div>
        </div>
      </div>
    </div>`;
}

function _render_cats(groups, frm, d) {
    let bar = d.$wrapper.find("#pos-cats");
    let html = `<button class="pos-cat" data-g="" style="padding:5px 12px;border:none;border-radius:16px;background:#2b6cb0;color:white;cursor:pointer;font-size:12px">All</button>`;
    groups.forEach(g => {
        html += `<button class="pos-cat" data-g="${g.name}" style="padding:5px 12px;border:1px solid #e2e8f0;border-radius:16px;background:white;cursor:pointer;font-size:12px">${g.name}</button>`;
    });
    bar.html(html);
    bar.on("click",".pos-cat", function() {
        bar.find(".pos-cat").css({background:"white",color:"#2d3748",border:"1px solid #e2e8f0"});
        $(this).css({background:"#2b6cb0",color:"white",border:"none"});
        let g = $(this).data("g");
        frappe.call({
            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.get_menu_items",
            args:{outlet:frm.doc.outlet, item_group:g||undefined},
            callback(r) { if(r.message) _render_items(r.message, frm, d); }
        });
    });
}

function _render_items(items, frm, d) {
    let grid = d.$wrapper.find("#pos-grid");
    let html = items.map(i => `
      <div class="pos-item" data-code="${i.item_code}" data-rate="${i.standard_rate||0}" data-name="${i.item_name}" data-uom="${i.stock_uom||'Nos'}"
        style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:10px;cursor:pointer;text-align:center"
        onmouseover="this.style.borderColor='#4299e1'" onmouseout="this.style.borderColor='#e2e8f0'">
        <div style="font-size:12px;font-weight:600;color:#2d3748;margin-bottom:4px">${i.item_name}</div>
        <div style="font-size:13px;color:#2b6cb0;font-weight:bold">${fmt(i.standard_rate||0)}</div>
      </div>`).join("");
    grid.html(html || "<p style='color:#718096'>No items</p>");
    grid.find(".pos-item").on("click", function() {
        let code=$(this).data("code"), rate=parseFloat($(this).data("rate"))||0,
            name=$(this).data("name"), uom=$(this).data("uom")||"Nos";
        if (!_cart[code]) _cart[code]={item_code:code,item_name:name,rate:rate,qty:0,uom:uom,is_void:false};
        _cart[code].qty += 1;
        _render_cart(d);
    });
    d.$wrapper.find("#pos-search").off("input").on("input", function() {
        let q=$(this).val().toLowerCase();
        d.$wrapper.find(".pos-item").each(function() {
            $(this).toggle($(this).find("div").first().text().toLowerCase().includes(q));
        });
    });
}

function _render_cart(d) {
    let cart = d.$wrapper.find("#pos-cart");
    let items = Object.values(_cart).filter(i => i.qty > 0 && !i.is_void);
    if (!items.length) { cart.html('<p style="color:#718096;text-align:center;margin-top:20px">Cart empty</p>'); return; }
    let sub = 0;
    let rows = items.map(i => {
        let lt = i.qty * i.rate; sub += lt;
        return `<div style="display:flex;align-items:center;gap:6px;padding:6px 0;border-bottom:1px solid #f0f4f8">
          <div style="flex:1;font-size:13px">${i.item_name}</div>
          <button onclick="window._posQ('${i.item_code}',-1)" style="width:22px;height:22px;border:1px solid #e2e8f0;border-radius:4px;background:white;cursor:pointer">−</button>
          <span style="font-size:14px;font-weight:bold;min-width:20px;text-align:center">${i.qty}</span>
          <button onclick="window._posQ('${i.item_code}',1)" style="width:22px;height:22px;border:1px solid #e2e8f0;border-radius:4px;background:white;cursor:pointer">+</button>
          <span style="font-size:13px;font-weight:bold;color:#2b6cb0;min-width:60px;text-align:right">${fmt(lt)}</span>
        </div>`;
    }).join("");
    cart.html(rows);
    d.$wrapper.find("#pos-sub").text(fmt(sub));
    d.$wrapper.find("#pos-total").text(fmt(sub));
    window._posQ = function(code, delta) {
        if (_cart[code]) { _cart[code].qty = Math.max(0, _cart[code].qty + delta); if (_cart[code].qty===0) delete _cart[code]; }
        _render_cart(d);
    };
}

function _sync_to_server(frm, d) {
    let items = Object.values(_cart).filter(i => i.qty > 0);
    let items_json = JSON.stringify(items);
    if (frm.doc.__islocal) {
        frm.set_value("items_json", items_json);
        frm.save().then(() => { d.hide(); frm.reload_doc(); });
    } else {
        frappe.call({
            method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.save_items",
            args:{pos_name:frm.doc.name, items_json},
            callback() { d.hide(); frm.reload_doc(); }
        });
    }
}

function _table_map(frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.get_open_tables",
        args:{outlet:frm.doc.outlet},
        callback(r) {
            if (!r.message) return;
            let cells = r.message.map(t => {
                let bg={"Available":"#f0fff4","Occupied":"#fff5f5","Reserved":"#ebf8ff","Cleaning":"#fffff0"}[t.table_status]||"#f9f9f9";
                let border={"Available":"#68d391","Occupied":"#fc8181","Reserved":"#63b3ed","Cleaning":"#f6e05e"}[t.table_status]||"#e2e8f0";
                return `<div class="tbl" data-t="${t.name}" data-s="${t.table_status}" style="background:${bg};border:2px solid ${border};border-radius:8px;padding:12px;cursor:pointer;text-align:center">
                  <div style="font-size:16px;font-weight:bold">${t.table_number}</div>
                  <div style="font-size:11px;color:#718096">${t.seating_capacity} seats</div>
                  <div style="font-size:11px;font-weight:500">${t.table_status}</div>
                </div>`;
            }).join("");
            let dlg = new frappe.ui.Dialog({
                title:__("Select Table"),
                fields:[{fieldtype:"HTML",options:`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:10px;padding:10px">${cells}</div>`}]
            });
            dlg.show();
            dlg.$wrapper.find(".tbl").on("click",function() {
                if ($(this).data("s")==="Occupied") { frappe.show_alert({message:__("Table occupied"),indicator:"red"}); return; }
                let t=$(this).data("t");
                frm.set_value("restaurant_table", t);
                if (frm.doc.name && !frm.doc.__islocal) {
                    frappe.call({method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.assign_table",args:{pos_name:frm.doc.name,table_name:t}});
                }
                dlg.hide();
            });
        }
    });
}

function _print_kot(frm) {
    frappe.call({
        method:"dagaarsoft_hospitality.dagaarsoft_hospitality.doctype.restaurant_pos.restaurant_pos.print_kot",
        args:{pos_name:frm.doc.name},
        callback(r) {
            if (!r.message) return;
            let k=r.message;
            let rows=(k.items||[]).map(i=>`<tr><td style="padding:6px">${i.item_name}</td><td style="padding:6px;text-align:center;font-size:16px;font-weight:bold">${i.qty}</td></tr>`).join("");
            frappe.msgprint({title:__("KOT"),message:`<div style="font-family:'Courier New';padding:10px">
              <h3 style="text-align:center">KOT — ${k.table||""}</h3>
              <p style="text-align:center">${k.order_type} | ${new Date().toLocaleTimeString()}</p>
              <hr><table style="width:100%"><thead><tr><th>Item</th><th>Qty</th></tr></thead><tbody>${rows}</tbody></table>
              ${k.kitchen_notes?`<p><strong>Notes:</strong> ${k.kitchen_notes}`:""}
            </div>`});
        }
    });
}

function _setup_status(frm) {
    const c={"Draft":"gray","Open":"blue","KOT Printed":"yellow","Ready":"orange","Served":"green","Billed":"purple","Paid":"green","Voided":"red"};
    frm.page.set_indicator(frm.doc.order_status||"Draft", c[frm.doc.order_status]||"gray");
}
function fmt(v) { return parseFloat(v||0).toLocaleString("en",{minimumFractionDigits:2}); }
