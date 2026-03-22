/**
 * POSA Hotel Room Integration v5
 * 
 * This script injects a Hotel Room selector into POSAwesome.
 * It works by hooking into POSA's invoice store and mounting a Vue component
 * after the customer section renders.
 * 
 * Loaded via: app_include_js in hooks.py (only on POS page)
 */

(function() {
    "use strict";

    // Only run on POSA page
    if (!window.location.pathname.includes('/pos')) return;

    // Wait for Vue + POSA to be ready
    function waitForPOSA(callback, attempts) {
        attempts = attempts || 0;
        if (attempts > 100) return;
        
        // POSA mounts itself on #app
        const app = document.getElementById('app');
        if (app && app.__vue_app__) {
            callback(app.__vue_app__);
        } else {
            setTimeout(() => waitForPOSA(callback, attempts + 1), 200);
        }
    }

    function injectHotelRoomSelector(vueApp) {
        // Only inject if hotel integration is enabled
        const defaults = (frappe.boot && frappe.boot.hospitality_defaults) || {};
        if (!defaults.allow_posa_room_charge) return;

        // Wait for DOM to have the invoice panel
        function mountWidget() {
            const invoicePanel = document.querySelector('.pos-invoice-wrapper, .invoice-wrapper, [class*="invoice"]');
            if (!invoicePanel) {
                setTimeout(mountWidget, 500);
                return;
            }
            // Don't double-mount
            if (document.getElementById('hotel-room-widget')) return;

            const container = document.createElement('div');
            container.id = 'hotel-room-widget';
            container.style.cssText = 'padding: 4px 8px;';

            // Insert after customer section (first v-row in invoice)
            const customerRow = invoicePanel.querySelector('.items.px-2, [class*="customer"]');
            if (customerRow && customerRow.parentNode) {
                customerRow.parentNode.insertBefore(container, customerRow.nextSibling);
            } else {
                invoicePanel.prepend(container);
            }

            // Mount the Vue 3 component
            const { createApp, ref, watch, computed } = vueApp.config.globalProperties.$vue ||
                                                          window.Vue || {};
            if (!createApp) {
                console.warn('Hotel Room: Vue not accessible');
                return;
            }

            const HotelWidget = {
                template: `
                <div style="display:flex;gap:6px;align-items:center;padding:4px 0">
                    <div style="flex:1;min-width:0">
                        <select
                            v-model="selectedRoom"
                            @change="onRoomChange"
                            style="width:100%;padding:6px 8px;border:1px solid #e2e8f0;
                                   border-radius:4px;font-size:13px;background:#fff;
                                   color:#2d3748"
                        >
                            <option value="">-- Hotel Room (optional) --</option>
                            <option v-for="r in rooms" :key="r.name" :value="r.name">
                                Room {{ r.name }} — {{ r.current_guest }}
                            </option>
                        </select>
                    </div>
                    <div v-if="guestInfo" style="font-size:11px;color:#276749;min-width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        ✓ {{ guestInfo.guest_name }}
                        <span v-if="guestInfo.balance_due > 0" style="color:#e53e3e;margin-left:4px">
                            Bal: {{ fmt(guestInfo.balance_due) }}
                        </span>
                    </div>
                    <button v-if="selectedRoom" @click="clearRoom"
                        style="padding:4px 8px;background:#fed7d7;border:none;border-radius:4px;
                               cursor:pointer;font-size:11px;color:#e53e3e">✕</button>
                </div>`,
                data() {
                    return {
                        rooms: [],
                        selectedRoom: "",
                        guestInfo: null,
                        loading: false
                    };
                },
                mounted() {
                    this.loadOccupiedRooms();
                    // Refresh every 2 minutes
                    this._interval = setInterval(() => this.loadOccupiedRooms(), 120000);
                },
                beforeUnmount() {
                    if (this._interval) clearInterval(this._interval);
                },
                methods: {
                    loadOccupiedRooms() {
                        frappe.call({
                            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.room_utils.get_all_occupied_rooms",
                            args: {},
                            callback: (r) => {
                                if (r.message) this.rooms = r.message;
                            }
                        });
                    },
                    onRoomChange() {
                        if (!this.selectedRoom) {
                            this.guestInfo = null;
                            this.clearInvoiceFields();
                            return;
                        }
                        frappe.call({
                            method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.get_room_billing_info",
                            args: {room: this.selectedRoom},
                            callback: (r) => {
                                if (r.message) {
                                    this.guestInfo = r.message;
                                    this.applyToInvoice(r.message);
                                }
                            },
                            error: () => {
                                this.guestInfo = null;
                                frappe.show_alert({
                                    message: "No active guest in Room " + this.selectedRoom,
                                    indicator: "red"
                                });
                                this.selectedRoom = "";
                            }
                        });
                    },
                    applyToInvoice(info) {
                        // Inject hotel fields into POSA invoice via Pinia store
                        const pinia = vueApp.config.globalProperties.$pinia;
                        if (pinia) {
                            // Try to access invoiceStore
                            const stores = pinia._s;
                            const invoiceStore = stores && (stores.get('invoice') || stores.get('invoiceStore'));
                            if (invoiceStore && invoiceStore.mergeInvoiceDoc) {
                                invoiceStore.mergeInvoiceDoc({
                                    customer: info.customer,
                                    hotel_room: this.selectedRoom,
                                    hotel_stay: info.guest_stay,
                                    hotel_folio: info.guest_folio,
                                    hotel_guest_name: info.guest_name,
                                });
                                // Also trigger customer change in POSA
                                frappe.show_alert({
                                    message: `Room ${this.selectedRoom}: ${info.guest_name}`,
                                    indicator: "green"
                                });
                                return;
                            }
                        }
                        // Fallback: use frappe events
                        frappe.ui.form.trigger_event && frappe.ui.form.trigger_event(
                            "POS Invoice", "hotel_room", this.selectedRoom);
                    },
                    clearRoom() {
                        this.selectedRoom = "";
                        this.guestInfo = null;
                        this.clearInvoiceFields();
                    },
                    clearInvoiceFields() {
                        const pinia = vueApp.config.globalProperties.$pinia;
                        if (pinia) {
                            const stores = pinia._s;
                            const invoiceStore = stores && (stores.get('invoice') || stores.get('invoiceStore'));
                            if (invoiceStore && invoiceStore.mergeInvoiceDoc) {
                                invoiceStore.mergeInvoiceDoc({
                                    hotel_room: "",
                                    hotel_stay: "",
                                    hotel_folio: "",
                                    hotel_guest_name: "",
                                });
                            }
                        }
                    },
                    fmt(v) {
                        return parseFloat(v||0).toLocaleString("en",{minimumFractionDigits:2});
                    }
                }
            };

            const widgetApp = createApp(HotelWidget);
            widgetApp.mount(container);
        }

        setTimeout(mountWidget, 1000);
    }

    waitForPOSA(injectHotelRoomSelector);
})();
