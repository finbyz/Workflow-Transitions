# Copyright (c) 2025, finbyz tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import timedelta
from frappe.utils import time_diff_in_hours
from frappe import _
from collections import namedtuple
from frappe.utils.safe_exec import get_safe_globals
from frappe.utils import nowdate


class DocumentShift(Document):
    def get_context(self, doc):
        Frappe = namedtuple("frappe", ["utils"])
        return {
            "doc": doc,
            "nowdate": nowdate,
            "frappe": Frappe(utils=get_safe_globals().get("frappe").get("utils")),
        }
        
    def validate(self):
        for row in self.shift_details:
            if row.condition:
                temp_doc = frappe.new_doc(self.doctype_name)                
                if row.condition:
                    try:
                        frappe.safe_eval(row.condition, None, self.get_context(temp_doc.as_dict()))
                    except Exception:
                        frappe.throw(_("The Condition '{0}' is invalid").format(row.condition))