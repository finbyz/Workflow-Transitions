frappe.ui.form.on('State Change', {
    onload: function(frm) {
        injectWorkflowCSS();

        if (frm.doc.doctype_name && frm.doc.document_name) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: frm.doc.doctype_name,
                    name: frm.doc.document_name
                },
                callback: function(doc_response) {
                    if (doc_response.message) {
                        let doc = doc_response.message;
                        
                        frappe.call({
                            method: "workflow_transitions.workflow_transitions.doc_events.workflow.get_workflow_transitions",
                            args: {
                                doc: frm.doc.doctype_name
                            },
                            callback: function(transition_response) {
                                if (transition_response.message) {
                                    let transitions = transition_response.message;
                                    
                                    transitions = filterTransitionsByConditions(transitions, doc);
                                    let html = generateWorkflowHtml(transitions, frm.doc.items || []);
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
    let stateRoles = new Map(); // Map to store roles for each state
    
    transitions.forEach(t => {
        allStates.add(t.state);
        allStates.add(t.next_state);
        
        // Store roles for states
        if (t.allowed && t.state) {
            stateRoles.set(t.state, t.allowed);
        }
        if (t.allowed && t.next_state) {
            stateRoles.set(t.next_state, t.allowed);
        }
    });

    let html = `<div id="workflow-container">
                    <div class="workflow-states">`;

    Array.from(allStates).forEach(state => {
        let stateId = state.replace(/\s+/g, '-').toLowerCase();
        let stateIndicator = getStateIndicator(state, items, "", transitions);
        let role = stateRoles.get(state) || 'Any';
        
        html += `<div class="workflow-state" id="${stateId}">
                    <div class="state-content">
                        <div class="state-text">${state}${stateIndicator}</div>
                        <div class="state-role">${role}</div>
                    </div>
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
            min-height: 80px;
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

        .state-content {
            display: flex;
            flex-direction: column;
            gap: 8px;
            align-items: center;
        }

        .state-role {
            font-size: 0.8em;
            color: #6b7280;
            font-weight: normal;
            font-style: italic;
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

        .connection-label {
            background-color: white;
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 0.8em;
        }
    `;

    $('.workflow-custom-style').remove();
    $('<style class="workflow-custom-style">').text(css).appendTo('head');
}