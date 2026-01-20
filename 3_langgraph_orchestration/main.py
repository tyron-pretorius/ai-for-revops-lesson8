"""
Module 3: LangGraph Workflow with Human-in-the-Loop

This Flask server demonstrates LangGraph's key advantages over simple agent loops:

1. PARALLEL EXECUTION
   - Salesforce, Marketo, and Web research run simultaneously
   - Faster than sequential calls!

2. CONDITIONAL LOOPS
   - Email review creates an improvement loop
   - Human feedback loops back to regenerate

3. HUMAN-IN-THE-LOOP
   - SQL leads pause for Slack approval
   - Workflow resumes when human responds
   - State persists across the pause!

ENDPOINTS:
- POST /contact-sales   - Start the workflow (may pause for approval)
- POST /human-response  - Resume workflow with human's response from Slack
- GET  /health         - Health check
- GET  /graph          - View workflow diagram

TO RUN:
1. Start this server: python main.py
2. In another terminal, start slack_listener.py for human approval
3. Send a test payload to /contact-sales
"""

import json
import uuid
import traceback
from flask import Flask, request, make_response

import sys
import os

# Add module directory to path for local imports
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from state import create_initial_state
from graph import lead_workflow_graph, get_graph_mermaid
from slack_listener import register_pending_workflow, get_pending_workflow, remove_pending_workflow

app = Flask(__name__)


@app.route('/contact-sales', methods=['POST'])
def contact_sales():
    """
    Handle incoming contact sales notifications.
    
    The workflow will:
    1. Run parallel research (Salesforce + Marketo + Web)
    2. Analyze the inquiry
    3. Qualify the lead
    4. Generate email with AI review loop
    5. For SQL leads: Pause for human approval
    6. Send email and update CRM
    
    Returns 202 if waiting for approval, 200 if completed.
    """
    payload = request.json
    email = payload.get("email", "unknown")
    
    print(f"\n{'='*60}")
    print(f"📥 CONTACT SALES RECEIVED")
    print(f"   Email: {email}")
    print(f"   Company: {payload.get('company_name', 'Unknown')}")
    print(f"{'='*60}")
    
    try:
        # Create initial state from payload
        initial_state = create_initial_state(payload)
        
        print(f"\n🚀 Starting LangGraph workflow...")
        print(f"   ⚡ Parallel research (Salesforce + Marketo + Web)")
        print(f"   🔄 Email review loop")
        print(f"   👤 Human-in-the-loop for SQL leads")
        
        # Generate a unique thread_id for this workflow run
        # This is used by the checkpointer to track state across interrupts
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        
        # Execute the graph
        # For SQL leads, this will PAUSE at request_human_approval (interrupt)
        final_state = lead_workflow_graph.invoke(initial_state, config=config)
        
        workflow_status = final_state.get("workflow_status", "unknown")
        
        # If waiting for human, register and return 202
        if workflow_status == "waiting_for_human":
            human_approval = final_state.get("human_approval", {})
            channel = human_approval.get("slack_channel")
            thread_ts = human_approval.get("slack_thread_ts")
            
            # Register workflow for the Slack listener
            # Include thread_id so we can resume from the same checkpoint
            if channel and thread_ts:
                register_pending_workflow(channel, thread_ts, final_state, thread_id)
            
            return make_response(
                json.dumps({
                    "status": "waiting_for_approval",
                    "message": "Workflow paused - waiting for human approval in Slack",
                    "email": email,
                    "qualification": final_state.get("qualification", {}),
                    "email_draft_version": final_state.get("email_draft", {}).get("version", 0),
                    "slack_thread": f"{channel}/{thread_ts}" if channel else None
                }, indent=2),
                202,  # 202 Accepted - processing but not complete
                {"Content-Type": "application/json"}
            )
        
        # Workflow completed without needing approval
        return make_response(
            json.dumps({
                "status": "completed",
                "email": email,
                "qualification": final_state.get("qualification", {}),
                "email_sent": final_state.get("email_sent", False),
                "salesforce_updated": final_state.get("salesforce_updated", False),
                "email_versions": final_state.get("email_draft", {}).get("version", 0)
            }, indent=2),
            200,
            {"Content-Type": "application/json"}
        )
        
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"\n❌ ERROR:")
        print(traceback_str)
        
        return make_response(
            json.dumps({
                "status": "error",
                "email": email,
                "error": str(e)
            }),
            500,
            {"Content-Type": "application/json"}
        )


@app.route('/human-response', methods=['POST'])
def human_response():
    """
    Resume workflow with human's response from Slack.
    
    This endpoint is called by slack_listener.py when a human responds
    in a Slack thread. The workflow resumes from where it paused.
    
    Expected payload:
    {
        "channel": "C02MVAN0KDM",
        "thread_ts": "1768760878.712199",
        "human_message": "looks good, send it",
        "reviewer": "U01MB9ZKQQ1"
    }
    """
    payload = request.json
    channel = payload.get("channel")
    thread_ts = payload.get("thread_ts")
    human_message = payload.get("human_message", "")
    reviewer = payload.get("reviewer", "Unknown")
    
    print(f"\n{'='*60}")
    print(f"👤 HUMAN RESPONSE RECEIVED")
    print(f"   Channel: {channel}")
    print(f"   Thread: {thread_ts}")
    print(f"   Reviewer: {reviewer}")
    print(f"   Message: {human_message[:50]}{'...' if len(human_message) > 50 else ''}")
    print(f"{'='*60}")
    
    # Load the pending workflow
    pending = get_pending_workflow(channel, thread_ts)
    
    if not pending:
        return make_response(
            json.dumps({
                "status": "error",
                "error": "No pending workflow found for this thread"
            }),
            404,
            {"Content-Type": "application/json"}
        )
    
    workflow_state = pending.get("state", {})
    thread_id = pending.get("thread_id")
    
    print(f"\n🔄 Resuming workflow (thread_id: {thread_id})")
    
    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        # Update the checkpoint state with the human's message
        lead_workflow_graph.update_state(
            config,
            {
                "human_approval": {
                    **workflow_state.get("human_approval", {}),
                    "human_message": human_message,
                    "reviewer": reviewer,
                    "status": "pending"  # Will be determined by process_human_response
                },
                "workflow_status": "running"
            }
        )
        
        # Resume from interrupt - pass None as input to continue from checkpoint
        final_state = lead_workflow_graph.invoke(None, config=config)
        
        workflow_status = final_state.get("workflow_status", "unknown")
        print(f"   Workflow status: {workflow_status}")
        
        # If still waiting for human (changes requested, new draft generated)
        if workflow_status == "waiting_for_human":
            human_approval = final_state.get("human_approval", {})
            new_channel = human_approval.get("slack_channel")
            new_thread_ts = human_approval.get("slack_thread_ts")
            
            # Re-register with updated state
            if new_channel and new_thread_ts:
                register_pending_workflow(new_channel, new_thread_ts, final_state, thread_id)
            
            return make_response(
                json.dumps({
                    "status": "waiting_for_approval",
                    "message": "Email regenerated - waiting for approval",
                    "email_draft_version": final_state.get("email_draft", {}).get("version", 0),
                    "email_body": final_state.get("email_draft", {}).get("body", "")
                }),
                202,
                {"Content-Type": "application/json"}
            )
        
        # Workflow completed
        remove_pending_workflow(channel, thread_ts)
        
        return make_response(
            json.dumps({
                "status": "completed",
                "email_sent": final_state.get("email_sent", False),
                "human_decision": final_state.get("human_approval", {}).get("status", "unknown"),
                "salesforce_updated": final_state.get("salesforce_updated", False)
            }),
            200,
            {"Content-Type": "application/json"}
        )
        
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"\n❌ ERROR resuming workflow:")
        print(traceback_str)
        
        return make_response(
            json.dumps({
                "status": "error",
                "error": str(e)
            }),
            500,
            {"Content-Type": "application/json"}
        )


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return make_response(
        json.dumps({
            "status": "healthy",
            "service": "module-3-langgraph",
            "features": ["parallel_execution", "loops", "human_in_the_loop"]
        }),
        200,
        {"Content-Type": "application/json"}
    )


@app.route('/graph', methods=['GET'])
def graph():
    """
    View the workflow graph structure.
    
    Returns a Mermaid diagram you can paste into:
    https://mermaid.live/
    """
    return make_response(
        json.dumps({
            "name": "Lead Qualification Workflow",
            "description": "Contact sales workflow with parallel research, loops, and human approval",
            "features": {
                "parallel_execution": [
                    "research_salesforce",
                    "research_marketo", 
                    "research_web"
                ],
                "loops": [
                    "email review (regenerate if quality low)",
                    "human feedback (regenerate if changes requested)"
                ],
                "human_in_the_loop": "Slack approval for SQL leads"
            },
            "mermaid_diagram": get_graph_mermaid()
        }, indent=2),
        200,
        {"Content-Type": "application/json"}
    )


def print_startup_banner():
    """Print helpful startup information."""
    print("\n" + "=" * 60)
    print("🚀 MODULE 3: LANGGRAPH WORKFLOW SERVER")
    print("=" * 60)
    print("\nLangGraph Advantages Demonstrated:")
    print("  ⚡ Parallel Execution - 3 research tasks at once")
    print("  🔄 Conditional Loops  - Email review & human feedback")
    print("  👤 Human-in-the-Loop  - Slack approval with state persistence")
    print("\nEndpoints:")
    print("  POST /contact-sales   - Start workflow")
    print("  POST /human-response  - Resume workflow with human feedback")
    print("  GET  /health         - Health check")
    print("  GET  /graph          - View workflow diagram")
    print("\n⚠️  IMPORTANT: Also run slack_listener.py in another terminal")
    print("   for human-in-the-loop approval to work!")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    print_startup_banner()
    app.run(debug=True, host='0.0.0.0', port=5053)
