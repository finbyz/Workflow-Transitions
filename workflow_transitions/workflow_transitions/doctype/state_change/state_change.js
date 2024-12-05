frappe.ui.form.on('State Change', {
    onload: function(frm) {
        // Function to dynamically generate status indicators based on workflow progression
        function generateStatusIndicators(items, workflowStates, options = {}) {
            // Default options with ability to customize
            const defaultOptions = {
                completedMarker: '✓',
                currentMarker: '?',
                rejectedMarker: '✗',
                emptyMarker: '',
                rejectedKeywords: ['reject', 'canceled', 'declined']
            };
            
            // Merge provided options with defaults
            const config = { ...defaultOptions, ...options };
            
            // Create a map of states to their progression order
            const stateOrder = workflowStates.map(state => 
                typeof state === 'object' ? state.state : state
            );
            
            // Dynamic status generation function
            const generateRowStatus = (row, rowIndex) => {
                // If no workflow states or first item without state, special handling
                if (!row?.workflow_state || 
                    (rowIndex === 0 && !row.workflow_state)) {
                    return stateOrder.map((state, stateIndex) => {
                        if (stateIndex === 0) return config.completedMarker;
                        if (stateIndex === 1) return config.currentMarker;
                        return config.emptyMarker;
                    });
                }
                
                // Find the current state's index
                const currentStateIndex = stateOrder.findIndex(state => 
                    state.toLowerCase() === row.workflow_state.toLowerCase()
                );
                
                // Check if the current state is rejected
                const isRejected = config.rejectedKeywords.some(keyword => 
                    row.workflow_state.toLowerCase().includes(keyword)
                );
                
                // Generate status indicators
                return stateOrder.map((state, stateIndex) => {
                    // Completed states before current
                    if (stateIndex < currentStateIndex) return config.completedMarker;
                    
                    // Rejected state handling
                    if (isRejected) {
                        return stateIndex === currentStateIndex 
                            ? config.rejectedMarker 
                            : config.emptyMarker;
                    }
                    
                    // Current state
                    if (stateIndex === currentStateIndex) return config.currentMarker;
                    
                    // Future states
                    return config.emptyMarker;
                });
            };
            
            // Generate status for all items
            return items.map(generateRowStatus);
        }

        // Fetch workflow details dynamically
        function fetchWorkflowDetails() {
            return new Promise((resolve, reject) => {
                frappe.call({
                    method: 'workflow_transitions.workflow_transitions.doc_events.workflow.get_workflow_fields',
                    args: {
                        doc: frm.doc.doctype_name
                    }
                }).then(r => {
                    console.log("r",r)
                    if (r.message && r.message.length > 0) {
                        const workflowStates = r.message.map(workflow => ({
                            state: workflow.state || "",
                            roles: workflow.allow_edit ? [workflow.allow_edit] : [],
                            // Add other mappings as needed
                        }));
                        
                        resolve(workflowStates);
                    } else {
                        reject(new Error('No active workflow found for this document type'));
                    }
                }).catch(err => {
                    console.error("Workflow Fetch Error:", err);
                    reject(err);
                });
            });
        }
        // Determine current workflow state
        function getCurrentState(frm) {
            // Try to get the current state from different possible sources
            if (frm.doc.workflow_state) return frm.doc.workflow_state;
            if (frm.doc.items && frm.doc.items.length > 0) {
                return frm.doc.items[frm.doc.items.length - 1].workflow_state || 'Draft';
            }
            return 'Draft';
        }

function createWorkflowVisualization(workflowStates, currentState) {
    // Extract unique roles, ensuring the order is maintained
    const uniqueRoles = [...new Map(
        workflowStates.map(state => [state.roles[0], state.roles[0]])
    ).values()];

    // Generate status indicators for the current workflow
    const statusIndicators = generateStatusIndicators(frm.doc.items, workflowStates, {
        currentMarker: '?',
        completedMarker: '✓',
        rejectedMarker: '✗'
    });

    // Map indicators to unique roles
    const levelBoxes = uniqueRoles.map((role, index) => {
        // Find the first workflow state corresponding to this role
        const roleStateIndex = workflowStates.findIndex(state => state.roles.includes(role));
        const marker = roleStateIndex !== -1 ? statusIndicators[0][roleStateIndex] : '';

        return `
            <div class="level-box" style="
                position: relative;
                padding: 10px;
                border: 2px solid blue;
                border-radius: 5px;
                margin: 0 10px;
                flex: 1;
                min-width: 100px;
                text-align: center;
            ">
                <div style="
                    position: absolute;
                    top: 5px;
                    right: 5px;
                    font-weight: bold;
                    font-size: 24px;
                    color: ${marker === '✓' ? 'green' : 
                             (marker === '?' ? 'orange' : 
                             (marker === '✗' ? 'red' : 'blue'))}
                ">
                    ${marker}
                </div>
                <label style="display: block; margin-top: 20px;">
                    <strong>${role}</strong><br>
                    Level ${index + 1}
                </label>
            </div>
        `;
    }).join('');

    // Create full HTML content
    return `
        <div style="
            text-align: center;
            margin-bottom: 15px;
        ">
            <div style="
                display: flex;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 10px;
            ">
                ${levelBoxes}
            </div>
        </div>
    `;
}


        // Main function to update custom HTML
        function updateCustomHtml() {
            // Get current state
            const currentState = getCurrentState(frm);

            // Fetch workflow details and create visualization
            fetchWorkflowDetails().then(workflowStates => {
                // Generate HTML
                const htmlContent = createWorkflowVisualization(workflowStates, currentState);

                // Update the custom HTML field
                frm.set_df_property("custom_html", "options", htmlContent);
            }).catch(err => {
                frappe.msgprint(__('Error processing workflow: {0}', [err]));
            });
        }

        // Call the function to update HTML on form load
        updateCustomHtml();

        // Optional: Refresh HTML when workflow state changes
        frm.add_custom_button(__('Refresh Workflow'), function() {
            updateCustomHtml();
        });
    }
});