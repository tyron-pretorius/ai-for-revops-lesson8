"""
Tool definitions for the Agentic AI workflow.

These tools are available for the AI agent to call autonomously.
The agent decides which tools to use based on the situation.
"""

from typing import Dict, Any
from datetime import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path so "functions" can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from functions import (
    gmail_functions,
    googlesheets_functions,
    salesforce_functions
)

load_dotenv()

# Google Sheets config
SHEET_ID = '1Yay6Bf7KEjOxWmKp_aMa_Cmn-R42hYq2ykoLd1O5_Io'
SHEET_NAME = 'Agentic'
SHEET_HEADERS = [
    "timestamp", "id", "email", "sfdc_type", "first_name", "last_name",
    "company_name", "website", "phone", "revenue", "industry",
    "employees","sales_inquiry", "inquiry_type", "status", "status_detail",
    "email_body", "sfdc_update_response","sfdc_task_response", "gmail_response", "error"
]


# =============================================================================
# Tool Definitions (for OpenAI function calling)
# =============================================================================

TOOLS = [
    
    {
        "type": "function",
        "name": "analyze_inquiry",
        "description": "Use a specialized sub-agent to classify inquiry type (Sales, Spam/Solicitation, Support, Empty)",
        "parameters": {
            "type": "object",
            "properties": {
                "inquiry_text": {
                    "type": "string",
                    "description": "The sales inquiry text to analyze"
                }
            },
            "required": ["inquiry_text"]
        }
    },
    {
        "type": "function",
        "name": "qualify_lead",
        "description": "Use the qualification sub-agent (LLM) to classify SQL/SSL/Unknown/Disqualified",
        "parameters": {
            "type": "object",
            "properties": {
                "inquiry_text": {
                    "type": "string",
                    "description": "The sales inquiry text"
                },
                "email": {
                    "type": "string",
                    "description": "Lead email address"
                },
                "revenue": {
                    "type": "string",
                    "description": "Revenue range"
                },
                "industry": {
                    "type": "string",
                    "description": "Industry"
                },
                "employees": {
                    "type": "string",
                    "description": "Employee count"
                }
            },
            "required": ["inquiry_text", "email"]
        }
    },
    {
        "type": "function",
        "name": "draft_email_response",
        "description": "Generate a personalized email response (sub-agent tool)",
        "parameters": {
            "type": "object",
            "properties": {
                "first_name": {
                    "type": "string",
                    "description": "Lead's first name"
                },
                "inquiry_text": {
                    "type": "string",
                    "description": "The original inquiry"
                },
                "qualification_status": {
                    "type": "string",
                    "enum": ["SQL", "SSL", "Unknown", "Disqualified", "Support"],
                    "description": "The lead's qualification status"
                },
                "inquiry_type": {
                    "type": "string",
                    "enum": ["sales", "support", "spam"],
                    "description": "Type of inquiry"
                },
                "additional_context": {
                    "type": "string",
                    "description": "Any additional context to personalize the email"
                }
            },
            "required": ["first_name", "inquiry_text", "qualification_status", "inquiry_type"]
        }
    },
    {
        "type": "function",
        "name": "send_email",
        "description": "Send the drafted email to the lead via Gmail",
        "parameters": {
            "type": "object",
            "properties": {
                "to_email": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body (HTML supported)"
                }
            },
            "required": ["to_email", "subject", "body"]
        }
    },
    {
        "type": "function",
        "name": "lookup_person_in_salesforce",
        "description": (
            "Look up a Lead or Contact by ID and return specific fields. "
            "Use Salesforce API field names. Non-standard fields: "
            "Employees_Cb__c (employees) and Industry_Cb__c (industry)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {
                    "type": "string",
                    "description": "The Salesforce Lead or Contact ID"
                },
                "record_type": {
                    "type": "string",
                    "enum": ["Lead", "Contact"],
                    "description": "Whether this is a Lead or Contact record"
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Salesforce API field names to return"
                }
            },
            "required": ["record_id", "record_type", "fields"]
        }
    },
    {
        "type": "function",
        "name": "update_salesforce_status",
        "description": "Update the lead's status in Salesforce after qualification. Valid status values are: SSL, SQL, Unknown, or Disqualified.",
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {
                    "type": "string",
                    "description": "Salesforce record ID"
                },
                "record_type": {
                    "type": "string",
                    "enum": ["Lead", "Contact"],
                    "description": "Type of record"
                },
                "status": {
                    "type": "string",
                    "enum": ["SSL", "SQL", "Unknown", "Disqualified"],
                    "description": "Qualification status. Must be one of: SSL, SQL, Unknown, or Disqualified"
                }
            },
            "required": ["record_id", "record_type", "status"]
        }
    },
    {
        "type": "function",
        "name": "log_to_sheets",
        "description": (
            "Log the workflow results to Google Sheets. Pass the results from other tool calls. "
            "Lead info (id, email, name, company, etc.) is automatically included from context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "inquiry_type": {
                    "type": "string",
                    "description": "Classification result: Sales Inquiry, Support Request, Spam/Solicitation, or Empty"
                },
                "status": {
                    "type": "string",
                    "description": "Qualification status: SQL, SSL, Unknown, or Disqualified"
                },
                "status_detail": {
                    "type": "string",
                    "description": "Reason for the qualification status (from qualify_lead result)"
                },
                "email_body": {
                    "type": "string",
                    "description": "The email body that was sent (from draft_email_response)"
                },
                "gmail_response": {
                    "type": "string",
                    "description": "Response from send_email tool (stringify the result)"
                },
                "sfdc_update_response": {
                    "type": "string",
                    "description": "Response from update_salesforce_status tool (stringify the result)"
                },
                "sfdc_task_response": {
                    "type": "string",
                    "description": "Response from log_salesforce_task tool (stringify the result)"
                },
                "error": {
                    "type": "string",
                    "description": "Any error that occurred during the workflow"
                }
            },
            "required": ["inquiry_type", "status"]
        }
    },
    {
        "type": "function",
        "name": "log_salesforce_task",
        "description": "Log the sent email as a Salesforce Task (WhoId = Lead or Contact ID)",
        "parameters": {
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "Salesforce Lead or Contact ID (WhoId)"
                },
                "subject": {
                    "type": "string",
                    "description": "Task subject"
                },
                "body": {
                    "type": "string",
                    "description": "Task body/description"
                },
                "direction": {
                    "type": "string",
                    "description": "Inbound or Outbound",
                    "default": "Outbound"
                }
            },
            "required": ["person_id", "subject", "body"]
        }
    },
    {
        "type": "function",
        "name": "update_lead_state",
        "description": (
            "Update the lead's state with new information discovered during the workflow. "
            "Call this AFTER gathering information from other tools (like Salesforce lookups) "
            "to persist what you learned. Valid fields: industry, employees, website, phone, revenue, "
            "company_name, first_name, last_name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "object",
                    "description": "Key-value pairs of fields to update with their new values",
                    "additionalProperties": {"type": "string"}
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation of why these updates are being made (e.g., 'Retrieved from Salesforce lookup')"
                }
            },
            "required": ["updates", "reason"]
        }
    },
    {
        "type": "function",
        "name": "complete_workflow",
        "description": "Signal that the workflow is complete and provide a summary including all tool responses",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of actions taken"
                },
                "qualification_status": {
                    "type": "string",
                    "description": "Final qualification status"
                },
                "email_sent": {
                    "type": "boolean",
                    "description": "Whether an email was sent"
                },
                "gmail_response": {
                    "type": "string",
                    "description": "Response from send_email (include message ID)"
                },
                "sfdc_update_response": {
                    "type": "string",
                    "description": "Response from update_salesforce_status"
                },
                "sfdc_task_response": {
                    "type": "string",
                    "description": "Response from log_salesforce_task (include task ID)"
                }
            },
            "required": ["summary"]
        }
    }
]


# =============================================================================
# Tool Implementations
# =============================================================================

def lookup_person_in_salesforce(record_id: str, record_type: str, fields: list[str]) -> Dict[str, Any]:
    """Look up a Lead or Contact with specified fields."""
    return salesforce_functions.lookup_person_fields(record_type, record_id, fields)


def send_email(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    """Send email via Gmail API (shared implementation)."""
    # Convert plain text newlines to HTML <br> tags for proper formatting
    html_body = body.replace("\n", "<br>\n")
    
    # gmail_functions.send_email signature: (to, cc, subject, message_text, reply_to="", is_html=False)
    result = gmail_functions.send_email(
        to=to_email,
        cc="",
        subject=subject,
        message_text=html_body,
        is_html=True
    )
    return result


def update_salesforce_status(record_id: str, record_type: str, status: str) -> Dict[str, Any]:
    """Update Salesforce record status (shared implementation)."""
    if record_type == "Lead":
        return salesforce_functions.update_lead_fields(record_id, {"Status": status})
    return salesforce_functions.update_contact_fields(record_id, {"Lead_Status__c": status})


def log_to_sheets(workflow_results: Dict[str, Any], lead_context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Log data to Google Sheets.
    
    Merges workflow_results with lead_context to create a complete row.
    The row order is defined by SHEET_HEADERS.
    
    Args:
        workflow_results: Results from the workflow (inquiry_type, status, status_detail, 
                         email_body, gmail_response, salesforce_response, error)
        lead_context: Original lead data (id, email, first_name, etc.)
    """
    # Start with lead context (original lead data)
    data = dict(lead_context) if lead_context else {}
    
    # Merge in workflow results (these override lead_context if there's overlap)
    data.update(workflow_results)
    
    # Add timestamp
    data["timestamp"] = datetime.now().isoformat()
    
    # Write to sheets - the function will use SHEET_HEADERS order
    googlesheets_functions.writeRow2Sheet(data, SHEET_NAME, SHEET_ID, SHEET_HEADERS)
    return {"success": True, "fields_logged": list(data.keys())}


def log_salesforce_task(person_id: str, subject: str, body: str, direction: str = "Outbound") -> Dict[str, Any]:
    """Log an email as a Salesforce Task."""
    return salesforce_functions.log_sfdc_task(person_id, subject, body, direction)


# =============================================================================
# Tool Executor
# =============================================================================

def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with given arguments."""
    
    tool_map = {
        "lookup_person_in_salesforce": lookup_person_in_salesforce,
        "send_email": send_email,
        "update_salesforce_status": update_salesforce_status,
        "log_salesforce_task": log_salesforce_task,
    }
    
    if tool_name in tool_map:
        try:
            return tool_map[tool_name](**arguments)
        except Exception as e:
            return {"error": str(e), "tool": tool_name}
    
    # Sub-agent tools are handled separately in the agent
    return {"error": f"Unknown tool: {tool_name}"}

