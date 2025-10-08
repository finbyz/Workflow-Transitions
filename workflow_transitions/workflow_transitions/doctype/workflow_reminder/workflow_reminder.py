# Copyright (c) 2025, finbyz tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.email.doctype.notification.notification import get_context
import datetime
from frappe.utils import now_datetime

class WorkflowReminder(Document):
    def validate(self):
        data = frappe.get_doc("Document Shift", self.doctype_name)
        
        # Default total shift time
        self.total_shift_time = 0

        # Evaluate conditions inside Document Shift child table
        for row in data.shift_details:
            context = get_context(frappe.get_doc(self.doctype_name, self.document_name))
            if not row.condition:
                self.total_shift_time = row.total_time
            else:
                condition_result = frappe.safe_eval(row.condition, None, context)
                if condition_result:
                    self.total_shift_time = row.total_time  # Assuming row.total_time is in hours
        if data.overdue_time:
            self.overdue_shift_time = data.overdue_time
        if data.role:
            self.role = data.role

        # Ensure required fields are available
        if not self.time or not self.total_shift_time:
            frappe.throw("Missing 'time' or 'total_shift_time' for Workflow Reminder calculation")

        from_time = self.time
        total_shift_hours = self.total_shift_time
        start_time = convert_to_time(data.start_time)
        end_time = convert_to_time(data.end_time)
        break_start_time = convert_to_time(data.break_start_time)
        break_end_time = convert_to_time(data.break_end_time)

        # Calculate the target datetime
        target_time = calculate_target_datetime(
            from_time, total_shift_hours, start_time, end_time, break_start_time, break_end_time
        )
        overdue_time = calculate_target_datetime(
            from_time, self.overdue_shift_time, start_time, end_time, break_start_time, break_end_time
        )
        # Store the calculated target time
        self.notification_send_time = target_time
        self.overdue_time = overdue_time

                
def send_reminder(data):
    try:
        # Fetch Active Workflow
        workflow = frappe.get_value("Workflow", {"document_type": data.doctype_name, "is_active": 1}, "name")
        if not workflow:
            frappe.log_error("Active Workflow not found", "Workflow Reminder")
            return

        workflow_doc = frappe.get_doc("Workflow", workflow)
        current_state = data.workflow_state
        next_roles = set()

        # Loop through transitions and find eligible next state(s) from current_state
        for transition in workflow_doc.transitions:
            if transition.state == current_state:
                # Check condition if exists
                if transition.condition:
                    if not frappe.safe_eval(transition.condition, {"doc": frappe.get_doc(data.doctype_name, data.document_name)}):
                        continue  # Skip this transition if condition fails
                # If condition passed or not required, add role to notify
                if transition.allowed:
                    next_roles.add(transition.allowed)

        if not next_roles:
            frappe.log_error(f"No valid next role found from state '{current_state}'", "Workflow Reminder")
            return

        # Fetch users based on the role(s)
        users = frappe.get_all("Has Role", 
            filters={"role": ["in", list(next_roles)]}, 
            fields=["parent"])  # 'parent' is the user
        
        user_list = []
        doctype_data = frappe.get_doc(data.doctype_name, data.document_name)
        
        for row in users:
            user_id = row.parent  # Get actual user ID string
            if frappe.db.exists("User", user_id) and user_id != "Administrator":
                if frappe.db.get_value("Workflow", {"document_type": data.doctype_name, "is_active": 1}, "send_email_as_project_condition") == 1:
                    if check_project_permissions(user_id, doctype_data):
                        user_list.append(user_id)
                else:
                    user_list.append(user_id)
        
        if not user_list:
            frappe.log_error(f"No users found for roles: {next_roles}", "Workflow Reminder")
            user_list = [row.parent for row in users]

        if data.notification_send:
            return  # Already sent

        # Create Notification Logs and (Optional) Send Emails
        user_list = list(set(user_list))
        print(user_list)
        for user in user_list:
            if not user:
                continue  # Skip this user if no email is found

            # Create notification log
            notification = frappe.new_doc("Notification Log")
            notification.for_user = user  # Directly assign the user ID string
            notification.type = "Alert"
            notification.document_type = data.doctype_name
            notification.document_name = data.document_name
            notification.subject = data.description or f"Reminder for {data.document_name}"
            notification.insert()

            doc_url = f"{frappe.utils.get_url()}/app/{frappe.scrub(data.doctype_name)}/{data.document_name}"
            # (Optional) Email sending
            email_body = f"""
            Dear {user},<br><br>
            This is a reminder to take action on document **{data.document_name}** ({data.doctype_name}).<br>
            This is a reminder to take action on document <a href="{doc_url}"><b>{data.document_name}</b></a>  ({data.doctype_name}).<br>
            Current Workflow Stage: **{current_state}**<br>
            Please review and proceed as per the workflow process.<br>
            """
            frappe.sendmail(
                recipients=user,
                subject="Workflow Reminder Alert",
                message=email_body,
                now=frappe.flags.in_test,
            )

    except Exception as e:
        frappe.log_error(f"Failed to send reminder: {str(e)}", "Workflow Reminder")
                
def check_project_permissions(user, doc):
    all_documents = [doc] + doc.get_all_children()
    
    for d in all_documents:
        meta = frappe.get_meta(d.doctype)
        for row in meta.get_link_fields():
            if row.options == "Project" and ((d.get(row.fieldname) and not frappe.db.exists("User Permission", {"user": user, "allow": "Project","for_value": d.get(row.fieldname)})) or not d.get(row.fieldname)):
                
                return False
    
    return True

def send_notification():
    try:
        workflow_reminders = frappe.get_all(
            "Workflow Reminder",
            fields=["name", "time", "doctype_name", "document_name", "description", "total_shift_time","notification_send_time","workflow_state"],
            filters={"notification_send": 0}
        )
        for reminder in workflow_reminders:
            if reminder.notification_send_time <= now_datetime() and frappe.db.get_value(reminder.doctype_name,reminder.document_name,"workflow_state") == reminder.workflow_state and frappe.db.get_value(reminder.doctype_name,reminder.document_name,"docstatus") == 0:
                workflow_doc = frappe.get_doc("Workflow Reminder", reminder.get("name"))
                send_reminder(workflow_doc)
                workflow_doc.db_set("notification_send", 1)
                
    except Exception as e:
        frappe.log_error(f"Error in sending notification {str(e)}", "Workflow Reminder Error")

def convert_to_time(value):
    """Convert timedelta or string to time object."""
    if isinstance(value, datetime.timedelta):
        return (datetime.datetime.min + value).time()
    elif isinstance(value, str):
        return datetime.datetime.strptime(value, "%H:%M:%S").time()
    return value  # Already a time object

def is_holiday(date):
    if frappe.db.exists("Holiday", {"holiday_date": date}):
        return True
    return False


def calculate_target_datetime(from_time, total_shift_hours, start_time, end_time, break_start_time, break_end_time):
    """Calculate the target datetime when total_shift_hours are completed considering breaks and holidays."""

    # ✅ Safe datetime parsing with or without microseconds
    if isinstance(from_time, str):
        try:
            from_time = datetime.datetime.strptime(from_time, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            from_time = datetime.datetime.strptime(from_time, "%Y-%m-%d %H:%M:%S")

    if total_shift_hours <= 0:
        return from_time  # No work required

    total_required = datetime.timedelta(hours=total_shift_hours)
    total_counted = datetime.timedelta()
    current_time = from_time

    while total_counted < total_required:
        current_date = current_time.date()

        # ✅ Skip holiday
        if is_holiday(current_date):
            current_time = datetime.datetime.combine(current_date + datetime.timedelta(days=1), start_time)
            continue

        # ✅ Shift timings for the day
        shift_start = datetime.datetime.combine(current_date, start_time)
        shift_end = datetime.datetime.combine(current_date, end_time)
        break_start = datetime.datetime.combine(current_date, break_start_time)
        break_end = datetime.datetime.combine(current_date, break_end_time)

        # If current time is before shift start, move to shift start
        if current_time < shift_start:
            current_time = shift_start

        # If current time is after shift end, move to next day's shift start
        if current_time >= shift_end:
            current_time = datetime.datetime.combine(current_date + datetime.timedelta(days=1), start_time)
            continue

        # ✅ Calculate working period before break
        work_end = min(shift_end, break_start)

        if current_time < work_end:
            available = work_end - current_time
            if total_counted + available >= total_required:
                return current_time + (total_required - total_counted)
            total_counted += available
            current_time = break_end  # Skip break
            continue

        # ✅ After break
        if current_time >= break_end and current_time < shift_end:
            available = shift_end - current_time
            if total_counted + available >= total_required:
                return current_time + (total_required - total_counted)
            total_counted += available
            current_time = datetime.datetime.combine(current_date + datetime.timedelta(days=1), start_time)
            continue

        # ✅ If inside break, skip to break end
        if break_start <= current_time < break_end:
            current_time = break_end
            continue

        # ✅ Else move to next day
        current_time = datetime.datetime.combine(current_date + datetime.timedelta(days=1), start_time)

    # Safety net return (should not hit ideally)
    return current_time

def send_overdue_notification():
    try:
        overdue_reminders = frappe.get_all(
            "Workflow Reminder",
            fields=["name", "doctype_name", "document_name", "description", "overdue_shift_time","overdue_time","workflow_state"],
            filters={"notification_send": 1,"overdue_shift_time": [">", 0]}
        )
        for reminder in overdue_reminders:
            if reminder.overdue_time <= now_datetime() and frappe.db.get_value(reminder.doctype_name,reminder.document_name,"workflow_state") == reminder.workflow_state and frappe.db.get_value(reminder.doctype_name,reminder.document_name,"docstatus") == 0:
                workflow_doc = frappe.get_doc("Workflow Reminder", reminder.get("name"))
                send_overdue_email_reminder(workflow_doc)
                workflow_doc.db_set("overdue_notification_send", 1)
                
    except Exception as e:
        frappe.log_error(f"Error in sending overdue notification {str(e)}", "Workflow Reminder Error")
        # Check if overdue time is set and send notification
                
        
def send_overdue_email_reminder(data):
    try:
        frappe.logger().info(f"[Reminder Debug] Triggered for: {data.name} | Doctype: {data.doctype_name} | Doc: {data.document_name} | Role: {data.role}")

        workflow = frappe.get_value("Workflow", {"document_type": data.doctype_name, "is_active": 1}, "name")
        if not workflow:
            frappe.log_error("Active Workflow not found", "Workflow Reminder")
            return

        workflow_doc = frappe.get_doc("Workflow", workflow)
        current_state = data.workflow_state
        next_roles = set()

        # Find roles responsible for next actions
        for transition in workflow_doc.transitions:
            if transition.state == current_state:
                if transition.condition:
                    try:
                        if not frappe.safe_eval(transition.condition, {"doc": frappe.get_doc(data.doctype_name, data.document_name)}):
                            continue
                    except Exception as eval_err:
                        frappe.log_error(f"Error evaluating condition: {transition.condition} — {str(eval_err)}", "Workflow Reminder")
                        continue
                if transition.allowed:
                    next_roles.add(transition.allowed)

        role_list = ", ".join(next_roles)

        # Fetch valid users for next roles
        users_with_next_roles = frappe.get_all(
            "Has Role",
            filters={"role": ["in", list(next_roles)]},
            fields=["parent"]
        )

        valid_users = set()
        for user in users_with_next_roles:
            if not frappe.db.exists("User", user.parent):
                # frappe.log_error(f"[Reminder Debug] Skipping invalid user: {user.parent} (User not found)", "Workflow Reminder")
                continue

            user_doc = frappe.get_doc("User", user.parent)
            if user_doc.enabled and user_doc.user_type == "System User" and user_doc.email and user_doc != "Administrator":
                valid_users.add(user_doc.email)

        users_list_html = "<br>".join(valid_users)

        # 🔸 Fetch users based on `data.role` (used for sending notifications)
        if not data.role:
            frappe.log_error("Missing `data.role` in Workflow Reminder", "Workflow Reminder")
            return

        users = frappe.get_all(
            "Has Role",
            filters={"role": data.role},
            fields=["parent"]
        )

        if not users:
            frappe.log_error(f"No users found for role: {data.role}", "Workflow Reminder")
            return

        base_url = frappe.utils.get_url()
        doc_link = f"{base_url}/app/{data.doctype_name.lower().replace(' ', '-')}/{data.document_name}"

        for user in users:
            if not user.parent or not frappe.db.exists("User", user.parent):
                frappe.log_error(f"[Reminder Debug] Skipping notification: Invalid or missing user {user.parent}", "Workflow Reminder")
                continue

            # Create notification log
            notification = frappe.new_doc("Notification Log")
            notification.for_user = user.parent
            notification.type = "Alert"
            notification.document_type = data.doctype_name
            notification.document_name = data.document_name
            notification.subject = f"Overdue Reminder for {data.document_name}"
            notification.insert()

            # Compose and send email
            email_body = f"""
            Dear User,<br><br>
            The following document has been delayed for more than the expected time:<br>
            <b>Document Type:</b> {data.doctype_name}<br>
            <b>ID:</b> {data.document_name}<br>
            <b>Role Holder(s) Responsible for Next Action:</b> {role_list}<br><br>
            <b>Users with Next Roles:</b><br>
            {users_list_html}<br><br>
            <b>Document Link:</b> <a href="{doc_link}">{data.document_name}</a><br><br>
            Please coordinate with the responsible Role Holders to expedite the Approval/Rejection on the Document.<br>
            Thank you and have a nice day.
            """

            frappe.sendmail(
                recipients=user.parent,
                subject="Workflow Overdue Reminder Alert",
                message=email_body,
                now=frappe.flags.in_test,
            )

    except Exception as e:
        frappe.log_error(f"Failed to send overdue reminder: {str(e)}", "Workflow Reminder")
