"""
Tools for the LangGraph workflow.

This module provides all the external integrations and AI sub-agents used by the workflow.
It demonstrates how LangGraph nodes can use shared functions across your codebase.

Tools are organized by category:
- Salesforce (CRM)
- Marketo (Marketing Automation)  
- Web Search (using OpenAI's native web search)
- AI Analysis (sub-agents for specific tasks)
- Email (Gmail)
- Slack (Human-in-the-loop)
- Google Sheets (Logging)
"""

import os
import sys
import json
from typing import Dict, Any, Optional
from datetime import datetime

from dotenv import load_dotenv

# Add project root to path so we can import shared functions
PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import prompts from centralized location
from prompts import (
    WEB_RESEARCH_PROMPT,
    INQUIRY_TYPE_PROMPT,
    QUALIFICATION_PROMPT,
    EMAIL_GENERATION_PROMPT,
    EMAIL_REVIEW_PROMPT,
    HUMAN_INTENT_PROMPT,
)

# Import shared functions - these are the same functions used in Module 2
from functions import (
    salesforce_functions,
    marketo_functions,
    gmail_functions,
    googlesheets_functions,
    gpt_functions,
)

load_dotenv()

# Slack config
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APPROVAL_CHANNEL = "wins"

# Google Sheets config
SHEET_ID = '1Yay6Bf7KEjOxWmKp_aMa_Cmn-R42hYq2ykoLd1O5_Io'
SHEET_NAME = 'LangGraph'


# =============================================================================
# SALESFORCE TOOLS
# Reuses functions from the shared functions package
# =============================================================================

def lookup_crm_data(record_id: str, record_type: str) -> Dict[str, Any]:
    """
    Look up a Lead or Contact from Salesforce with qualification fields.
    
    For Contacts, we also pull in Account fields (company name, industry, etc.)
    using Salesforce's relationship query syntax (Account.FieldName).
    """
    if not record_id:
        return {"success": False, "error": "No record ID provided"}
    
    # Fields needed for qualification
    if record_type == "Lead":
        # Leads have company info directly on the record
        fields = ["Id", "Email", "FirstName", "LastName", "Company", 
                  "Industry_Cb__c", "Employees_Cb__c", "Website", "Phone"]
    else:
        # Contacts: pull company info from the related Account
        fields = ["Id", "Email", "FirstName", "LastName", "Phone",
                  "Industry_Cb__c", "Employees_Cb__c",
                  # Account fields (related object)
                  "Account.Name", "Account.Website", 
                  "Account.Company_Estimated_Annual_Revenue_Cb__c"]
    
    result = salesforce_functions.lookup_person_fields(record_type, record_id, fields)
    
    if result.get("success"):
        data = result.get("data", {})
        
        # For Contacts, extract Account fields from nested object
        account = data.get("Account", {}) or {}
        
        return {
            "success": True,
            "data": {
                "id": data.get("Id"),
                "email": data.get("Email"),
                "first_name": data.get("FirstName"),
                "last_name": data.get("LastName"),
                "phone": data.get("Phone"),
                # Contact-level fields (may be empty)
                "industry": data.get("Industry_Cb__c"),
                "employees": data.get("Employees_Cb__c"),
                # For Contacts: Company info from Account
                "company": data.get("Company") or account.get("Name"),
                "website": data.get("Website") or account.get("Website"),
                "revenue": account.get("Company_Estimated_Annual_Revenue_Cb__c"),
            }
        }
    return result


def update_salesforce_status(record_id: str, record_type: str, status: str) -> Dict[str, Any]:
    """Update the lead/contact status in Salesforce."""
    if record_type == "Lead":
        return salesforce_functions.update_lead_fields(record_id, {"Status": status})
    return salesforce_functions.update_contact_fields(record_id, {"Lead_Status__c": status})


def log_salesforce_task(person_id: str, subject: str, body: str) -> Dict[str, Any]:
    """Log an activity/task in Salesforce."""
    return salesforce_functions.log_sfdc_task(person_id, subject, body, direction="Outbound")


# =============================================================================
# MARKETO TOOLS
# Uses the real Marketo API via shared functions
# =============================================================================

def lookup_marketo_lead(email: str) -> Dict[str, Any]:
    """
    Look up a lead in Marketo by email.
    
    This is needed to get the Marketo lead ID before we can fetch activities.
    """
    try:
        token = marketo_functions.checkTokenLife()
        result = marketo_functions.lookupLead(
            token, 
            filterType="email", 
            filterValues=email,
            fields="id,email,firstName,lastName,createdAt"
        )
        
        if result.get("success") and result.get("result"):
            lead = result["result"][0]
            return {
                "success": True,
                "marketo_lead_id": lead.get("id"),
                "data": lead
            }
        return {"success": False, "error": "Lead not found in Marketo"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_marketo_activity(marketo_lead_id: str, days_back: int = 7) -> Dict[str, Any]:
    """
    Get recent activities for a Marketo lead.
    
    Activities help us understand engagement level:
    - Email opens
    - Web visits  
    - Form fills
    """
    if not marketo_lead_id:
        return {"success": False, "error": "Marketo lead ID required"}
    
    try:
        result = marketo_functions.getActivitiesforLead(marketo_lead_id, days_in_past=days_back)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# WEB SEARCH TOOL
# Uses OpenAI's native web search via the Responses API
# =============================================================================

def research_company_web(company_name: str, website: str = "") -> Dict[str, Any]:
    """
    Research a company on the internet using OpenAI's native web search.
    
    This is a KEY ADVANTAGE of using the Responses API - it can search the web
    in real-time to find current information about the company.
    """
    prompt = WEB_RESEARCH_PROMPT.format(
        company_name=company_name,
        website=website or 'unknown'
    )

    try:
        response = gpt_functions.create_response(
            prompt=prompt,
            tools=[{"type": "web_search_preview"}]
        )
        
        # Extract the text response - try multiple approaches
        research_text = ""
        
        # Method 1: Check output_text directly (simplest)
        if hasattr(response, 'output_text') and response.output_text:
            research_text = response.output_text
        
        # Method 2: Iterate through output items
        elif response and hasattr(response, 'output') and response.output:
            for item in response.output:
                # Check for message type items with content
                if hasattr(item, "content") and item.content:
                    for content_block in item.content:
                        if hasattr(content_block, "text"):
                            research_text += content_block.text
                # Check for direct text attribute
                elif hasattr(item, "text"):
                    research_text += item.text
        
        if not research_text:
            # Log the response structure for debugging
            print(f"       ⚠️ Web search response structure: {type(response)}")
            if hasattr(response, '__dict__'):
                print(f"       ⚠️ Response attrs: {list(response.__dict__.keys())}")
            return {"success": False, "error": "No research results returned - check response structure"}
        
        return {
            "success": True,
            "company": company_name,
            "research": research_text,
            "source": "web_search"
        }
    except Exception as e:
        import traceback
        print(f"       ⚠️ Web search error: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


# =============================================================================
# AI ANALYSIS TOOLS (Sub-agents)
# Prompts are imported from prompts.py for centralized management
# =============================================================================

def analyze_inquiry(inquiry: str) -> Dict[str, Any]:
    """
    Classify a sales inquiry into categories.
    Uses the SAME prompt as Module 2.
    """
    if not inquiry or not inquiry.strip():
        return {"category": "Empty"}
    
    prompt = INQUIRY_TYPE_PROMPT.format(inquiry=inquiry)
    
    return gpt_functions.create_response(
        prompt=prompt,
        input_text="Classify this inquiry and return JSON."
    )


def qualify_lead_ai(
    inquiry: str,
    email: str,
    revenue: str = "",
    industry: str = "",
    employees: str = ""
) -> Dict[str, Any]:
    """
    Qualify a lead using the SAME prompt as Module 2.
    """
    prompt = QUALIFICATION_PROMPT.format(
        inquiry=inquiry,
        email=email,
        revenue=revenue or "Unknown",
        industry=industry or "Unknown",
        employees=employees or "Unknown"
    )
    
    return gpt_functions.create_response(
        prompt=prompt,
        input_text="Qualify this lead and return JSON."
    )


# =============================================================================
# EMAIL TOOLS
# =============================================================================

def generate_email(
    first_name: str,
    inquiry: str,
    qualification_status: str,
    inquiry_type: str = "Sales Inquiry",
    context: str = "",
    previous_feedback: str = ""
) -> Dict[str, Any]:
    """
    Generate an email using the SAME prompt as Module 2.
    """
    previous_feedback_section = ""
    if previous_feedback:
        previous_feedback_section = f"\n- Address this feedback from human review: {previous_feedback}"
    
    prompt = EMAIL_GENERATION_PROMPT.format(
        first_name=first_name,
        inquiry=inquiry,
        qualification_status=qualification_status,
        inquiry_type=inquiry_type,
        context=context or "None",
        previous_feedback_section=previous_feedback_section
    )
    
    return gpt_functions.create_response(
        prompt=prompt,
        input_text="Generate the email response and return JSON."
    )


def review_email_quality(email_body: str, inquiry: str, qualification: str) -> Dict[str, Any]:
    """
    AI review of email quality before sending.
    
    This creates a LOOP in the workflow - if quality is low, 
    we regenerate the email. This is a key LangGraph feature!
    """
    prompt = EMAIL_REVIEW_PROMPT.format(
        inquiry=inquiry,
        qualification=qualification,
        email_body=email_body
    )

    result = gpt_functions.create_response(
        prompt=prompt,
        input_text="Review the email and return JSON with score and feedback."
    )
    
    # Auto-approve if score >= 7
    if result.get("score", 0) >= 7:
        result["approved"] = True
    return result


def interpret_human_intent(human_message: str, email_body: str, lead_email: str) -> Dict[str, Any]:
    """
    AI sub-agent that interprets what the human reviewer wants.
    
    Used in the human-in-the-loop approval flow to understand
    whether the reviewer approved, rejected, or wants changes.
    
    Args:
        human_message: The raw message from Slack
        email_body: The current email draft
        lead_email: The lead's email address (for context)
        
    Returns:
        decision: "approved" | "rejected" | "changes_requested"
        feedback: Any specific changes requested
        reasoning: Brief explanation of interpretation
    """
    prompt = HUMAN_INTENT_PROMPT.format(
        lead_email=lead_email,
        email_preview=email_body,
        human_message=human_message
    )

    try:
        return gpt_functions.create_response(
            prompt=prompt,
            input_text="Interpret the human's intent and return JSON."
        )
    except Exception as e:
        print(f"       ⚠️ AI interpretation failed: {e}")
        # Fallback: treat as changes_requested
        return {
            "decision": "changes_requested",
            "feedback": human_message,
            "reasoning": "Fallback due to AI error"
        }


def send_email(to_email: str, subject: str, body_html: str) -> Dict[str, Any]:
    """Send email via Gmail API using shared functions."""
    # Convert newlines to HTML breaks
    body_html = body_html.replace("\n", "<br>\n")
    
    result = gmail_functions.send_email(
        to=to_email,
        cc="",
        subject=subject,
        message_text=body_html,
        is_html=True
    )
    return {
        "success": "id" in result,
        "message_id": result.get("id"),
        "response": result
    }


# =============================================================================
# SLACK TOOLS (Human-in-the-loop)
# This is the KEY LANGGRAPH FEATURE - pausing workflow for human input
# =============================================================================

def send_slack_approval_request(
    lead_email: str,
    qualification: str,
    email_subject: str,
    email_body: str,
    context: str = ""
) -> Dict[str, Any]:
    """
    Send an approval request to Slack and wait for human response.
    
    This is where LangGraph shines:
    - The workflow PAUSES here waiting for human input
    - The state is preserved while waiting
    - When human responds, workflow RESUMES from where it left off
    
    Commands the human can use in the thread:
    - @bot approve - Send the email
    - @bot reject [reason] - Discard the email
    - @bot changes [feedback] - Request changes (loops back to email generation!)
    """
    import requests
    
    if not SLACK_BOT_TOKEN:
        return {"success": False, "error": "SLACK_BOT_TOKEN not configured"}
    
    # Show full email in Slack (no truncation)
    email_preview = email_body
    
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔔 Email Approval Required", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Lead:*\n{lead_email}"},
                {"type": "mrkdwn", "text": f"*Qualification:*\n{qualification}"}
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Subject:*\n{email_subject}"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Email Draft:*\n```{email_preview}```"}
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "💬 *Reply in this thread* to approve, reject, or suggest changes"}
            ]
        }
    ]
    
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'channel': SLACK_APPROVAL_CHANNEL,
            'text': f"Email approval required for {lead_email}",
            'blocks': blocks
        },
        timeout=30
    )
    
    data = response.json()
    return {
        "success": data.get("ok", False),
        "channel": data.get("channel"),
        "thread_ts": data.get("ts"),
        "error": data.get("error")
    }


# =============================================================================
# GOOGLE SHEETS LOGGING
# =============================================================================

# These are the columns for the business audit log in Google Sheets
# Each row represents one lead that went through the workflow
SHEET_HEADERS = [
    # Basic info
    "timestamp",
    "id",
    "email",
    "sfdc_type",
    "first_name",
    "last_name",
    "company_name",
    "website",
    "phone",
    "revenue",
    "industry",
    "employees",
    # Inquiry & qualification
    "sales_inquiry",
    "inquiry_type",
    "status",
    "status_detail",
    # Email
    "email_body",
    "email_versions",
    "human_approved",
    # Research results
    "marketo_activity",
    "web_search",
    # Tool responses
    "sfdc_update_response",
    "sfdc_task_response",
    "gmail_response",
    # Errors
    "error",
]


def extract_business_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract all relevant fields from the workflow state for logging.
    
    This is the bridge between LangGraph's internal state and your 
    business reporting in Google Sheets.
    
    Args:
        state: The full LangGraph WorkflowState
        
    Returns:
        A flat dictionary matching SHEET_HEADERS
    """
    import json
    
    # The lead has already been ENRICHED by research_salesforce_node,
    # so we just read directly from state.lead - no fallbacks needed!
    lead = state.get("lead", {})
    qualification = state.get("qualification", {})
    email_draft = state.get("email_draft", {})
    human_approval = state.get("human_approval", {})
    research = state.get("research", {})
    
    # Get Marketo activity - convert to string for sheets
    marketo_data = research.get("marketo", {})
    marketo_activity = ""
    if marketo_data.get("success") and marketo_data.get("activities"):
        activities = marketo_data.get("activities", [])
        marketo_activity = json.dumps(activities) if activities else ""
    
    # Get web search results - convert to string for sheets
    web_data = research.get("web", {})
    web_search = ""
    if web_data.get("success"):
        # The web search returns "research" field with the text content
        web_search = web_data.get("research", "")
    
    # Get tool responses
    tool_responses = state.get("tool_responses", {})
    
    return {
        # Basic info - lead is already enriched, just read directly
        "id": lead.get("id"),
        "email": lead.get("email"),
        "sfdc_type": lead.get("sfdc_type"),
        "first_name": lead.get("first_name"),
        "last_name": lead.get("last_name"),
        "company_name": lead.get("company_name"),
        "website": lead.get("website"),
        "phone": lead.get("phone"),
        "revenue": lead.get("revenue"),
        "industry": lead.get("industry"),
        "employees": lead.get("employees"),
        # Inquiry & qualification
        "sales_inquiry": lead.get("sales_inquiry"),
        "inquiry_type": research.get("inquiry_analysis", {}).get("category"),
        "status": qualification.get("status"),
        "status_detail": qualification.get("reason"),
        # Email
        "email_body": email_draft.get("body", ""),
        "email_versions": email_draft.get("version"),
        "human_approved": human_approval.get("status") == "approved",
        # Research results
        "marketo_activity": marketo_activity,
        "web_search": web_search,
        # Tool responses
        "sfdc_update_response": json.dumps(tool_responses.get("sfdc_update")) if tool_responses.get("sfdc_update") else "",
        "sfdc_task_response": json.dumps(tool_responses.get("sfdc_task")) if tool_responses.get("sfdc_task") else "",
        "gmail_response": json.dumps(tool_responses.get("gmail")) if tool_responses.get("gmail") else "",
        # Errors
        "error": ", ".join(state.get("errors", [])) if state.get("errors") else "",
    }


def log_to_sheets(state_or_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Log workflow results to Google Sheets.
    
    Can accept either:
    - The full WorkflowState (will extract business summary automatically)
    - A pre-extracted data dictionary
    """
    try:
        # Check if this looks like a full state or already-extracted data
        if "lead" in state_or_data or "qualification" in state_or_data:
            # It's a full state - extract the business summary
            data = extract_business_summary(state_or_data)
        else:
            # It's already extracted data
            data = state_or_data
        
        # Add timestamp
        data['timestamp'] = datetime.now().isoformat()
        
        # Use the shared writeRow2Sheet function
        googlesheets_functions.writeRow2Sheet(
            dict=data,
            sheet_name=SHEET_NAME,
            spreadsheet_id=SHEET_ID,
            headers=SHEET_HEADERS
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

