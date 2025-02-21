import frappe

def execute(filters=None):
    # Ensure that the filter for Doctype and Document is provided
    doctype = filters.get("doctype")
    document_name = filters.get("document")
    
    if filters.get("doctype") and not filters.get("document"):
        columns = [
            {"fieldname": "ID", "label": "ID", "fieldtype": "Link", "options": "State Change"},  # Corrected "option" to "options"
            {"fieldname": "Doctype", "label": "Doctype", "fieldtype": "Data"},
            {"fieldname": "Document Type", "label": "Document Type", "fieldtype": "Data"},
        ]
        
        # Fetch distinct workflow states for the selected doctype
        workflow_states = frappe.db.sql("""
            SELECT DISTINCT sci.workflow_state
            FROM `tabState Change` AS sc
            JOIN `tabState Change Items` AS sci
            ON sc.name = sci.parent
            WHERE sc.doctype_name = %s
        """, (doctype,), as_dict=True)

        # Dynamically create columns based on the number of workflow states
        for i, state in enumerate(workflow_states, start=1):
            columns.append({"fieldname": f"Username_{i}", "label": f"Username (State {i})", "fieldtype": "Data"})
            columns.append({"fieldname": f"Role_{i}", "label": f"Role (State {i})", "fieldtype": "Data"})
            columns.append({"fieldname": f"Workflow_State_{i}", "label": f"Workflow State (State {i})", "fieldtype": "Data"})
            columns.append({"fieldname": f"Modification_Time_{i}", "label": f"Modification Time (State {i})", "fieldtype": "Data"})
        
        # Fetch data for all state changes related to the selected doctype
        state_changes = frappe.db.sql("""
            SELECT 
                sc.name As name,
                sc.doctype_name AS doctype,
                sc.document_name AS document_type,
                sci.username AS username,
                sci.role AS role,
                sci.workflow_state AS workflow_state,
                sci.modification_time AS modification_time,
                ROW_NUMBER() OVER (PARTITION BY sc.document_name ORDER BY sci.modification_time) AS row_num
            FROM 
                `tabState Change` AS sc
            JOIN 
                `tabState Change Items` AS sci
            ON 
                sc.name = sci.parent
            WHERE 
                sc.doctype_name = %s
        """, (doctype,), as_dict=True)

        # Prepare the data for the report, ensuring one row per document
        data = {}
        for change in state_changes:
            # Initialize the row if it doesn't exist
            if change.document_type not in data:
                data[change.document_type] = {
                    "id": change.name,  # Add the "id" key here
                    "doctype": change.doctype,
                    "document_type": change.document_type,
                }
            
            # Map the data to the respective columns based on row number
            row_num = change.row_num
            username_column = f"Username_{row_num}"
            role_column = f"Role_{row_num}"
            state_column = f"Workflow_State_{row_num}"
            time_column = f"Modification_Time_{row_num}"

            # Convert datetime to string for modification_time
            modification_time_str = change.modification_time.strftime("%Y-%m-%d %H:%M:%S") if change.modification_time else "N/A"

            # Assign the values for each workflow state
            data[change.document_type][username_column] = change.username
            data[change.document_type][role_column] = change.role
            data[change.document_type][state_column] = change.workflow_state
            data[change.document_type][time_column] = modification_time_str

        # Convert the dictionary to a list of rows
        report_data = []
        for document_type, row_data in data.items():
            row = [
                row_data.get("id", "N/A"),  # Ensure id is included
                row_data["doctype"],
                row_data["document_type"],
            ]
            
            # Append the workflow state columns dynamically
            for i in range(1, len(workflow_states) + 1):
                row.append(row_data.get(f"Username_{i}", "N/A"))
                row.append(row_data.get(f"Role_{i}", "N/A"))
                row.append(row_data.get(f"Workflow_State_{i}", "N/A"))
                row.append(row_data.get(f"Modification_Time_{i}", "N/A"))
            
            report_data.append(row)

        return columns, report_data
    
    elif filters.get("doctype") and filters.get("document"):
        columns = [
            {"fieldname": "ID", "label": "ID", "fieldtype": "Link", "options": "State Change"},  # Corrected "option" to "options"
            {"fieldname": "Doctype", "label": "Doctype", "fieldtype": "Data"},
            {"fieldname": "Document Type", "label": "Document Type", "fieldtype": "Data"},
            {"fieldname": "Username", "label": "Username", "fieldtype": "Data"},
            {"fieldname": "Role", "label": "Role", "fieldtype": "Data"},
            {"fieldname": "Workflow States", "label": "Workflow States", "fieldtype": "Data"},
            {"fieldname": "Modification Time", "label": "Modification Time", "fieldtype": "Data"},
        ]

        # Fetch data from State Change and join with State Change Items
        state_changes = frappe.db.sql("""
            SELECT 
                sc.name as id,
                sc.doctype_name AS doctype,
                sc.document_name AS document_type,
                sci.username AS username,
                sci.role AS role,
                sci.workflow_state AS workflow_state,
                sci.modification_time AS modification_time
            FROM 
                `tabState Change` AS sc
            JOIN 
                `tabState Change Items` AS sci
            ON 
                sc.name = sci.parent
            WHERE 
                sc.doctype_name = %s AND sc.document_name = %s
        """, (doctype, document_name), as_dict=True)

        # Prepare the data for the report
        data = []
        for change in state_changes:
            # Convert datetime to string for modification_time
            modification_time_str = change.modification_time.strftime("%Y-%m-%d %H:%M:%S") if change.modification_time else "N/A"
            data.append([
                change.id,
                change.doctype,
                change.document_type,
                change.username,
                change.role,
                change.workflow_state,
                modification_time_str,
            ])

        return columns, data
