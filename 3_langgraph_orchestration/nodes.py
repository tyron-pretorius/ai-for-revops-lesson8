"""
LangGraph Workflow Nodes

This file contains all the "nodes" (steps) in our workflow graph.
Each node is a simple Python function that:
1. Receives the current workflow state
2. Does some work (API call, AI analysis, etc.)
3. Returns updates to the state

WHY LANGGRAPH?
=============
LangGraph makes it easy to:
1. Run nodes in PARALLEL (e.g., research from 3 sources at once)
2. Create LOOPS (e.g., keep revising email until it's good enough)
3. PAUSE for human input and resume later (human-in-the-loop)
4. PERSIST state across long-running workflows

These are hard to do cleanly with plain Python or simple agents.
"""

import sys
import os
import json
from typing import Dict, Any

# Add module directory to path for local imports
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from state import WorkflowState
from tools import (
    # Research tools
    lookup_crm_data,
    lookup_marketo_lead,
    get_marketo_activity,
    research_company_web,
    analyze_inquiry,
    qualify_lead_ai,
    generate_email,
    review_email_quality,
    send_email,
    log_salesforce_task,
    update_salesforce_status,
    send_slack_approval_request,
    log_to_sheets,
    # Human intent interpretation
    interpret_human_intent,
)


# =============================================================================
# PARALLEL RESEARCH NODES
# =============================================================================
# These 3 nodes run AT THE SAME TIME - this is a key LangGraph feature!
# In plain Python, you'd need threading/asyncio. LangGraph handles it for you.


def research_salesforce_node(state: WorkflowState) -> Dict[str, Any]:
    """
    🔵 PARALLEL NODE 1: Look up lead in Salesforce
    
    Runs simultaneously with research_marketo_node and research_web_node.
    Gets qualification fields like industry, employees, etc.
    
    KEY PATTERN: This node ENRICHES the lead in state with any new data found.
    Downstream nodes (like qualify_lead_node) can then just read from state.lead.
    """
    print("\n  ☁️  [Parallel 1/3] Looking up Salesforce data...")
    
    lead = state.get("lead", {})
    record_id = lead.get("id", "")
    record_type = lead.get("sfdc_type", "Lead")
    
    if not record_id:
        result = {"success": False, "error": "No Salesforce ID provided"}
    else:
        result = lookup_crm_data(record_id, record_type)
    
    # Start with research results
    updates = {"research": {"salesforce": result}}
    
    if result.get("success"):
        data = result.get("data", {})
        print(f"       ✓ Found: {data.get('first_name')} {data.get('last_name')} ({data.get('industry')})")
        print(f"         - Company: {data.get('company')}")
        print(f"         - Industry: {data.get('industry')}")
        print(f"         - Employees: {data.get('employees')}")
        print(f"         - Revenue: {data.get('revenue')}")
        print(f"         - Website: {data.get('website')}")
        
        # ENRICH the lead with any new data from Salesforce
        # Only update fields that are empty in the current lead
        enriched_lead = dict(lead)  # Copy current lead
        
        # Map Salesforce fields to lead fields
        field_mappings = {
            "industry": "industry",
            "employees": "employees", 
            "website": "website",
            "phone": "phone",
            "revenue": "revenue",
            "company": "company_name",
        }
        
        for sfdc_field, lead_field in field_mappings.items():
            sfdc_value = data.get(sfdc_field)
            if sfdc_value and not enriched_lead.get(lead_field):
                enriched_lead[lead_field] = sfdc_value
                print(f"       ↳ Enriched {lead_field}: {sfdc_value}")
        
        updates["lead"] = enriched_lead
    else:
        print(f"       ✗ Error: {result.get('error')}")
    
    return updates


def research_marketo_node(state: WorkflowState) -> Dict[str, Any]:
    """
    🔵 PARALLEL NODE 2: Look up lead activity in Marketo
    
    Runs simultaneously with research_salesforce_node and research_web_node.
    Gets engagement history (emails opened, web visits, etc.)
    """
    print("\n  📊 [Parallel 2/3] Looking up Marketo activity...")
    
    lead = state.get("lead", {})
    email = lead.get("email", "")
    
    result = {"success": False, "activities": []}
    
    if email:
        # First look up the Marketo lead ID
        marketo_lookup = lookup_marketo_lead(email)
        
        if marketo_lookup.get("success"):
            marketo_id = marketo_lookup.get("marketo_lead_id")
            print(f"       ✓ Found Marketo ID: {marketo_id}")
            
            # Then get their activity
            activity_result = get_marketo_activity(str(marketo_id), days_back=7)
            if activity_result.get("success"):
                result = activity_result
                activity_count = activity_result.get('activity_count', 0)
                print(f"       ✓ Found {activity_count} activities")
                # Show the activities found
                activities = activity_result.get('activities', [])
                for activity in activities[:5]:  # Show up to 5 activities
                    activity_type = activity.get('activityTypeId', 'Unknown')
                    activity_date = activity.get('activityDate', '')[:10] if activity.get('activityDate') else ''
                    primary_attr = activity.get('primaryAttributeValue', '')
                    print(f"         - Type {activity_type}: {primary_attr} ({activity_date})")
                if activity_count > 5:
                    print(f"         ... and {activity_count - 5} more")
        else:
            print(f"       ✗ Lead not found in Marketo")
    else:
        print(f"       ✗ No email provided")
    
    # Return just this node's contribution - reducer will merge it
    return {"research": {"marketo": result}}


def research_web_node(state: WorkflowState) -> Dict[str, Any]:
    """
    🔵 PARALLEL NODE 3: Research company on the web
    
    Runs simultaneously with research_salesforce_node and research_marketo_node.
    Uses OpenAI's native web search to find current info about the company.
    """
    print("\n  🌐 [Parallel 3/3] Researching company on web...")
    
    lead = state.get("lead", {})
    company = lead.get("company_name", "")
    website = lead.get("website", "")
    
    if company:
        result = research_company_web(company, website)
        if result.get("success"):
            print(f"       ✓ Found web research for {company}")
            # Show the research summary (first 500 chars)
            research_text = result.get("research", "")
            if research_text:
                # Split into lines and show each point
                lines = research_text.split('\n')
                for line in lines[:10]:  # Show first 10 lines
                    if line.strip():
                        print(f"         {line.strip()}")
                if len(lines) > 10:
                    print(f"         ... ({len(lines) - 10} more lines)")
        else:
            print(f"       ✗ Web research failed: {result.get('error')}")
    else:
        result = {"success": False, "error": "No company name provided"}
        print(f"       ✗ No company name to research")
    
    # Return just this node's contribution - reducer will merge it
    return {"research": {"web": result}}


def analyze_inquiry_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Analyze the sales inquiry using AI.
    
    This runs AFTER the parallel research completes.
    Classifies the inquiry as sales/support/spam and extracts key info.
    """
    print("\n  🔬 Analyzing inquiry...")
    
    lead = state.get("lead", {})
    inquiry = lead.get("sales_inquiry", "")
    
    if inquiry:
        result = analyze_inquiry(inquiry)
        print(f"       Category: {result.get('category')}")
    else:
        result = {"category": "Empty"}
        print(f"       ✗ No inquiry text")
    
    # Add inquiry analysis to research - reducer will merge it
    return {"research": {"inquiry_analysis": result}, "research_complete": True}


# =============================================================================
# QUALIFICATION NODE
# =============================================================================

def qualify_lead_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Qualify the lead using all research data.
    
    Uses the SAME qualification logic as Module 2.
    Returns SQL, SSL, Unknown, or Disqualified.
    
    NOTE: The lead in state has already been ENRICHED by research_salesforce_node,
    so we can just read directly from state.lead - no complex fallback logic needed!
    """
    print("\n  🎯 Qualifying lead...")
    
    lead = state.get("lead", {})
    research = state.get("research", {})
    
    # Get inquiry analysis (uses "category" field from Module 2 prompt)
    inquiry_analysis = research.get("inquiry_analysis", {})
    category = inquiry_analysis.get("category", "Sales Inquiry")
    
    # Handle spam - update status and skip email (workflow ends after logging)
    if category == "Spam/Solicitation":
        print(f"       → Disqualified (Spam) - will update CRM and log only")
        return {
            "qualification": {"status": "Disqualified", "reason": "Spam/Solicitation"},
            "requires_human_approval": False
        }
    
    # Run AI qualification (SAME prompt as Module 2)
    # Lead is already enriched with Salesforce data, so we just read from it
    result = qualify_lead_ai(
        inquiry=lead.get("sales_inquiry", ""),
        email=lead.get("email", ""),
        revenue=lead.get("revenue", ""),
        industry=lead.get("industry", ""),
        employees=lead.get("employees", "")
    )
    
    status = result.get("status", "Unknown")
    reason = result.get('reason', '')
    print(f"       → {status}: {reason}")
    
    # SQL leads require human approval before sending email
    requires_approval = status == "SQL"
    
    return {
        "qualification": result,
        "requires_human_approval": requires_approval
    }


# =============================================================================
# EMAIL GENERATION AND REVIEW LOOP
# =============================================================================
# This demonstrates LOOPING in LangGraph:
# - Generate email → Review → If not good enough → Generate again
# - Maximum 3 iterations to prevent infinite loops


def generate_email_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Generate an email response using AI.
    
    Uses the SAME email generation prompt as Module 2.
    Can be called MULTIPLE TIMES for review loops.
    """
    lead = state.get("lead", {})
    qualification = state.get("qualification", {})
    research = state.get("research", {})
    current_draft = state.get("email_draft", {})
    
    # Track version number (for loop counting)
    version = current_draft.get("version", 0) + 1
    print(f"\n  ✉️  Generating email (v{version})...")
    
    # Get any previous feedback (from AI review or human)
    feedback_history = current_draft.get("feedback_history", [])
    previous_feedback = feedback_history[-1] if feedback_history else ""
    
    # Get inquiry type from analysis (uses "category" from Module 2 prompt)
    inquiry_analysis = research.get("inquiry_analysis", {})
    inquiry_type = inquiry_analysis.get("category", "Sales Inquiry")
    
    # Build context from research
    context_parts = []
    web_research = research.get("web", {})
    if web_research.get("success"):
        context_parts.append(f"Company info: {web_research.get('research', '')}")
    
    marketo = research.get("marketo", {})
    if marketo.get("activity_count", 0) > 0:
        context_parts.append(f"Recent engagement: {marketo.get('activity_count')} activities in last 7 days")
    
    # Generate the email (SAME prompt as Module 2)
    result = generate_email(
        first_name=lead.get("first_name", "there"),
        inquiry=lead.get("sales_inquiry", ""),
        qualification_status=qualification.get("status", "Unknown"),
        inquiry_type=inquiry_type,
        context="; ".join(context_parts),
        previous_feedback=previous_feedback
    )
    
    email_body = result.get("email_body", "")
    
    # Format for HTML (AI already generates greeting and sign-off in the body)
    body_html = email_body.replace('\n', '<br>')
    
    print(f"       ✓ Generated ({len(email_body)} chars)")
    
    return {
        "email_draft": {
            "subject": "Re: Your Telnyx Inquiry",
            "body": email_body,
            "body_html": body_html,
            "full_email": body_html,  # Same as body_html - AI generates complete email
            "version": version,
            "feedback_history": feedback_history
        }
    }


def review_email_node(state: WorkflowState) -> Dict[str, Any]:
    """
    🔄 AI REVIEW NODE - Creates a LOOP in the workflow!
    
    Reviews the email for quality. If it doesn't pass:
    - The workflow LOOPS back to generate_email_node
    - Feedback is passed to improve the next version
    - Maximum 3 attempts to prevent infinite loops
    
    This is a key LangGraph feature - conditional routing based on state.
    """
    lead = state.get("lead", {})
    qualification = state.get("qualification", {})
    email_draft = state.get("email_draft", {})
    
    version = email_draft.get("version", 1)
    print(f"\n  🔍 Reviewing email (v{version})...")
    
    result = review_email_quality(
        email_body=email_draft.get("body", ""),
        inquiry=lead.get("sales_inquiry", ""),
        qualification=qualification.get("status", "Unknown")
    )
    
    review_count = state.get("email_review_count", 0) + 1
    
    # Auto-approve after 3 attempts to prevent infinite loops
    approved = result.get("approved", False) or review_count >= 3
    score = result.get("score", 0)
    
    print(f"       Score: {score}/10 {'✓' if approved else '✗'}")
    
    if not approved:
        issues = result.get("issues", [])
        if issues:
            print(f"       Issues: {', '.join(issues[:2])}...")
        
        # Add feedback for the next iteration
        feedback_history = list(email_draft.get("feedback_history", []))
        suggestions = result.get("suggestions", [])
        if suggestions:
            feedback_history.append("; ".join(suggestions))
        
        return {
            "email_draft": {**email_draft, "feedback_history": feedback_history},
            "email_review_count": review_count,
            "email_approved_by_ai": False
        }
    
    print(f"       ✓ Approved for sending")
    return {
        "email_review_count": review_count,
        "email_approved_by_ai": True
    }


# =============================================================================
# HUMAN-IN-THE-LOOP NODES
# =============================================================================
# This is THE key LangGraph feature for enterprise workflows!
# The workflow PAUSES waiting for human input, then RESUMES.


def request_human_approval_node(state: WorkflowState) -> Dict[str, Any]:
    """
    👤 HUMAN-IN-THE-LOOP: Request approval via Slack
    
    This node:
    1. Sends the email draft to Slack for human review
    2. PAUSES the workflow (sets status to "waiting_for_human")
    3. Returns - the workflow will resume when human responds
    
    The human can:
    - @bot approve → Send the email
    - @bot reject [reason] → Discard
    - @bot changes [feedback] → Loop back to regenerate email
    """
    print("\n  👤 Requesting human approval via Slack...")
    
    lead = state.get("lead", {})
    qualification = state.get("qualification", {})
    email_draft = state.get("email_draft", {})
    
    result = send_slack_approval_request(
        lead_email=lead.get("email", ""),
        qualification=qualification.get("status", "Unknown"),
        email_subject=email_draft.get("subject", ""),
        email_body=email_draft.get("body", ""),
        context=qualification.get("reason", "")
    )
    
    if result.get("success"):
        print(f"       ✓ Approval request sent to Slack")
        print(f"       ⏸️  Workflow PAUSED - waiting for human response")
        return {
            "human_approval": {
                "requested": True,
                "slack_channel": result.get("channel"),
                "slack_thread_ts": result.get("thread_ts"),
                "status": "pending"
            },
            "workflow_status": "waiting_for_human"
        }
    else:
        # If Slack fails, skip human approval
        print(f"       ✗ Slack failed: {result.get('error')}")
        print(f"       → Proceeding without human approval")
        return {
            "human_approval": {"requested": False, "status": "skipped"},
            "requires_human_approval": False
        }


def process_human_response_node(state: WorkflowState) -> Dict[str, Any]:
    """
    🤖 MASTER AGENT: Interpret and act on human's response.
    
    This is where the AI interprets what the human wants and decides:
    - approved → Send the email
    - rejected → Don't send, mark as handled
    - changes_requested → Loop back to regenerate with feedback
    
    The slack_listener just forwards the raw message here.
    The AGENT makes the decision.
    """
    print("\n  🤖 Master Agent: Processing human response...")
    
    human_approval = state.get("human_approval", {})
    human_message = human_approval.get("human_message", "")
    reviewer = human_approval.get("reviewer", "Unknown")
    email_draft = state.get("email_draft", {})
    
    print(f"       Reviewer: {reviewer}")
    print(f"       Message: \"{human_message[:60]}...\"" if len(human_message) > 60 else f"       Message: \"{human_message}\"")
    
    # If no message, check if status was pre-set (for skipped approval flow)
    if not human_message:
        status = human_approval.get("status", "approved")
        print(f"       → No message, using status: {status}")
        return {"human_approval": {**human_approval, "status": status}}
    
    # Use AI to interpret what the human wants (defined in tools.py)
    interpretation = interpret_human_intent(
        human_message=human_message,
        email_body=email_draft.get("body", ""),
        lead_email=state.get("lead", {}).get("email", "")
    )
    
    decision = interpretation.get("decision", "changes_requested")
    feedback = interpretation.get("feedback", "")
    reasoning = interpretation.get("reasoning", "")
    
    print(f"       → Decision: {decision}")
    if reasoning:
        print(f"       → Reasoning: {reasoning[:50]}...")
    
    # Update approval status based on AI interpretation
    updated_approval = {
        **human_approval,
        "status": decision,
        "feedback": feedback,
        "ai_reasoning": reasoning
    }
    
    # If changes requested, add feedback to email draft for next iteration
    if decision == "changes_requested" and feedback:
        feedback_history = list(email_draft.get("feedback_history", []))
        feedback_history.append(f"Human: {feedback}")
        
        return {
            "email_draft": {**email_draft, "feedback_history": feedback_history},
            "human_approval": updated_approval
        }
    
    return {"human_approval": updated_approval}


# =============================================================================
# FINAL ACTION NODES
# =============================================================================

def send_email_node(state: WorkflowState) -> Dict[str, Any]:
    """Send the approved email via Gmail."""
    print("\n  📤 Sending email...")
    
    lead = state.get("lead", {})
    email_draft = state.get("email_draft", {})
    new_tool_responses = {}
    
    # Send email via Gmail
    gmail_result = send_email(
        to_email=lead.get("email", ""),
        subject=email_draft.get("subject", "Re: Your Telnyx Inquiry"),
        body_html=email_draft.get("full_email", "")
    )
    new_tool_responses["gmail"] = gmail_result
    
    if gmail_result.get("success"):
        print(f"       ✓ Email sent successfully")
        
        # Also log as Salesforce task
        lead_id = lead.get("id")
        if lead_id:
            sfdc_task_result = log_salesforce_task(
                person_id=lead_id,
                subject=email_draft.get("subject", ""),
                body=email_draft.get("body", "")
            )
            new_tool_responses["sfdc_task"] = sfdc_task_result
            if sfdc_task_result.get("success"):
                print(f"       ✓ Salesforce task logged")
    else:
        print(f"       ✗ Failed: {gmail_result.get('error')}")
    
    return {
        "email_sent": gmail_result.get("success", False),
        "tool_responses": new_tool_responses,  # Reducer will merge with existing
    }


def update_crm_node(state: WorkflowState) -> Dict[str, Any]:
    """Update the lead's status in Salesforce."""
    print("\n  ☁️  Updating Salesforce...")
    
    lead = state.get("lead", {})
    qualification = state.get("qualification", {})
    
    result = update_salesforce_status(
        record_id=lead.get("id", ""),
        record_type=lead.get("sfdc_type", "Lead"),
        status=qualification.get("status", "Unknown")
    )
    
    if result.get("success"):
        print(f"       ✓ Status updated to: {qualification.get('status')}")
    else:
        print(f"       ✗ Failed: {result.get('error')}")
    
    return {
        "salesforce_updated": result.get("success", False),
        "tool_responses": {"sfdc_update": result},  # Reducer will merge with existing
    }


def log_results_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Log all results to Google Sheets.
    
    This uses the extract_business_summary helper to pull only the 
    business-relevant fields from the LangGraph state. This keeps
    Google Sheets clean and useful for RevOps analysis.
    """
    print("\n  📊 Logging to Google Sheets...")
    
    # Pass the full state - log_to_sheets will extract the business summary
    result = log_to_sheets(state)
    
    if result.get("success"):
        print(f"       ✓ Logged to Google Sheets")
    else:
        print(f"       ✗ Failed: {result.get('error')}")
    
    return {"logged_to_sheets": result.get("success", False)}


def finalize_node(state: WorkflowState) -> Dict[str, Any]:
    """Final node - print summary and mark workflow complete."""
    lead = state.get("lead", {})
    qualification = state.get("qualification", {})
    email_draft = state.get("email_draft", {})
    
    print(f"\n{'='*60}")
    print(f"✅ WORKFLOW COMPLETE")
    print(f"{'='*60}")
    print(f"   Lead: {lead.get('email')}")
    print(f"   Qualification: {qualification.get('status')}")
    print(f"   Email versions: {email_draft.get('version', 0)}")
    print(f"   Email sent: {state.get('email_sent', False)}")
    print(f"   CRM updated: {state.get('salesforce_updated', False)}")
    print(f"{'='*60}")
    
    return {"workflow_status": "completed"}


def skip_email_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Skip sending email - workflow continues to CRM update and logging.
    
    This is used when:
    - Lead is spam/disqualified (no point emailing)
    - Human rejected the email (don't want to send)
    
    The workflow still continues to update Salesforce and log to sheets.
    """
    qualification = state.get("qualification", {})
    human_approval = state.get("human_approval", {})
    
    reason = "spam/disqualified" if qualification.get("status") == "Disqualified" else "human rejected"
    print(f"\n  🚫 Skipping email ({reason})...")
    
    return {
        "email_sent": False,
        "email_draft": {"body": "", "skipped": True, "version": 0}
    }
