"""
State Schema for the LangGraph Workflow

This file defines the structure of data that flows through the workflow.
Think of it like a form that gets filled out as the lead progresses through each step.

WHY DO WE NEED THIS?
====================
In Module 2, we passed data around in function calls - it worked but got messy.
Here, we define ONE structured "state" object that:

1. Holds all lead information in one place
2. Gets updated as we learn more (from Salesforce, Marketo, etc.)
3. Can be SAVED when we pause for human approval
4. Can be LOADED when the human responds (even days later!)

This is like having a lead record that automatically tracks everything
that happens during the qualification process.
"""

from typing import TypedDict, Literal, Annotated, Optional, Dict, Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import operator


def merge_research_results(current: dict, update: dict) -> dict:
    """
    When multiple research tasks run in parallel, this combines their results.
    
    Example: Salesforce lookup finishes first, then Marketo, then web search.
    This function merges all three into one research dictionary.
    """
    if current is None:
        current = {}
    if update is None:
        return current
    result = dict(current)
    result.update(update)
    return result


class LeadInfo(TypedDict, total=False):
    """
    Lead information from the webhook.
    This is what we receive when a new lead comes in.
    """
    id: str                 # Salesforce ID
    email: str              # Lead's email
    first_name: str
    last_name: str
    company_name: str
    website: str
    phone: str
    sfdc_type: Literal["Lead", "Contact"]
    sales_inquiry: str      # What they asked about
    revenue: str            # Company revenue range
    industry: str
    employees: str


class ResearchResults(TypedDict, total=False):
    """
    Results from researching the lead.
    
    We gather info from 3 sources AT THE SAME TIME (parallel):
    - Salesforce: qualification fields (industry, employees, etc.)
    - Marketo: engagement history (did they open emails? visit website?)
    - Web: company info from the internet
    """
    salesforce: dict
    marketo: dict
    web: dict
    inquiry_analysis: dict  # AI classification of their inquiry


class QualificationResult(TypedDict, total=False):
    """
    The qualification decision.
    
    - SQL: High value, route to sales rep
    - SSL: Lower value, self-serve
    - Unknown: Need more info
    - Disqualified: Not a fit (spam, prohibited use case)
    - Support: They need help, not sales
    """
    status: Literal["SQL", "SSL", "Unknown", "Disqualified", "Support"]
    reason: str
    estimated_spend: Optional[float]


class EmailDraft(TypedDict, total=False):
    """
    The email we're preparing to send.
    
    May go through multiple versions if:
    - AI review says it needs improvement
    - Human reviewer requests changes
    """
    subject: str
    body: str               # Plain text
    body_html: str          # HTML formatted
    full_email: str         # Complete with greeting/signature
    version: int            # How many times we've revised it
    feedback_history: list[str]  # What changes were requested
    skipped: bool           # True if we didn't send (spam/disqualified)


class HumanApproval(TypedDict, total=False):
    """
    Tracks the human review process.
    
    When we send an email to Slack for approval:
    1. We save WHERE we sent it (channel, thread)
    2. We wait for a response
    3. We capture WHAT they said
    4. The AI interprets their response and decides next steps
    """
    requested: bool
    slack_channel: str
    slack_thread_ts: str    # Identifies the specific thread
    human_message: str      # What they typed in Slack
    status: Literal["pending", "approved", "rejected", "changes_requested"]
    feedback: str           # Specific feedback extracted by AI
    reviewer: str           # Who responded
    ai_reasoning: str       # Why AI interpreted it that way


class WorkflowState(TypedDict, total=False):
    """
    The complete state of a lead's journey through the workflow.
    
    This gets passed to every step and updated along the way.
    When we pause for human approval, this entire state is saved.
    When the human responds, we load it back and continue.
    """
    # === LEAD INFO ===
    lead: LeadInfo
    timestamp: str
    
    # === RESEARCH (gathered in parallel) ===
    research: Annotated[dict, merge_research_results]
    research_complete: bool
    
    # === QUALIFICATION ===
    qualification: QualificationResult
    
    # === EMAIL ===
    email_draft: EmailDraft
    email_review_count: int
    email_approved_by_ai: bool
    
    # === HUMAN REVIEW ===
    human_approval: HumanApproval
    requires_human_approval: bool
    
    # === RESULTS ===
    email_sent: bool
    salesforce_updated: bool
    logged_to_sheets: bool
    
    # === TOOL RESPONSES (for logging what each tool returned) ===
    tool_responses: Annotated[dict, merge_research_results]  # Stores: sfdc_update, sfdc_task, gmail responses
    
    # === TRACKING ===
    errors: Annotated[list[str], operator.add]
    current_node: str
    workflow_status: Literal["running", "waiting_for_human", "completed", "failed"]


def create_initial_state(payload: dict) -> WorkflowState:
    """
    Create the starting state from a webhook payload.
    
    This is called when a new lead comes in - it sets up
    the initial state with the lead info and empty fields
    for everything else.
    """
    
    dt = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Chicago"))
    
    lead: LeadInfo = {
        "id": payload.get("id", ""),
        "email": payload.get("email", ""),
        "first_name": payload.get("first_name", ""),
        "last_name": payload.get("last_name", ""),
        "company_name": payload.get("company_name", ""),
        "website": payload.get("website", ""),
        "phone": payload.get("phone", ""),
        "sfdc_type": payload.get("sfdc_type", "Lead"),
        "sales_inquiry": payload.get("sales_inquiry", ""),
        "revenue": payload.get("revenue", ""),
        "industry": payload.get("industry", ""),
        "employees": payload.get("employees", ""),
    }
    
    return WorkflowState(
        # Lead info
        lead=lead,
        timestamp=dt.strftime('%Y-%m-%dT%H:%M:%S%z'),
        
        # Research (will be filled by parallel tasks)
        research={},
        research_complete=False,
        
        # Qualification (will be set after research)
        qualification={},
        
        # Email (may have multiple versions)
        email_draft={},
        email_review_count=0,
        email_approved_by_ai=False,
        
        # Human review
        human_approval={},
        requires_human_approval=False,
        
        # Results
        email_sent=False,
        salesforce_updated=False,
        logged_to_sheets=False,
        
        # Tool responses (for logging)
        tool_responses={},
        
        # Tracking
        errors=[],
        current_node="start",
        workflow_status="running",
    )
