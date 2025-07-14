// Copyright (c) 2025, info@finbyz.tech and contributors
// For license information, please see license.txt

frappe.query_reports["State Change User"] = {
	"filters": [
		{
			"fieldname": "doctype",
			"label": __("Select Doctype"),
			"fieldtype": "Link",
			"options": "DocType",
			"reqd": 1
		},
		{
			fieldname: "document",
			label: __("Select Document"),
			fieldtype: "Dynamic Link",
			get_options: function () {
				let doctype = frappe.query_report.get_filter_value("doctype");
				if (!doctype) {
					frappe.throw(__("Please select Doctype first"));
				}
				return doctype;
			}
		},
		{
			"fieldname": "user",
			"label": __("User"),
			"fieldtype": "Link",
			"options": "User"
		}
	]
};
