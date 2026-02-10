

# Copyright (c) 2026, info@finbyz.tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WorkflowEmail(Document):
	def before_validate(self):
		self.before_validate_workflow_email()

	def before_validate_workflow_email(self):
		"""
		Generic approach to create server scripts for workflow email notifications
		Similar to workflow transitions server script generation
		"""
		if self.is_active and self.enable_email_notifications:
			# Delete existing server scripts if they exist
			server_script_names = [
				f"Workflow Email Trigger for {self.document_type}",
			]
			
			for script_name in server_script_names:
				if frappe.db.exists("Server Script", script_name):
					frappe.delete_doc("Server Script", script_name)
			
			# Create the main workflow email trigger server script
			create_workflow_email_trigger_script(self)
			
			frappe.msgprint(f"Workflow Email notifications enabled for {self.document_type}")
		
		elif self.is_active and not self.enable_email_notifications:
			# Remove server scripts when email notifications are disabled
			if frappe.db.exists("Server Script", f"Workflow Email Trigger for {self.document_type}"):
				frappe.delete_doc("Server Script", f"Workflow Email Trigger for {self.document_type}")
			
			frappe.msgprint(f"Workflow Email notifications disabled for {self.document_type}")


def create_workflow_email_trigger_script(workflow_email_doc):
	"""
	Create a server script that triggers on document events
	This replaces the need for manual hooks.py configuration
	"""
	server_script = frappe.new_doc("Server Script")
	server_script.name = f"Workflow Email Trigger for {workflow_email_doc.document_type}"
	server_script.script_type = "DocType Event"
	server_script.reference_doctype = workflow_email_doc.document_type
	
	# Use After Save event to capture all state changes
	server_script.doctype_event = "After Save"
	# server_script.module = "Workflow Transitions"
	
	# Generate the script content
	server_script.script = generate_workflow_email_script(workflow_email_doc)
	
	server_script.save()


def generate_workflow_email_script(workflow_email_doc):
	"""
	Generate the server script content for workflow email triggering
	Inlined version to avoid scope issues in Frappe Server Scripts
	"""
	
	script = """
# ==========================================================
# WORKFLOW EMAIL TRIGGER - AUTO-GENERATED
# ==========================================================


# 1. Fetch State Change History
history = doc.get("state_change") or []

if not history:
    # First time save, no history yet
    new_state = doc.workflow_state
    old_state = "Draft"

else:
	
	try:
		sorted_history = sorted(history, key=lambda x: int(x.idx or 0))
	except Exception:
		# Fallback if idx is missing for some reason
		sorted_history = history

	# The record being saved right now is the last entry in the sorted list
	current_entry = sorted_history[-1]
	new_state = current_entry.workflow_state

	# The previous state is the row before the last one
	if len(sorted_history) > 1:
		old_state = sorted_history[-2].workflow_state
	else:
		old_state = "Draft"


	if old_state == new_state:
		pass
		# frappe.log_error("States are same, exiting", "Workflow Email Debug")
		# frappe.logger().info("States are same, exiting")
	else:
		# Fetch workflow email rules
		rules = frappe.get_all(
			"Workflow Email",
			filters={
				"document_type": doc.doctype,
				"is_active": 1,
				"enable_email_notifications": 1
			},
			fields=["name"]
		)
		
		# frappe.log_error(
		# 	f"Found {len(rules)} workflow email rules",
		# 	"Workflow Email Debug"
		# )
		
		for r in rules:
			workflow_email = frappe.get_doc("Workflow Email", r.name)
			
			workflows = workflow_email.get("workflows")
			if not workflows:
				continue
			
			for wf in workflows:
				# State check
				if wf.get("workflow_state") != new_state:
					continue
				
				# frappe.log_error(
				# 	f"Matched workflow state: {new_state}",
				# 	"Workflow Email Debug"
				# )
				
				# Conditional check
				conditional_doctype = wf.get("conditional_doctype")
				document_no = wf.get("document_no")
				
				if conditional_doctype and document_no:
					conditional_field = conditional_doctype.lower().replace(" ", "_")
					field_value = doc.get(conditional_field)
					
					if field_value != document_no:
						continue
				
				recipients = []
				
				# Role based
				if workflow_email.get("based_on") == "Role Based":
					roles = workflow_email.get("roles") or []
					if isinstance(roles, str):
						roles = [r.strip() for r in roles.split("\\n") if r.strip()]
					
					if roles:
						users = frappe.get_all(
							"Has Role",
							filters={
								"role": ["in", roles],
								"parenttype": "User"
							},
							pluck="parent"
						)
						
						for u in users:
							email = frappe.db.get_value("User", u, "email")
							if email:
								recipients.append(email)
				
				# User / Email based
				else:
					users = workflow_email.get("users") or []
					if isinstance(users, str):
						users = [u.strip() for u in users.split("\\n") if u.strip()]
					
					for u in users:
						if "@" in u:
							recipients.append(u)
						else:
							email = frappe.db.get_value("User", u, "email")
							if email:
								recipients.append(email)
				
				# Child table emails
				if wf.get("user"):
					extra = wf.get("user").split(",")
					for e in extra:
						e = e.strip()
						if "@" in e:
							recipients.append(e)
				
				# Add document creator email if state is Approved
				if new_state == "Approved":
					creator_email = frappe.db.get_value("User", doc.owner, "email")
					if creator_email:
						recipients.append(creator_email)
						# frappe.log_error(
						# 	f"Added document creator email: {creator_email}",
						# 	"Workflow Email Debug"
						# )
				
				# Remove duplicates
				final_recipients = []
				for rcp in recipients:
					if rcp not in final_recipients:
						final_recipients.append(rcp)
				
				if not final_recipients:
					# frappe.log_error(
					# 	"No valid recipients found",
					# 	"Workflow Email Debug"
					# )
					continue
				
				# frappe.log_error(
				# 	f"Sending email to: {final_recipients}",
				# 	"Workflow Email Debug"
				# )
				
				# ==========================================================
				# SEND EMAIL VIA BACKGROUND JOB
				# ==========================================================
				
				# Use frappe.call to execute external function (imports not allowed in server scripts)
				try:
					frappe.call(
						"workflow_transitions.workflow_transitions.doctype.workflow_email.workflow_email.enqueue_workflow_email",
						workflow_email=workflow_email,
						workflow=wf,
						doc=doc,
						recipients=final_recipients
					)
					
					# frappe.log_error(
					# 	"Email queued successfully for: " + str(final_recipients),
					# 	"Workflow Email Queued"
					# )
					
				except Exception as e:
					pass
					# frappe.log_error(
					# 	"Error queueing email: " + str(e),
					# 	"Workflow Email Queue Error"
					# )
					# frappe.logger().info("Error queueing email: " + str(e))
"""
	
	return script


@frappe.whitelist(allow_guest=True)
def enqueue_workflow_email(workflow_email, workflow, doc, recipients):
	"""
	Enqueue email sending to background job to prevent request timeout
	This function is called from the server script
	"""
	frappe.enqueue(
		method=send_email,
		queue="short",
		is_async=True,
		timeout=300,
		workflow_email_name=workflow_email.name,
		workflow_state=workflow.get("workflow_state"),
		doctype=doc.doctype,
		docname=doc.name,
		recipients=recipients
	)
	frappe.logger().info(f"Enqueued workflow email for {doc.doctype} {doc.name} to {len(recipients)} recipients")


def send_email(workflow_email_name, workflow_state, doctype, docname, recipients):
	"""
	Send email to recipients with optional PDF attachment
	This function is called asynchronously from a background job
	Note: No @frappe.whitelist decorator - this is only called from background jobs
	"""
	# Get fresh document and workflow email data
	try:
		doc = frappe.get_doc(doctype, docname)
		workflow_email = frappe.get_doc("Workflow Email", workflow_email_name)
	except Exception as e:
		# frappe.log_error(
		# 	f"Error fetching document or workflow email:\n{str(e)}\n{frappe.get_traceback()}",
		# 	"Workflow Email Fetch Error"
		# )
		return

	subject = f"{doc.doctype} {doc.name} – {doc.workflow_state}"
	frappe.logger().info(
		f"=== Starting Email Send Process ===\n"
		f"Subject: {subject}\n"
		f"Recipients: {recipients}"
	)

	# Render message template with doc context
	try:
		if not workflow_email.message:
			frappe.throw("Email message template is empty")
			
		message = frappe.render_template(workflow_email.message, {"doc": doc})
		frappe.logger().debug(f"✓ Message rendered successfully. Length: {len(message)}")
	except Exception as e:
		# frappe.log_error(
		# 	f"Error rendering message template: {str(e)}\n{frappe.get_traceback()}", 
		# 	"Workflow Email Error"
		# )
		return

	attachments = []
	# Check if print format is attached
	if workflow_email.attach_print_format:
		frappe.logger().debug(f"Generating PDF with print format: {workflow_email.attach_print_format}")
		try:
			pdf = frappe.get_print(
				doc.doctype,
				doc.name,
				workflow_email.attach_print_format,
				as_pdf=True
			)
			attachments.append({
				"fname": f"{doc.name}.pdf",
				"fcontent": pdf
			})
			frappe.logger().debug(f"✓ PDF generated successfully")
		except Exception as e:
			# frappe.log_error(
			# 	f"Error generating PDF: {str(e)}\n{frappe.get_traceback()}", 
			# 	"Workflow Email PDF Error"
			# )
			frappe.logger().info(f"Error generating PDF: {str(e)}")

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			attachments=attachments,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=True
			# Email will be queued and sent by email queue worker
		)
		
		
		frappe.logger().info(f"✓✓✓ Email sent successfully to {len(recipients)} recipients!")
		# Also log success to Error Log for tracking
		# frappe.log_error(
		# 	f"Email sent successfully\n"
		# 	f"DocType: {doc.doctype}\n"
		# 	f"Document: {doc.name}\n"
		# 	f"Recipients: {recipients}\n"
		# 	f"Subject: {subject}",
		# 	"Workflow Email Success"
		# )
		
	except Exception as e:
		frappe.logger().info(f"Email sent failed  ")

		# frappe.log_error(
		# 	f"CRITICAL ERROR sending email:\n"
		# 	f"Error: {str(e)}\n"
		# 	f"Recipients: {recipients}\n"
		# 	f"Subject: {subject}\n\n"
		# 	f"Full Traceback:\n{frappe.get_traceback()}", 
		# 	"Workflow Email Send Error"
		# )