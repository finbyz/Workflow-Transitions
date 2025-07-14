import frappe
from datetime import timedelta
from collections import defaultdict

def format_duration(td):
    total_seconds = int(td.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

def execute(filters=None):
    doctype = filters.get("doctype")
    document_name = filters.get("document")
    user_filter = filters.get("user")

    detailed_columns = [
        {"fieldname": "workflow_state", "label": "Workflow State", "fieldtype": "Data"},
        {"fieldname": "username", "label": "Username", "fieldtype": "Data"},
        {"fieldname": "role", "label": "Role", "fieldtype": "Data"},
        {"fieldname": "modification_time", "label": "Modification Time", "fieldtype": "Datetime"},
        {"fieldname": "duration", "label": "Time Taken Since Previous", "fieldtype": "Data"},
    ]

    # Case 4: Doctype + Document + User
    if doctype and document_name and user_filter:
        all_transitions = frappe.db.sql("""
            SELECT sci.workflow_state, sci.username, sci.role, sci.modification_time
            FROM `tabState Change` sc
            JOIN `tabState Change Items` sci ON sc.name = sci.parent
            WHERE sc.doctype_name = %s AND sc.document_name = %s
            ORDER BY sci.modification_time
        """, (doctype, document_name), as_dict=True)

        user_transitions = [row for row in all_transitions if row.username == user_filter]

        if not user_transitions:
            return detailed_columns, [{
                "workflow_state": "",
                "username": "",
                "role": "",
                "modification_time": None,
                "duration": "User has no actions on this document."
            }]

        data = []
        durations = []

        for user_row in user_transitions:
            user_time = user_row.modification_time
            previous_time = None

            for row in reversed(all_transitions):
                if row.modification_time < user_time:
                    previous_time = row.modification_time
                    break

            if previous_time:
                delta = user_time - previous_time
                delta_str = format_duration(delta)
                durations.append(delta)
            else:
                delta_str = "0"

            data.append({
                "workflow_state": user_row.workflow_state,
                "username": user_row.username,
                "role": user_row.role,
                "modification_time": user_row.modification_time,
                "duration": delta_str
            })

        avg_duration = format_duration(sum(durations, timedelta()) / len(durations)) if durations else "0"
        data.append({
            "workflow_state": "",
            "username": "",
            "role": "",
            "modification_time": None,
            "duration": f"Average Duration: {avg_duration}"
        })

        return detailed_columns, data

    # Case 1: Doctype + Document
    elif doctype and document_name:
        transitions = frappe.db.sql("""
            SELECT sci.workflow_state, sci.username, sci.role, sci.modification_time
            FROM `tabState Change` AS sc
            JOIN `tabState Change Items` AS sci ON sc.name = sci.parent
            WHERE sc.doctype_name = %s AND sc.document_name = %s
            ORDER BY sci.modification_time
        """, (doctype, document_name), as_dict=True)

        data = []
        durations = []
        prev_time = None

        for idx, row in enumerate(transitions):
            curr_time = row.modification_time
            if idx == 0 or not prev_time:
                delta = timedelta()
                delta_str = "0"
            else:
                delta = curr_time - prev_time
                delta_str = format_duration(delta)
                durations.append(delta)

            data.append({
                "workflow_state": row.workflow_state,
                "username": row.username,
                "role": row.role,
                "modification_time": curr_time,
                "duration": delta_str
            })
            prev_time = curr_time

        avg_duration = format_duration(sum(durations, timedelta()) / len(durations)) if durations else "0"
        data.append({
            "workflow_state": "",
            "username": "",
            "role": "",
            "modification_time": None,
            "duration": f"Average Duration: {avg_duration}"
        })

        return detailed_columns, data

    # Case 2: Doctype + User
    elif doctype and user_filter:
        columns = [
            {"fieldname": "username", "label": "User", "fieldtype": "Link", "options": "User"},
            {"fieldname": "avg_duration", "label": "Avg Duration (HH:MM:SS)", "fieldtype": "Data"},
            {"fieldname": "transition_count", "label": "Transition Count", "fieldtype": "Int"},
        ]

        transitions = frappe.db.sql("""
            SELECT sc.document_name, sci.username, sci.modification_time
            FROM `tabState Change` sc
            JOIN `tabState Change Items` sci ON sc.name = sci.parent
            WHERE sc.doctype_name = %s AND sci.username = %s
            ORDER BY sc.document_name, sci.modification_time
        """, (doctype, user_filter), as_dict=True)

        durations = []
        prev_doc = None
        prev_time = None

        for row in transitions:
            doc = row.document_name
            time = row.modification_time
            if prev_doc == doc and prev_time:
                delta = time - prev_time
                durations.append(delta)
            prev_doc = doc
            prev_time = time

        avg_str = format_duration(sum(durations, timedelta()) / len(durations)) if durations else "0"

        return columns, [{
            "username": user_filter,
            "avg_duration": avg_str,
            "transition_count": len(durations)
        }]

    # Case 3: Doctype only (summary of all users)
    elif doctype:
        columns = [
            {"fieldname": "username", "label": "User", "fieldtype": "Link", "options": "User"},
            {"fieldname": "avg_duration", "label": "Avg Duration (HH:MM:SS)", "fieldtype": "Data"},
            {"fieldname": "transition_count", "label": "Transition Count", "fieldtype": "Int"},
        ]

        transitions = frappe.db.sql("""
            SELECT sc.document_name, sci.username, sci.modification_time
            FROM `tabState Change` AS sc
            JOIN `tabState Change Items` AS sci ON sc.name = sci.parent
            WHERE sc.doctype_name = %s
            ORDER BY sc.document_name, sci.username, sci.modification_time
        """, (doctype,), as_dict=True)

        user_durations = defaultdict(list)
        prev_doc = None
        prev_user = None
        prev_time = None

        for row in transitions:
            doc = row.document_name
            user = row.username
            time = row.modification_time

            if prev_doc == doc and prev_user == user and prev_time:
                delta = time - prev_time
                user_durations[user].append(delta)

            prev_doc = doc
            prev_user = user
            prev_time = time

        data = []
        for user, durations in user_durations.items():
            if durations:
                avg = sum(durations, timedelta()) / len(durations)
                avg_str = format_duration(avg)
                data.append({
                    "username": user,
                    "avg_duration": avg_str,
                    "transition_count": len(durations)
                })

        return columns, data