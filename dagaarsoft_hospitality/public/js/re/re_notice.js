frappe.ui.form.on("RE Notice", {
    refresh(frm) {
        const colors = {"Draft":"grey","Sent":"blue","Acknowledged":"orange",
                        "Accepted":"green","Rejected":"red","Expired":"grey"};
        frm.page.set_indicator(__(frm.doc.status||"Draft"), colors[frm.doc.status]||"grey");
        if (frm.doc.docstatus===1 && frm.doc.notice_type==="Renewal Offer"
                && frm.doc.tenant_response==="Accepted") {
            frm.add_custom_button(__("Create Renewal Lease"), () => {
                frappe.new_doc("RE Lease", {
                    unit: frm.doc.unit,
                    tenant: frm.doc.tenant,
                    start_date: frm.doc.effective_date,
                    end_date: frm.doc.new_end_date,
                    monthly_rent: frm.doc.new_rent_amount,
                });
            }).addClass("btn-primary");
        }
    }
});
