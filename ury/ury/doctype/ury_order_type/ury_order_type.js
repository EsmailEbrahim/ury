// Copyright (c) 2025, Tridz Technologies Pvt. Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("URY Order Type", {
	refresh(frm) {
        frm.set_query("default_table", function () {
			return {
				filters: {
					is_take_away: 1,
				},
			};
		});
	},
});
