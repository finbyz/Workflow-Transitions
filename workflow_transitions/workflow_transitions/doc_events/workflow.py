import frappe 
def before_validate(self,method):
    if self.is_active and self.track_state_transitions:
        if frappe.db.exists("Server Script",f"Track State Transition For {self.document_type}"):
            frappe.delete_doc("Server Script",f"Track State Transition For {self.document_type}")
        server_script = frappe.new_doc("Server Script")
        server_script.name = f"Track State Transition For {self.document_type}"
        server_script.script_type = "DocType Event"
        server_script.reference_doctype = self.document_type
        server_script.doctype_event = "Before Validate"
        server_script.script = """if doc.name:
                prev_state_query = frappe.db.sql(
                    \"\"\"
                    SELECT sci.workflow_state 
                    FROM `tabState Change Items` AS sci
                    JOIN `tabState Change` AS sc 
                        ON sci.parent = sc.name 
                        AND sc.document_name = %s 
                        AND sc.doctype_name = %s
                    ORDER BY sci.idx DESC 
                    LIMIT 1
                    \"\"\",
                    (doc.name, doc.doctype), as_dict=True)
                
                # Retrieve user's roles using a different method
                user_doc = frappe.get_doc("User", frappe.session.user)
                user_roles = [role.role for role in user_doc.roles]
                role = user_roles[0] if user_roles else "No Role"
                
                if prev_state_query:
                    prev_state = prev_state_query[0].get('workflow_state')
                    user = frappe.db.get_value("User", frappe.session.user, "full_name")
                    if prev_state != doc.workflow_state:
                        # Try to get existing document or create a new one
                        try:
                            workflow_doc = frappe.get_doc("State Change", {"document_name": doc.name, "doctype_name": doc.doctype})
                        except frappe.DoesNotExistError:
                            workflow_doc = frappe.new_doc("State Change")
                            workflow_doc.doctype_name = doc.doctype
                            workflow_doc.document_name = doc.name
                        
                        workflow_doc.append("items", {
                            "username": frappe.session.user,
                            "modification_time": frappe.utils.now(),
                            "workflow_state": doc.workflow_state,
                            "role": role  # Add role to the child table
                        })
                        workflow_doc.save(ignore_permissions=True)
                else:
                    workflow_doc = frappe.new_doc("State Change")
                    workflow_doc.doctype_name = doc.doctype
                    workflow_doc.document_name = doc.name
                    workflow_doc.append("items", {
                        "username": frappe.session.user,
                        "modification_time": frappe.utils.now(),
                        "workflow_state": doc.workflow_state,
                        "role": role  # Add role to the child table
                    })
                    workflow_doc.save(ignore_permissions=True)"""

        server_script.save()

@frappe.whitelist()
def get_workflow_fields(doc):
    data = frappe.db.sql(f"""
    select w.name as workflow_name, wds.state, wds.allow_edit
    from `tabWorkflow` as w
    join `tabWorkflow Document State` as wds on w.name = wds.parent
    where w.document_type = '{doc}' and w.is_active = 1
    order by wds.idx
    """, as_dict=True)
    return data