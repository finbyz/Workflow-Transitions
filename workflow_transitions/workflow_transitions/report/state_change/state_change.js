frappe.query_reports["State change"] = {
	"filters": [
		{
			"fieldname": "doctype",
			"label": __("Select Doctype"),
			"fieldtype": "Link",
			"options": "DocType",
			"reqd":1,

		},
		{
			fieldname: "document",
			label: __("Select Document"),
			fieldtype: "Dynamic Link",
			get_options: function () {
				let doctype = frappe.query_report.get_filter_value("doctype");
				if (!doctype) {
					frappe.throw(__("Please select Party Type first"));
				}
				return doctype;
			},
		},
	]
};
