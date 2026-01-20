"""
LangGraph Workflow Definition

This file defines the GRAPH structure of our workflow using LangGraph.

WHY LANGGRAPH? This graph demonstrates three key capabilities:
============================================================

1. PARALLEL EXECUTION
   - Salesforce lookup, Marketo lookup, and Web search run SIMULTANEOUSLY
   - In plain Python, you'd need threading/asyncio. LangGraph handles it automatically.

2. CONDITIONAL LOOPS
   - Email review creates a loop: generate → review → (if bad) → generate again
   - Human feedback also loops: generate → human review → (if changes) → generate again
   - Clean and declarative - no while loops or state management needed.

3. HUMAN-IN-THE-LOOP
   - Workflow PAUSES at the approval step
   - State is PRESERVED while waiting (can be hours or days!)
   - When human responds, workflow RESUMES exactly where it left off

WORKFLOW DIAGRAM:
=================

                                START
                                  │
           ┌──────────────────────┼──────────────────────┐
           │                      │                      │
           ▼                      ▼                      ▼
    ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
    │ Salesforce  │      │   Marketo   │      │ Web Search  │
    │   Lookup    │      │   Lookup    │      │  (OpenAI)   │
    └──────┬──────┘      └──────┬──────┘      └──────┬──────┘
           │                    │                    │
           └──────────────────┬─┴────────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ Analyze Inquiry │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  Qualify Lead   │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
        [Disqualified]                    [Other]
              │                               │
              ▼                               ▼
    ┌─────────────────┐              ┌─────────────────┐
    │   Skip Email    │              │ Generate Email  │◄────────┐
    └────────┬────────┘              └────────┬────────┘         │
             │                                │                   │
             │                                ▼                   │
             │                       ┌─────────────────┐         │
             │                       │  Review Email   │         │
             │                       └────────┬────────┘         │
             │                                │                   │
             │                   ┌────────────┴────────────┐     │
             │                   │                         │     │
             │             [Not Approved]            [Approved]  │
             │                   │                         │     │
             │                   └─────────────────────────┼─────┘
             │                                             │
             │                              ┌──────────────┴──────────────┐
             │                              │                             │
             │                       [SQL - needs approval]         [Other]
             │                              │                             │
             │                              ▼                             │
             │                    ┌─────────────────┐                     │
             │                    │ Request Slack   │                     │
             │                    │    Approval     │                     │
             │                    └────────┬────────┘                     │
             │                             │                              │
             │                       [⏸️ PAUSE]                           │
             │                             │                              │
             │                    ┌────────┴────────┐                     │
             │                    │ Process Human   │                     │
             │                    │   Response      │                     │
             │                    └────────┬────────┘                     │
             │                             │                              │
             │              ┌──────────────┼──────────────┐               │
             │              │              │              │               │
             │         [Approved]    [Changes]     [Rejected]            │
             │              │              │              │               │
             │              │              └──────────────┼───────────────┘
             │              │                             │        (loops to Generate)
             │              └──────────────┬──────────────┘
             │                             │
             │                             ▼
             │                    ┌─────────────────┐
             │                    │   Send Email    │
             │                    └────────┬────────┘
             │                             │
             └──────────────┬──────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   Update CRM    │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Log to Sheets  │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │    Finalize     │
                   └────────┬────────┘
                            │
                            ▼
                           END
"""

import sys
import os
from typing import Literal

# Add module directory to path for local imports
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from state import WorkflowState
from nodes import (
    # Parallel research
    research_salesforce_node,
    research_marketo_node,
    research_web_node,
    analyze_inquiry_node,
    # Qualification
    qualify_lead_node,
    # Email with review loop
    generate_email_node,
    review_email_node,
    # Human-in-the-loop
    request_human_approval_node,
    process_human_response_node,
    # Final actions
    send_email_node,
    update_crm_node,
    log_results_node,
    finalize_node,
    skip_email_node,
)


# =============================================================================
# ROUTING FUNCTIONS
# These functions decide where to go next based on the current state
# =============================================================================

def route_after_qualification(state: WorkflowState) -> Literal["skip_email", "generate_email"]:
    """
    Route based on qualification result.
    
    Only Spam/Solicitation (Disqualified) skips email - they just get logged.
    Support requests flow through to email generation (inquiry_type ensures right email).
    """
    status = state.get("qualification", {}).get("status", "Unknown")
    
    if status == "Disqualified":
        return "skip_email"
    return "generate_email"


def route_after_email_review(state: WorkflowState) -> Literal["generate_email", "check_approval"]:
    """
    Route after AI email review.
    
    If email not approved, LOOP back to generate a new version.
    This creates an iterative improvement loop!
    """
    approved = state.get("email_approved_by_ai", False)
    
    if not approved:
        return "generate_email"  # LOOP!
    return "check_approval"


def route_check_approval(state: WorkflowState) -> Literal["request_approval", "send_email"]:
    """
    Check if human approval is needed.
    
    SQL (high-value) leads require human review before sending.
    """
    requires_approval = state.get("requires_human_approval", False)
    
    if requires_approval:
        return "request_approval"
    return "send_email"


def route_after_human_response(state: WorkflowState) -> Literal["generate_email", "send_email", "skip_email"]:
    """
    Route based on human response from Slack.
    
    - approved → send the email
    - changes_requested → LOOP back to regenerate with feedback
    - rejected → skip email, mark as handled
    """
    status = state.get("human_approval", {}).get("status", "pending")
    
    if status == "approved":
        return "send_email"
    elif status == "changes_requested":
        return "generate_email"  # LOOP back with feedback!
    elif status == "rejected":
        return "skip_email"
    
    # Default to send if status unclear
    return "send_email"


# =============================================================================
# BUILD THE GRAPH
# =============================================================================

def build_workflow_graph() -> StateGraph:
    """
    Build the LangGraph workflow.
    
    This function assembles all nodes and edges into a compiled graph
    that can be executed.
    """
    
    # Create the graph builder with our state schema
    builder = StateGraph(WorkflowState)
    
    # =========================================================================
    # ADD NODES
    # Each node is a function that takes state and returns state updates
    # =========================================================================
    
    # Parallel research nodes (these will run simultaneously!)
    builder.add_node("research_salesforce", research_salesforce_node)
    builder.add_node("research_marketo", research_marketo_node)
    builder.add_node("research_web", research_web_node)
    builder.add_node("analyze_inquiry", analyze_inquiry_node)
    
    # Qualification
    builder.add_node("qualify_lead", qualify_lead_node)
    
    # Email generation and review (with loop capability)
    builder.add_node("generate_email", generate_email_node)
    builder.add_node("review_email", review_email_node)
    
    # Human-in-the-loop
    builder.add_node("request_approval", request_human_approval_node)
    builder.add_node("process_human_response", process_human_response_node)
    
    # Check node (pass-through for conditional routing)
    builder.add_node("check_approval", lambda state: state)
    
    # Final actions
    builder.add_node("send_email", send_email_node)
    builder.add_node("update_crm", update_crm_node)
    builder.add_node("log_results", log_results_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("skip_email", skip_email_node)
    
    # =========================================================================
    # ADD EDGES - Define the flow between nodes
    # =========================================================================
    
    # PARALLEL FAN-OUT: START triggers 3 research nodes simultaneously
    builder.add_edge(START, "research_salesforce")
    builder.add_edge(START, "research_marketo")
    builder.add_edge(START, "research_web")
    
    # PARALLEL FAN-IN: All 3 research nodes merge into analyze_inquiry
    builder.add_edge("research_salesforce", "analyze_inquiry")
    builder.add_edge("research_marketo", "analyze_inquiry")
    builder.add_edge("research_web", "analyze_inquiry")
    
    # After analysis → qualification
    builder.add_edge("analyze_inquiry", "qualify_lead")
    
    # CONDITIONAL: Route based on qualification
    builder.add_conditional_edges(
        "qualify_lead",
        route_after_qualification,
        {
            "skip_email": "skip_email",
            "generate_email": "generate_email"
        }
    )
    
    # Disqualified leads → straight to CRM update
    builder.add_edge("skip_email", "update_crm")
    
    # Email → Review
    builder.add_edge("generate_email", "review_email")
    
    # CONDITIONAL with LOOP: Review can loop back to generate
    builder.add_conditional_edges(
        "review_email",
        route_after_email_review,
        {
            "generate_email": "generate_email",  # LOOP!
            "check_approval": "check_approval"
        }
    )
    
    # CONDITIONAL: Check if human approval needed
    builder.add_conditional_edges(
        "check_approval",
        route_check_approval,
        {
            "request_approval": "request_approval",
            "send_email": "send_email"
        }
    )
    
    # Human approval flow
    builder.add_edge("request_approval", "process_human_response")
    
    # CONDITIONAL with LOOP: Human can request changes (loops back!)
    builder.add_conditional_edges(
        "process_human_response",
        route_after_human_response,
        {
            "generate_email": "generate_email",  # LOOP for changes!
            "send_email": "send_email",
            "skip_email": "skip_email"
        }
    )
    
    # Final sequence
    builder.add_edge("send_email", "update_crm")
    builder.add_edge("update_crm", "log_results")
    builder.add_edge("log_results", "finalize")
    builder.add_edge("finalize", END)
    
    # Compile and return the graph
    # interrupt_after pauses AFTER request_approval runs, waiting for human input
    # When resumed, execution continues from process_human_response
    # SqliteSaver persists checkpoints to a file that can be shared between processes
    # This is essential for human-in-the-loop where main.py and slack_listener.py are separate
    db_path = os.path.join(MODULE_DIR, ".workflow_checkpoints.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_after=["request_approval"]
    )


# Create the compiled graph (singleton)
lead_workflow_graph = build_workflow_graph()


def get_graph_mermaid() -> str:
    """Get Mermaid diagram of the workflow for visualization."""
    try:
        return lead_workflow_graph.get_graph().draw_mermaid()
    except Exception:
        # Fallback manual diagram
        return """
graph TD
    START --> research_salesforce & research_marketo & research_web
    research_salesforce & research_marketo & research_web --> analyze_inquiry
    analyze_inquiry --> qualify_lead
    qualify_lead -->|Disqualified/Spam| skip_email
    qualify_lead -->|Other| generate_email
    generate_email --> review_email
    review_email -->|Not Approved| generate_email
    review_email -->|Approved| check_approval
    check_approval -->|SQL| request_approval
    check_approval -->|Other| send_email
    request_approval --> process_human_response
    process_human_response -->|Approved| send_email
    process_human_response -->|Changes| generate_email
    process_human_response -->|Rejected| skip_email
    skip_email --> update_crm
    send_email --> update_crm
    update_crm --> log_results
    log_results --> finalize
    finalize --> END
"""


if __name__ == "__main__":
    print("=" * 60)
    print("LangGraph Workflow Visualization")
    print("=" * 60)
    print(get_graph_mermaid())
