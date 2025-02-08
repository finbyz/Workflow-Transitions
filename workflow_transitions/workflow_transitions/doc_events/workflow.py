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

        # Create second server script with fixed structure
        if frappe.db.exists("Server Script", f"Before Validate for {self.document_type}"):
            frappe.delete_doc("Server Script", f"Before Validate for {self.document_type}")
        
        before_validate_server_script = frappe.new_doc("Server Script")
        before_validate_server_script.name = f"Before Validate for {self.document_type}"
        before_validate_server_script.script_type = "DocType Event"
        before_validate_server_script.reference_doctype = self.document_type
        before_validate_server_script.doctype_event = "Before Validate"
        before_validate_server_script.script = """
def workflow_state(doc):
    user_doc = frappe.get_doc("User", frappe.session.user)
    user_roles = [role.role for role in user_doc.roles]
    role = user_roles[0] if user_roles else "No Role"
    user_name = frappe.db.get_value("User", frappe.session.user, "full_name")

    # Filter out duplicate workflow state entries instead of clearing all
    doc.state_change = [row for row in doc.state_change if row.workflow_state != doc.workflow_state]

    # Append the new workflow state entry
    doc.append('state_change', {
        'username': user_name,
        'modification_time': frappe.utils.now(),
        "workflow_state": doc.workflow_state,
        "role": role
    })

# Ensure that state change is tracked only if the workflow state has changed
previous_state = frappe.db.get_value(doc.doctype, doc.name, "workflow_state")
if previous_state != doc.workflow_state:
    workflow_state(doc)

"""
        
        before_validate_server_script.save()
        if frappe.db.exists("Server Script", f"Before insert for {self.document_type}"):
            frappe.delete_doc("Server Script", f"Before insert for {self.document_type}")
        
        before_insert_server_script = frappe.new_doc("Server Script")
        before_insert_server_script.name = f"Before insert for {self.document_type}"
        before_insert_server_script.script_type = "DocType Event"
        before_insert_server_script.reference_doctype = self.document_type
        before_insert_server_script.doctype_event = "Before Insert"
        before_insert_server_script.script = """self.workflow_changes = []"""
        before_insert_server_script.save()

        meta = frappe.get_meta(self.document_type)
        last_field = meta.fields[-1].fieldname if meta.fields else None

        field_definitions = [
            {"fieldname": "workflow_progress", "label": "Progress", "fieldtype": "Tab Break", "insert_after": last_field},
            {"fieldname": "custom_html", "label": "HTML", "fieldtype": "HTML", "insert_after": "workflow_progress"},
            {"fieldname": "state_change", "label": "State Change", "fieldtype": "Table", "options": "State Change Items", "insert_after": "custom_html"}
        ]

        existing_fieldnames = [df.fieldname for df in meta.get("fields")]

        for field in field_definitions:
            if field["fieldname"] not in existing_fieldnames:
                custom_field = frappe.new_doc("Custom Field")
                custom_field.dt = self.document_type  
                custom_field.fieldname = field["fieldname"]
                custom_field.label = field["label"]
                custom_field.fieldtype = field["fieldtype"]
                if "options" in field:
                    custom_field.options = field["options"]
                custom_field.insert_after = field["insert_after"]
                custom_field.insert()
                frappe.msgprint(f"Created {field['fieldname']} field.")

        frappe.db.commit()

        client_script_name = f"{self.document_type}-State Change"
        
        if frappe.db.exists("Client Script", client_script_name):
            frappe.delete_doc("Client Script", client_script_name)

        client_script = frappe.new_doc("Client Script")
        client_script.dt = self.document_type
        client_script.script_type = "Client"
        client_script.enabled = 1
        client_script.name = client_script_name
        client_script.script = generate_client_script(self.document_type)
        client_script.insert()
        frappe.db.commit()

def generate_client_script(document_type):
    return f"frappe.ui.form.on('{document_type}', " +"""{
        onload: function(frm) {
        injectWorkflowCSS();  // Apply styles

        if (frm.doc.doctype && frm.doc.name) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: frm.doc.doctype,
                    name: frm.doc.name
                },
                callback: function(doc_response) {
                    if (doc_response.message) {
                        let doc = doc_response.message;
                        
                        frappe.call({
                            method: "workflow_transitions.workflow_transitions.doc_events.workflow.get_workflow_transitions",
                            args: {
                                doc: frm.doc.doctype
                            },
                            callback: function(transition_response) {
                                if (transition_response.message) {
                                    let transitions = transition_response.message;
                                    
                                    transitions = filterTransitionsByConditions(transitions, doc);
                                    let html = generateWorkflowHtml(transitions, frm.doc.state_change || []);
                                    frm.fields_dict['custom_html'].wrapper.innerHTML = html;
                                    initializeJsPlumb(transitions);
                                }
                            }
                        });
                    }
                }
            });
        }
    }
});

function convertPythonCondition(condition) {
    if (!condition) return '';
    
    return condition
        .replace(/\band\b/g, '&&')
        .replace(/\bor\b/g, '||')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false')
        .replace(/\bNone\b/g, 'null')
        .replace(/\bnot\b/g, '!')
        .replace(/(\w+)\s*==\s*"([^"]*)"/, '$1 === "$2"')
        .replace(/(\w+)\s*==\s*(\d+)/, '$1 === $2');
}

function filterTransitionsByConditions(transitions, doc) {
    return transitions.filter(transition => {
        if (!transition.condition) {
            return true;
        }
        
        try {
            let jsCondition = convertPythonCondition(transition.condition);
            
            let context = {
                doc: doc,
                frappe: frappe,
                int: parseInt,
                str: String,
                float: parseFloat
            };
            
            try {
                let fn = new Function('doc', 'frappe', 'int', 'str', 'float', 
                    `try { return ${jsCondition}; } catch (e) { console.error(e); return false; }`);
                return fn(doc, frappe, parseInt, String, parseFloat);
            } catch (e) {
                console.error('Error in condition execution:', e);
                return false;
            }
        } catch (e) {
            console.error('Error in condition conversion:', e);
            return false;
        }
    });
}

function initializeJsPlumb(transitions) {
    jsPlumb.ready(function() {
        jsPlumb.reset();
        
        let instance = jsPlumb.getInstance({
            Container: "workflow-container",
            ConnectionsDetachable: false,
            Connector: ["Flowchart", { cornerRadius: 5, stub: [30, 30], gap: 10 }],
            Endpoint: ["Dot", { radius: 5 }],
            EndpointStyle: { fill: "#456" },
            PaintStyle: { 
                stroke: "#456",
                strokeWidth: 2 
            },
            HoverPaintStyle: { stroke: "#789" },
            ConnectionOverlays: [
                ["Arrow", {
                    location: 1,
                    width: 10,
                    length: 10
                }],
                ["Label", {
                    label: function(conn) {
                        let transition = transitions.find(t => 
                            t.state.replace(/\s+/g, '-').toLowerCase() === conn.sourceId &&
                            t.next_state.replace(/\s+/g, '-').toLowerCase() === conn.targetId
                        );
                        let label = transition ? transition.action : '';
                        if (transition && transition.condition) {
                            label += ' ⚙️';
                        }
                        return label;
                    },
                    cssClass: "connection-label"
                }]
            ]
        });
        
        instance.draggable($(".workflow-state"), {
            containment: true,
            grid: [10, 10]
        });
        
        transitions.forEach(t => {
            let sourceId = t.state.replace(/\s+/g, '-').toLowerCase();
            let targetId = t.next_state.replace(/\s+/g, '-').toLowerCase();
            
            instance.connect({
                source: sourceId,
                target: targetId,
                anchor: ["Right", "Left"],
                parameters: {
                    action: t.action,
                    condition: t.condition
                }
            });
        });
    });
}

function getStateIndicator(state, items = [], currentState = '', transitions = []) {
    if (!Array.isArray(items)) items = [];
    if (!Array.isArray(transitions)) transitions = [];

    // Sort items by modification time to get state history
    const sortedItems = [...items].sort((a, b) => {
        return new Date(a.modification_time) - new Date(b.modification_time);
    });

    // Get the latest state from sorted items
    const latestState = sortedItems.length > 0 
        ? sortedItems[sortedItems.length - 1].workflow_state
        : '';

    // Check if this state exists in history
    const stateExists = sortedItems.some(item => 
        item.workflow_state &&
        item.workflow_state.trim().toLowerCase() === state.trim().toLowerCase()
    );

    // If state exists in history, show checkmark or cross
    if (stateExists) {
        const negativeStates = ['cancel', 'reject', 'declined', 'rejected', 'cancelled'];
        const isNegativeState = negativeStates.some(negState => 
            state.toLowerCase().includes(negState.toLowerCase())
        );
        
        return isNegativeState 
            ? '<span class="state-indicator negative">✗</span>' 
            : '<span class="state-indicator positive">✓</span>';
    }

    // Check if this is a possible next state from the latest state
    const isNextPossibleState = transitions.some(transition => 
        transition.state &&
        transition.state.toLowerCase() === latestState.toLowerCase() &&
        transition.next_state.toLowerCase() === state.toLowerCase()
    );

    // Show question mark only for next possible states that haven't been reached yet
    if (isNextPossibleState && !stateExists) {
        return '<span class="state-indicator next">?</span>';
    }

    return '';
}

function generateWorkflowHtml(transitions, items = []) {
    let allStates = new Set();
    transitions.forEach(t => {
        allStates.add(t.state);
        allStates.add(t.next_state);
    });

    let html = `<div id="workflow-container">
                    <div class="workflow-states">`;

    Array.from(allStates).forEach(state => {
        let stateId = state.replace(/\s+/g, '-').toLowerCase();
        let stateIndicator = getStateIndicator(state, items, "", transitions); 
        
        html += `<div class="workflow-state" id="${stateId}">
                    <div class="state-text">${state}${stateIndicator}</div>
                </div>`;
    });

    html += `   </div>
              </div>`;

    return html;
}

function injectWorkflowCSS() {
    let css = `
        #workflow-container {
            position: relative;
            width: 100%;
            padding: 20px;
            border-radius: 8px;
        }

        .workflow-states {
            display: flex;
            flex-wrap: wrap;
            gap: 30px;
            justify-content: center;
            align-items: center;
        }

        .workflow-state {
            min-width: 180px;
            min-height: 60px;
            padding: 12px;
            background: white;
            border: 2px solid #d1d5db;
            border-radius: 6px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            text-align: center;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }

        .state-indicator {
            display: inline-block;
            margin-left: 5px;
            font-weight: bold;
            font-size: 24px;
        }

        .state-indicator.positive {
            color: #22c55e;
        }

        .state-indicator.negative {
            color: #ef4444;
        }
        .state-indicator.next {
            color: #FFEA00;
        }

        .current-state {
            border-color: #3b82f6;
            background-color: #eff6ff;
            box-shadow: 0 0 0 2px #3b82f6;
            transform: scale(1.05);
        }

        .state-text {
            position: relative;
            z-index: 1;
        }
    `;

    $('.workflow-custom-style').remove();
    $('<style class="workflow-custom-style">').text(css).appendTo('head');
}
    """


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

@frappe.whitelist()
def get_workflow_transitions(doc):
    transitions = frappe.db.sql(f"""
        SELECT w.name AS workflow_name, wds.state, wds.next_state, wds.allowed, wds.condition
        FROM `tabWorkflow` AS w
        JOIN `tabWorkflow Transition` AS wds ON w.name = wds.parent
        WHERE w.document_type = '{doc}' AND w.is_active = 1
        ORDER BY wds.idx
    """, as_dict=True)
    
    return transitions