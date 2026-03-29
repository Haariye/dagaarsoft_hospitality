/**
 * POSA Hotel Room + Restaurant Table Integration v8
 *
 * Strategy:
 *   1. Widget injection: DOM-inject room/table selectors into POSA invoice panel
 *   2. Pinia store: mergeInvoiceDoc to set fields on the reactive invoiceDoc
 *   3. frappe.call interceptor: patch frappe.call to inject hotel/table fields
 *      into every update_invoice/submit_invoice payload. This guarantees the
 *      fields reach the server even if POSA's document.ts doesn't know about them.
 *
 * Zero POSA files modified. Uninstall dagaarsoft_hospitality = everything gone.
 */
(function () {
	"use strict";

	function isPosaPage() {
		var p = window.location.pathname;
		return p.indexOf("/posapp") !== -1 || p.indexOf("/pos") !== -1;
	}
	if (!isPosaPage()) return;

	// ── State: current hotel/table selections ────────────────────────────────
	var _hotelState = {
		hotel_room: "",
		hotel_stay: "",
		hotel_folio: "",
		hotel_guest_name: "",
		restaurant_table: ""
	};

	// ── frappe.call interceptor ──────────────────────────────────────────────
	// Patch frappe.call to inject hotel/table fields into POSA invoice payloads
	// before they go to the server.
	var _originalFrappeCall = frappe.call;
	frappe.call = function (opts) {
		if (opts && opts.method && opts.args) {
			var m = opts.method || "";
			var isInvoiceCall =
				m.indexOf("update_invoice") !== -1 ||
				m.indexOf("submit_invoice") !== -1 ||
				m.indexOf("update_sales_order") !== -1 ||
				m.indexOf("submit_sales_order") !== -1;

			if (isInvoiceCall) {
				_injectFieldsIntoPayload(opts.args);
			}
		}
		return _originalFrappeCall.apply(this, arguments);
	};

	function _injectFieldsIntoPayload(args) {
		// The payload is in args.data (for update) or args.invoice (for submit)
		var targets = ["data", "invoice", "order"];
		for (var i = 0; i < targets.length; i++) {
			var key = targets[i];
			var payload = args[key];
			if (!payload) continue;

			// payload may be a string (JSON) or object
			var obj = payload;
			var wasString = false;
			if (typeof payload === "string") {
				try { obj = JSON.parse(payload); wasString = true; }
				catch (e) { continue; }
			}
			if (typeof obj !== "object" || obj === null) continue;

			// Inject hotel fields
			if (_hotelState.hotel_room) {
				obj.hotel_room = _hotelState.hotel_room;
				obj.hotel_stay = _hotelState.hotel_stay;
				obj.hotel_folio = _hotelState.hotel_folio;
				obj.hotel_guest_name = _hotelState.hotel_guest_name;
			}
			// Inject restaurant table
			if (_hotelState.restaurant_table) {
				obj.restaurant_table = _hotelState.restaurant_table;
			}

			// Write back
			if (wasString) {
				args[key] = JSON.stringify(obj);
			} else {
				args[key] = obj;
			}
		}
	}

	// ── Utility ──────────────────────────────────────────────────────────────
	function pollFor(testFn, interval, maxAttempts) {
		return new Promise(function (resolve, reject) {
			var attempts = 0;
			var timer = setInterval(function () {
				attempts++;
				var result = testFn();
				if (result) { clearInterval(timer); resolve(result); }
				else if (attempts >= maxAttempts) { clearInterval(timer); reject(); }
			}, interval);
		});
	}

	function getPiniaStores(vueApp) {
		var pinia = vueApp.config && vueApp.config.globalProperties &&
			vueApp.config.globalProperties.$pinia;
		if (!pinia || !pinia._s) return null;
		var s = pinia._s;
		return {
			invoice: s.get("invoice") || null,
			customers: s.get("customers") || null,
			ui: s.get("ui") || null
		};
	}

	function findCustomerCard() {
		var card = document.querySelector(".invoice-section-card.customer-card");
		if (card) return card;
		var headings = document.querySelectorAll(".invoice-section-heading__title");
		for (var i = 0; i < headings.length; i++) {
			if ((headings[i].textContent || "").toLowerCase().indexOf("customer") !== -1) {
				var c = headings[i].closest(".invoice-section-card");
				if (c) return c;
			}
		}
		return document.querySelector(".invoice-section-card") || null;
	}

	function makeCard(id, title, innerHTML) {
		var card = document.createElement("div");
		card.id = id;
		card.className = "v-card v-card--flat invoice-section-card pos-themed-card";
		card.innerHTML =
			'<div class="invoice-section-heading" style="padding:6px 12px 2px">' +
			'<h3 class="invoice-section-heading__title" style="font-size:12px;font-weight:600;opacity:0.7;text-transform:uppercase;letter-spacing:0.5px">' + title + '</h3>' +
			'</div>' +
			'<div style="padding:4px 12px 8px">' + innerHTML + '</div>';
		return card;
	}

	var selectStyle = "width:100%;padding:7px 10px;border:1px solid var(--pos-border-color,#e2e8f0);" +
		"border-radius:6px;font-size:13px;background:var(--pos-input-bg,#fff);" +
		"color:var(--pos-text-primary,#2d3748);outline:none;transition:border-color 0.2s";
	var clearBtnStyle = "padding:4px 8px;background:#fed7d7;border:none;border-radius:4px;" +
		"cursor:pointer;font-size:11px;color:#e53e3e;display:none";
	var linkStyle = "font-size:10px;padding:2px 6px;border-radius:4px;text-decoration:none;white-space:nowrap;display:inline-block";

	// ═══════════════════════════════════════════════════════════════════════════
	//  HOTEL ROOM WIDGET
	// ═══════════════════════════════════════════════════════════════════════════
	function injectHotelRoom(stores) {
		if (document.getElementById("dg-hotel-room-widget")) return;
		var anchor = findCustomerCard();
		if (!anchor) return;

		var html =
			'<div style="display:flex;gap:6px;align-items:center">' +
			'<div style="flex:1;min-width:0">' +
			'<select id="dg-room-select" style="' + selectStyle + '">' +
			'<option value="">-- Select Room --</option></select></div>' +
			'<div id="dg-guest-info" style="min-width:90px;font-size:11px;display:none">' +
			'<div id="dg-guest-name" style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>' +
			'<div id="dg-guest-balance" style="color:#e53e3e;font-size:10px;display:none"></div></div>' +
			'<div id="dg-hotel-links" style="display:none;gap:4px;align-items:center;flex-shrink:0">' +
			'<a id="dg-link-stay" href="#" target="_blank" style="' + linkStyle + ';border:1px solid rgb(var(--v-theme-primary,66,133,244));color:rgb(var(--v-theme-primary,66,133,244))">Stay</a>' +
			'<a id="dg-link-folio" href="#" target="_blank" style="' + linkStyle + ';border:1px solid #ed8936;color:#ed8936">Folio</a></div>' +
			'<button id="dg-clear-room" style="' + clearBtnStyle + '">✕</button></div>';

		var card = makeCard("dg-hotel-room-widget", "Hotel Room", html);
		anchor.parentNode.insertBefore(card, anchor.nextSibling);
		bindHotelRoom(card, stores);
	}

	function bindHotelRoom(card, stores) {
		var select = card.querySelector("#dg-room-select");
		var guestInfo = card.querySelector("#dg-guest-info");
		var guestName = card.querySelector("#dg-guest-name");
		var guestBal = card.querySelector("#dg-guest-balance");
		var links = card.querySelector("#dg-hotel-links");
		var linkStay = card.querySelector("#dg-link-stay");
		var linkFolio = card.querySelector("#dg-link-folio");
		var clearBtn = card.querySelector("#dg-clear-room");

		function loadRooms() {
			_originalFrappeCall({
				method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.room_utils.get_all_occupied_rooms",
				args: {}, async: true,
				callback: function (r) {
					if (!r.message) return;
					var cur = select.value;
					select.innerHTML = '<option value="">-- Select Room --</option>';
					r.message.forEach(function (room) {
						var o = document.createElement("option");
						o.value = room.name;
						o.textContent = "Room " + room.name + " \u2014 " + (room.current_guest || "");
						select.appendChild(o);
					});
					if (cur) select.value = cur;
				}
			});
		}

		function clearRoom() {
			_hotelState.hotel_room = "";
			_hotelState.hotel_stay = "";
			_hotelState.hotel_folio = "";
			_hotelState.hotel_guest_name = "";
			guestInfo.style.display = "none";
			guestBal.style.display = "none";
			links.style.display = "none";
			clearBtn.style.display = "none";
			if (stores.invoice && stores.invoice.mergeInvoiceDoc) {
				stores.invoice.mergeInvoiceDoc({
					hotel_room: "", hotel_stay: "", hotel_folio: "", hotel_guest_name: ""
				});
			}
		}

		select.addEventListener("change", function () {
			if (!select.value) { clearRoom(); return; }
			_originalFrappeCall({
				method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.get_room_billing_info",
				args: { room: select.value },
				callback: function (r) {
					if (!r.message) return;
					var info = r.message;

					// Update shared state (used by frappe.call interceptor)
					_hotelState.hotel_room = select.value;
					_hotelState.hotel_stay = info.guest_stay || "";
					_hotelState.hotel_folio = info.guest_folio || "";
					_hotelState.hotel_guest_name = info.guest_name || "";

					// Also set on Pinia store
					if (stores.invoice && stores.invoice.mergeInvoiceDoc) {
						stores.invoice.mergeInvoiceDoc({
							hotel_room: select.value,
							hotel_stay: info.guest_stay || "",
							hotel_folio: info.guest_folio || "",
							hotel_guest_name: info.guest_name || ""
						});
					}
					// Set customer
					if (info.customer && stores.customers && stores.customers.setSelectedCustomer) {
						stores.customers.setSelectedCustomer(info.customer);
					}
					// Update UI
					guestInfo.style.display = "block";
					guestName.textContent = "\u2713 " + (info.guest_name || "");
					if (info.balance_due && parseFloat(info.balance_due) > 0) {
						guestBal.style.display = "block";
						guestBal.textContent = "Bal: " + parseFloat(info.balance_due).toLocaleString("en", { minimumFractionDigits: 2 });
					} else { guestBal.style.display = "none"; }
					links.style.display = "flex";
					if (info.guest_stay) { linkStay.href = frappe.utils.get_url_to_form("Guest Stay", info.guest_stay); linkStay.style.display = "inline-block"; }
					else { linkStay.style.display = "none"; }
					if (info.guest_folio) { linkFolio.href = frappe.utils.get_url_to_form("Guest Folio", info.guest_folio); linkFolio.style.display = "inline-block"; }
					else { linkFolio.style.display = "none"; }
					clearBtn.style.display = "inline-block";
					frappe.show_alert({ message: "Room " + select.value + ": " + (info.guest_name || ""), indicator: "green" });
				},
				error: function () {
					select.value = ""; clearRoom();
					frappe.show_alert({ message: "No active guest in that room", indicator: "red" });
				}
			});
		});

		clearBtn.addEventListener("click", function () { select.value = ""; clearRoom(); });

		// Watch for invoice clear (new sale)
		if (stores.invoice && stores.invoice.$subscribe) {
			stores.invoice.$subscribe(function (mutation, state) {
				if (!state.invoiceDoc || !state.invoiceDoc.hotel_room) {
					if (select.value) { select.value = ""; clearRoom(); }
				}
			});
		}

		loadRooms();
		setInterval(loadRooms, 120000);
	}

	// ═══════════════════════════════════════════════════════════════════════════
	//  RESTAURANT TABLE WIDGET
	// ═══════════════════════════════════════════════════════════════════════════
	function injectRestaurantTable(stores) {
		if (document.getElementById("dg-table-widget")) return;
		var anchor = document.getElementById("dg-hotel-room-widget") || findCustomerCard();
		if (!anchor) return;

		var html =
			'<div style="display:flex;gap:6px;align-items:center">' +
			'<div style="flex:1;min-width:0">' +
			'<select id="dg-table-select" style="' + selectStyle + '">' +
			'<option value="">-- Select Table --</option></select></div>' +
			'<div id="dg-table-info" style="font-size:11px;display:none;white-space:nowrap">' +
			'<span id="dg-table-status" style="font-weight:600"></span>' +
			'<span id="dg-table-cap" style="margin-left:6px;opacity:0.7"></span></div>' +
			'<button id="dg-clear-table" style="' + clearBtnStyle + '">✕</button></div>';

		var card = makeCard("dg-table-widget", "Restaurant Table", html);
		anchor.parentNode.insertBefore(card, anchor.nextSibling);
		bindRestaurantTable(card, stores);
	}

	function bindRestaurantTable(card, stores) {
		var select = card.querySelector("#dg-table-select");
		var tableInfo = card.querySelector("#dg-table-info");
		var tableStatus = card.querySelector("#dg-table-status");
		var tableCap = card.querySelector("#dg-table-cap");
		var clearBtn = card.querySelector("#dg-clear-table");
		var tablesCache = [];

		function loadTables() {
			_originalFrappeCall({
				method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.get_all_restaurant_tables",
				args: {}, async: true,
				callback: function (r) {
					if (!r.message) return;
					tablesCache = r.message;
					var cur = select.value;
					select.innerHTML = '<option value="">-- Select Table --</option>';
					r.message.forEach(function (t) {
						var o = document.createElement("option");
						o.value = t.name;
						o.textContent = t.label;
						if (t.status === "Occupied") o.style.color = "#e53e3e";
						else if (t.status === "Reserved") o.style.color = "#ed8936";
						select.appendChild(o);
					});
					if (cur) select.value = cur;
				}
			});
		}

		function clearTable() {
			_hotelState.restaurant_table = "";
			tableInfo.style.display = "none";
			clearBtn.style.display = "none";
			if (stores.invoice && stores.invoice.mergeInvoiceDoc) {
				stores.invoice.mergeInvoiceDoc({ restaurant_table: "" });
			}
		}

		select.addEventListener("change", function () {
			if (!select.value) { clearTable(); return; }

			// Update shared state (used by frappe.call interceptor)
			_hotelState.restaurant_table = select.value;

			// Also set on Pinia store
			if (stores.invoice && stores.invoice.mergeInvoiceDoc) {
				stores.invoice.mergeInvoiceDoc({ restaurant_table: select.value });
			}

			var tbl = tablesCache.find(function (t) { return t.name === select.value; });
			if (tbl) {
				tableInfo.style.display = "block";
				var statusColor = tbl.status === "Available" ? "#276749" :
					tbl.status === "Occupied" ? "#e53e3e" : "#ed8936";
				tableStatus.textContent = "\u2713 " + tbl.table_number;
				tableStatus.style.color = statusColor;
				tableCap.textContent = tbl.capacity ? "Seats: " + tbl.capacity : "";
				if (tbl.floor) tableCap.textContent += (tableCap.textContent ? " \u00b7 " : "") + tbl.floor;
				clearBtn.style.display = "inline-block";
			}
			frappe.show_alert({
				message: "Table: " + (tbl ? tbl.table_number : select.value),
				indicator: "green"
			});
		});

		clearBtn.addEventListener("click", function () { select.value = ""; clearTable(); });

		if (stores.invoice && stores.invoice.$subscribe) {
			stores.invoice.$subscribe(function (mutation, state) {
				if (!state.invoiceDoc || !state.invoiceDoc.restaurant_table) {
					if (select.value) { select.value = ""; clearTable(); }
				}
			});
		}

		loadTables();
		setInterval(loadTables, 120000);
	}

	// ═══════════════════════════════════════════════════════════════════════════
	//  BOOTSTRAP
	// ═══════════════════════════════════════════════════════════════════════════
	function bootstrap() {
		pollFor(function () {
			var candidates = document.querySelectorAll("[data-v-app], .v-application");
			for (var i = 0; i < candidates.length; i++) {
				if (candidates[i].__vue_app__) return candidates[i].__vue_app__;
			}
			var main = document.querySelector(".main-section");
			if (main) {
				for (var j = 0; j < main.children.length; j++) {
					if (main.children[j].__vue_app__) return main.children[j].__vue_app__;
				}
			}
			return null;
		}, 300, 120).then(function (vueApp) {
			pollFor(function () {
				var s = getPiniaStores(vueApp);
				if (!s || !s.ui || !s.invoice) return null;
				var profile = s.ui.posProfile;
				if (profile && profile.name) return { stores: s, profile: profile };
				return null;
			}, 500, 120).then(function (result) {
				var stores = result.stores;
				var profile = result.profile;

				if (profile.posa_enable_hotel_room) injectHotelRoom(stores);
				if (profile.posa_enable_restaurant_table) injectRestaurantTable(stores);

				if (profile.posa_enable_hotel_room || profile.posa_enable_restaurant_table) {
					var observer = new MutationObserver(function () {
						if (profile.posa_enable_hotel_room && !document.getElementById("dg-hotel-room-widget")) {
							if (findCustomerCard()) injectHotelRoom(stores);
						}
						if (profile.posa_enable_restaurant_table && !document.getElementById("dg-table-widget")) {
							if (findCustomerCard()) injectRestaurantTable(stores);
						}
					});
					var root = document.querySelector(".v-application") || document.body;
					observer.observe(root, { childList: true, subtree: true });
				}
			}).catch(function () {});
		}).catch(function () {});
	}

	if (typeof frappe !== "undefined" && frappe.after_ajax) {
		frappe.after_ajax(function () { setTimeout(bootstrap, 500); });
	} else {
		document.addEventListener("DOMContentLoaded", function () { setTimeout(bootstrap, 1500); });
	}
})();
