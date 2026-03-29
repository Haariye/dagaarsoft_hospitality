/**
 * POSA Hotel Room Integration v6 — Standalone External Injection
 *
 * This script injects a Hotel Room selector into POS Awesome WITHOUT modifying
 * any POSA source files. It works entirely from dagaarsoft_hospitality.
 *
 * How it works:
 * 1. Waits for POSA Vue app to mount and Pinia stores to initialise
 * 2. Watches the uiStore for pos_profile to load (contains posa_enable_hotel_room)
 * 3. If enabled, mounts a hotel room widget into the invoice panel DOM
 * 4. Uses Pinia stores (invoiceStore, customersStore) to set hotel fields + customer
 * 5. Hotel fields flow through POSA's existing document.ts spread ({...sourceDoc})
 *    because mergeInvoiceDoc patches the reactive invoiceDoc object
 *
 * Loaded via: hooks.py → app_include_js (runs on every page, self-gates to /posapp)
 */
(function () {
	"use strict";

	// ── Gate: only run on the POSA page ──────────────────────────────────────
	function isPosaPage() {
		var p = window.location.pathname;
		return p.indexOf("/posapp") !== -1 || p.indexOf("/pos") !== -1;
	}
	if (!isPosaPage()) return;

	// ── Utility: poll for a condition ────────────────────────────────────────
	function pollFor(testFn, interval, maxAttempts) {
		return new Promise(function (resolve, reject) {
			var attempts = 0;
			var timer = setInterval(function () {
				attempts++;
				var result = testFn();
				if (result) {
					clearInterval(timer);
					resolve(result);
				} else if (attempts >= maxAttempts) {
					clearInterval(timer);
					reject(new Error("pollFor timed out"));
				}
			}, interval);
		});
	}

	// ── Find POSA's Pinia stores ─────────────────────────────────────────────
	function getPiniaStores(vueApp) {
		var pinia =
			(vueApp.config &&
				vueApp.config.globalProperties &&
				vueApp.config.globalProperties.$pinia) ||
			null;
		if (!pinia || !pinia._s) return null;
		var stores = pinia._s;
		return {
			invoice: stores.get("invoice") || null,
			customers: stores.get("customers") || null,
			ui: stores.get("ui") || null,
			toast: stores.get("toast") || null,
		};
	}

	// ── Main bootstrap ───────────────────────────────────────────────────────
	function bootstrap() {
		pollFor(
			function () {
				// Find the POSA Vue app mounted element
				var candidates = document.querySelectorAll("[data-v-app], .v-application");
				for (var i = 0; i < candidates.length; i++) {
					var el = candidates[i];
					if (el.__vue_app__) return el.__vue_app__;
					// Walk up
					var parent = el.closest("[data-v-app]");
					if (parent && parent.__vue_app__) return parent.__vue_app__;
				}
				// Fallback: search main-section
				var main = document.querySelector(".main-section");
				if (main) {
					var children = main.children;
					for (var j = 0; j < children.length; j++) {
						if (children[j].__vue_app__) return children[j].__vue_app__;
					}
				}
				return null;
			},
			300,
			120
		)
			.then(function (vueApp) {
				waitForStoresAndProfile(vueApp);
			})
			.catch(function () {
				// POSA didn't mount in 36s — not a POSA page or something is broken
			});
	}

	function waitForStoresAndProfile(vueApp) {
		pollFor(
			function () {
				var s = getPiniaStores(vueApp);
				if (!s || !s.ui || !s.invoice) return null;
				// Wait for pos_profile to be loaded into the UI store
				var profile = s.ui.posProfile;
				if (profile && profile.name) return { stores: s, profile: profile };
				return null;
			},
			500,
			120
		)
			.then(function (result) {
				onProfileReady(vueApp, result.stores, result.profile);
			})
			.catch(function () {
				// Profile never loaded — user didn't open a shift, etc.
			});
	}

	function onProfileReady(vueApp, stores, profile) {
		// Check if hotel room integration is enabled on this POS Profile
		if (!profile.posa_enable_hotel_room) return;

		// Also verify the dagaarsoft API is available
		injectWidget(vueApp, stores, profile);

		// Re-inject if the invoice panel re-renders (e.g. navigating back to POS view)
		var observer = new MutationObserver(function () {
			if (!document.getElementById("dg-hotel-room-widget")) {
				var target = findInvoiceInsertionPoint();
				if (target) {
					injectWidget(vueApp, stores, profile);
				}
			}
		});
		var appRoot = document.querySelector(".v-application") || document.body;
		observer.observe(appRoot, { childList: true, subtree: true });

		// Store observer reference for cleanup
		window.__dgHotelObserver = observer;
	}

	// ── Find where to insert the widget in POSA's DOM ────────────────────────
	function findInvoiceInsertionPoint() {
		// Strategy: Find the Customer Details card and insert after it
		// POSA uses: .invoice-section-card.customer-card or the first .invoice-section-card
		var customerCard = document.querySelector(
			".invoice-section-card.customer-card"
		);
		if (customerCard) return customerCard;

		// Fallback: find card with "Customer Details" heading
		var headings = document.querySelectorAll(".invoice-section-heading__title");
		for (var i = 0; i < headings.length; i++) {
			var text = (headings[i].textContent || "").trim().toLowerCase();
			if (text.indexOf("customer") !== -1) {
				var card = headings[i].closest(".invoice-section-card");
				if (card) return card;
			}
		}

		// Last fallback: first invoice section card
		var firstCard = document.querySelector(".invoice-section-card");
		return firstCard || null;
	}

	// ── Build and inject the widget ──────────────────────────────────────────
	function injectWidget(vueApp, stores, profile) {
		if (document.getElementById("dg-hotel-room-widget")) return;

		var insertAfter = findInvoiceInsertionPoint();
		if (!insertAfter) return;

		// Create card container matching POSA's styling
		var card = document.createElement("div");
		card.id = "dg-hotel-room-widget";
		card.className = "v-card v-card--flat invoice-section-card pos-themed-card";
		card.innerHTML = buildWidgetHTML();

		// Insert after the customer card
		insertAfter.parentNode.insertBefore(card, insertAfter.nextSibling);

		// Bind events
		bindWidgetEvents(card, stores, profile);
	}

	function buildWidgetHTML() {
		return (
			'<div class="invoice-section-heading" style="padding:6px 12px 2px">' +
			'<h3 class="invoice-section-heading__title" style="font-size:12px;font-weight:600;opacity:0.7;text-transform:uppercase;letter-spacing:0.5px">Hotel Room</h3>' +
			"</div>" +
			'<div style="padding:4px 12px 8px">' +
			'<div style="display:flex;gap:6px;align-items:center">' +
			// Room selector
			'<div style="flex:1;min-width:0">' +
			'<select id="dg-room-select" style="' +
			"width:100%;padding:7px 10px;border:1px solid var(--pos-border-color, #e2e8f0);" +
			"border-radius:6px;font-size:13px;background:var(--pos-input-bg, #fff);" +
			'color:var(--pos-text-primary, #2d3748);outline:none;transition:border-color 0.2s">' +
			'<option value="">-- Select Room --</option>' +
			"</select>" +
			"</div>" +
			// Guest info area
			'<div id="dg-guest-info" style="min-width:100px;font-size:11px;color:var(--pos-text-primary,#333);display:none">' +
			'<div id="dg-guest-name" style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>' +
			'<div id="dg-guest-balance" style="color:#e53e3e;font-size:10px;display:none"></div>' +
			"</div>" +
			// Links area
			'<div id="dg-hotel-links" style="display:none;gap:4px;align-items:center;flex-shrink:0">' +
			'<a id="dg-link-stay" href="#" target="_blank" style="' +
			"font-size:10px;padding:2px 6px;border:1px solid rgb(var(--v-theme-primary,66,133,244));" +
			"border-radius:4px;color:rgb(var(--v-theme-primary,66,133,244));text-decoration:none;" +
			'white-space:nowrap">⛏ Stay</a>' +
			'<a id="dg-link-folio" href="#" target="_blank" style="' +
			"font-size:10px;padding:2px 6px;border:1px solid #ed8936;" +
			'border-radius:4px;color:#ed8936;text-decoration:none;white-space:nowrap">📋 Folio</a>' +
			"</div>" +
			// Clear button
			'<button id="dg-clear-room" style="' +
			"padding:4px 8px;background:#fed7d7;border:none;border-radius:4px;" +
			'cursor:pointer;font-size:11px;color:#e53e3e;display:none">✕</button>' +
			"</div>" +
			"</div>"
		);
	}

	function bindWidgetEvents(card, stores, profile) {
		var select = card.querySelector("#dg-room-select");
		var guestInfoEl = card.querySelector("#dg-guest-info");
		var guestNameEl = card.querySelector("#dg-guest-name");
		var guestBalEl = card.querySelector("#dg-guest-balance");
		var linksEl = card.querySelector("#dg-hotel-links");
		var linkStay = card.querySelector("#dg-link-stay");
		var linkFolio = card.querySelector("#dg-link-folio");
		var clearBtn = card.querySelector("#dg-clear-room");

		var currentGuestInfo = null;

		// Load occupied rooms
		function loadRooms() {
			frappe.call({
				method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.room_utils.get_all_occupied_rooms",
				args: {},
				async: true,
				callback: function (r) {
					if (!r.message) return;
					var rooms = r.message;
					var currentVal = select.value;
					// Preserve selection
					select.innerHTML = '<option value="">-- Select Room --</option>';
					rooms.forEach(function (room) {
						var opt = document.createElement("option");
						opt.value = room.name;
						opt.textContent =
							"Room " +
							room.name +
							" — " +
							(room.current_guest || "");
						select.appendChild(opt);
					});
					if (currentVal) select.value = currentVal;
				},
			});
		}

		// Room change handler
		select.addEventListener("change", function () {
			var roomName = select.value;
			if (!roomName) {
				clearRoom();
				return;
			}
			frappe.call({
				method: "dagaarsoft_hospitality.dagaarsoft_hospitality.utils.posa_integration.get_room_billing_info",
				args: { room: roomName },
				callback: function (r) {
					if (!r.message) return;
					var info = r.message;
					currentGuestInfo = info;
					applyToInvoice(info, roomName);
					showGuestInfo(info);
				},
				error: function () {
					clearRoom();
					frappe.show_alert({
						message: "No active guest in Room " + roomName,
						indicator: "red",
					});
				},
			});
		});

		// Clear button
		clearBtn.addEventListener("click", function () {
			select.value = "";
			clearRoom();
		});

		function applyToInvoice(info, roomName) {
			// Set hotel fields on invoice doc via Pinia
			if (stores.invoice && stores.invoice.mergeInvoiceDoc) {
				stores.invoice.mergeInvoiceDoc({
					hotel_room: roomName,
					hotel_stay: info.guest_stay || "",
					hotel_folio: info.guest_folio || "",
					hotel_guest_name: info.guest_name || "",
				});
			}

			// Set customer via the customers store (triggers full POSA customer flow)
			if (
				info.customer &&
				stores.customers &&
				stores.customers.setSelectedCustomer
			) {
				stores.customers.setSelectedCustomer(info.customer);
			}

			frappe.show_alert({
				message:
					"Room " + roomName + ": " + (info.guest_name || ""),
				indicator: "green",
			});
		}

		function showGuestInfo(info) {
			guestInfoEl.style.display = "block";
			guestNameEl.textContent = "✓ " + (info.guest_name || "");

			if (info.balance_due && parseFloat(info.balance_due) > 0) {
				guestBalEl.style.display = "block";
				guestBalEl.textContent =
					"Bal: " +
					parseFloat(info.balance_due).toLocaleString("en", {
						minimumFractionDigits: 2,
					});
			} else {
				guestBalEl.style.display = "none";
			}

			linksEl.style.display = "flex";
			if (info.guest_stay) {
				linkStay.href = frappe.utils.get_url_to_form(
					"Guest Stay",
					info.guest_stay
				);
				linkStay.style.display = "inline-block";
			} else {
				linkStay.style.display = "none";
			}
			if (info.guest_folio) {
				linkFolio.href = frappe.utils.get_url_to_form(
					"Guest Folio",
					info.guest_folio
				);
				linkFolio.style.display = "inline-block";
			} else {
				linkFolio.style.display = "none";
			}

			clearBtn.style.display = "inline-block";
		}

		function clearRoom() {
			currentGuestInfo = null;
			guestInfoEl.style.display = "none";
			guestBalEl.style.display = "none";
			linksEl.style.display = "none";
			clearBtn.style.display = "none";

			if (stores.invoice && stores.invoice.mergeInvoiceDoc) {
				stores.invoice.mergeInvoiceDoc({
					hotel_room: "",
					hotel_stay: "",
					hotel_folio: "",
					hotel_guest_name: "",
				});
			}
		}

		// Watch for invoice clear (new sale) — reset widget
		if (stores.invoice && stores.invoice.$subscribe) {
			stores.invoice.$subscribe(function (mutation, state) {
				var doc = state.invoiceDoc;
				if (!doc || !doc.hotel_room) {
					if (select.value) {
						select.value = "";
						clearRoom();
					}
				}
			});
		}

		// Load rooms on init and refresh every 2 minutes
		loadRooms();
		var refreshTimer = setInterval(loadRooms, 120000);

		// Cleanup on page unload
		window.addEventListener("beforeunload", function () {
			clearInterval(refreshTimer);
		});
	}

	// ── Kick off ─────────────────────────────────────────────────────────────
	// Use frappe.after_ajax to ensure page JS is loaded, then bootstrap
	if (typeof frappe !== "undefined" && frappe.after_ajax) {
		frappe.after_ajax(function () {
			setTimeout(bootstrap, 500);
		});
	} else {
		// Fallback
		document.addEventListener("DOMContentLoaded", function () {
			setTimeout(bootstrap, 1500);
		});
	}
})();
