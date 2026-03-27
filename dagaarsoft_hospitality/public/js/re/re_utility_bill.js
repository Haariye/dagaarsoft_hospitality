frappe.ui.form.on("RE Utility Bill", {
    refresh(frm) {
        if (frm.doc.docstatus===1 && !frm.doc.sales_invoice
                && !frm.doc.included_in_rent && flt(frm.doc.tenant_portion) > 0) {
            frm.add_custom_button(__("Generate Invoice"), () => {
                frappe.call({
                    method: "dagaarsoft_hospitality.dagaarsoft_real_estate.utils.reports.create_utility_invoice",
                    args: {utility_name: frm.doc.name},
                    callback(r) { if(r.message) {frm.set_value("sales_invoice",r.message); frm.save();} }
                });
            }).addClass("btn-primary");
        }
    },
    current_reading(frm) { _calc_consumption(frm); },
    previous_reading(frm) { _calc_consumption(frm); },
    unit_rate(frm) { _calc_bill(frm); },
});
function _calc_consumption(frm) {
    const c = flt(frm.doc.current_reading) - flt(frm.doc.previous_reading);
    frm.set_value("consumption", Math.max(c, 0));
    _calc_bill(frm);
}
function _calc_bill(frm) {
    if (frm.doc.consumption && frm.doc.unit_rate) {
        frm.set_value("bill_amount", flt(frm.doc.consumption) * flt(frm.doc.unit_rate));
        frm.set_value("tenant_portion", flt(frm.doc.consumption) * flt(frm.doc.unit_rate));
    }
}
function flt(v) { return parseFloat(v||0); }
