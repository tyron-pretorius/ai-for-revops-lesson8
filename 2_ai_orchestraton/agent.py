"""
Agentic AI workflow using OpenAI function calling.

This agent autonomously handles lead handoffs by:
1. Analyzing the inquiry (using a sub-agent)
2. Looking up context from Salesforce
3. Qualifying the lead
4. Calculating monthly spend if needed (using a sub-agent)
5. Drafting and sending an appropriate response

The key difference from Module 1 is that the AI DECIDES what to do,
rather than following a predetermined sequence.
"""

import os
import sys
import json
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

# Add project root to path for shared functions
PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from functions import gpt_functions
from tools import TOOLS, execute_tool

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o"


# =============================================================================
# Sub-Agent Prompts
# =============================================================================

INQUIRY_TYPE_PROMPT = """

For every incoming request, you must classify it into one and only one of the following categories:
1. Sales Inquiry
2. Spam/Solicitation
3. Support Request
4. Empty

Your entire output MUST be a single JSON object matching the provided schema.
Do NOT provide explanations, reasoning, or extra text. Output only JSON.

Category Definitions

1. Sales Inquiry

Classify as “Sales Inquiry” if the requester is:
- Asking about Telnyx products, pricing, features, capabilities, integrations, or general usage.
- Describing how they want to use Telnyx services.
- Comparing Telnyx to another provider or complaining about their current provider.
- Asking about managed accounts.
- Providing any business use case, even briefly.

If you are in doubt, or the message is short but plausible, default to Sales Inquiry.

2. Spam / Solicitation

Mark as Spam/Solicitation only if:
- Someone is trying to sell TO Telnyx (agencies, recruiters, vendors, etc.)
- The content is obviously irrelevant, promotional, off-topic, or unrelated to communications APIs.
- It resembles SEO spam, ads, list selling, generic marketing outreach, or non-business junk.

Do not mark as spam simply because the message is short or vague — default to Sales Inquiry unless clearly spam.

3. Support Request

This category is ONLY for contacts explicitly asking Telnyx for help resolving a technical or account-related problem.

This includes:
- Issues with Telnyx portal login, verification, onboarding, or setup.
- Configuration help for existing accounts.
- Problems sending/receiving SMS, calls, data using Telnyx services.
- Billing or account access issues.

This does NOT include messages like:
- “We want to use Telnyx to communicate with our support customers.” → This is Sales Inquiry
“We’re having issues with Twilio and exploring alternatives.” → Sales Inquiry
- “We want to support our users via SMS.” → Sales Inquiry

To classify as a Support Request, the user must be directly asking Telnyx to fix or assist with a Telnyx-related technical issue.

4. Empty

Classify as Empty if:

- The submission contains no meaningful content
- It is blank, whitespace, or unreadable
- It only includes filler such as: "N/A", "test", "-", ".", "none", "na", asdf" (obvious random typing)

Inquiry: {inquiry}

You must ALWAYS respond with a single JSON object matching this schema:

{{
  "category": "Sales Inquiry | Spam/Solicitation | Support Request | Empty"
}}
"""


QUALIFICATION_PROMPT = """You're an inbound SDR at Telnyx.  You just received this contact sales request and your job is to qualify the lead into one of 4 categories: SQL, SSL, Unknown, or Disqualified.

Step 1. 
The first thing to do is to check if they intend to use Telnyx' service for bad use cases such as debt collection, gambling promotion, or cannabis marketing. If it is clear that they are using Telnyx for one of these bad use cases
then you should return "Disqualified"

Step 2.
Once you have determined that they are not using Telnyx for a bad use case then check:
- If the email is a freemail then return "SSL"
- Else if their revenue is greater than $50m then return "SQL"
- Else if they are in the Internet Software & Services industry and have more than 100 employees then return "SQL"

Step 3.
If the person does not meet any of the conditions from Step 2. then we need to assess their spend potential. Please look at the sales inquiry to see if they mention their current monthly spend or monthly volumes. If they do not mention any
spend or volumes then you should return "Unknown". If they mention volumes then you must make sure the volumes are volumes per month using extrapolation if necessary and then using the pricing table below to calculate the monthly spend:
- SMS: 0.004 USD per SMS
- Voice: 0.005 USD per minute
- Data: 12.50 USD per GB
- Numbers: 1.00 USD per number per month
- SIMs: 2.00 USD per SIM per month

Step 4.
Once you have determined their monthly spend potential you should return "SQL" if the spend is more than $1000 per month else you should return "SSL".

Sales Inquiry: {inquiry}
Email: {email}
Revenue: {revenue}
Industry: {industry}
Employees: {employees}

Respond with a JSON object:
{{
    "status": "SQL | SSL | Unknown | Disqualified"
    "reason": "The reason for the qualification"
}}
"""


EMAIL_GENERATION_PROMPT = """You are Eve an expert SDR at Telnyx crafting a response email.

You're an inbound SDR at Telnyx.  You just received this contact sales request and your job is to formulate a response to the contact.

You always respond with a response that shows you understand why they are reaching out to Telnyx and not with just a list of features or ways you can help.

Every message you write follows the message template and is under 150 words.

If you do not know an answer do not guess, especially if it involves pricing.

Lead Information:
- Name: {first_name}
- Inquiry: {inquiry}
- Status: {qualification_status}
- Inquiry Type: {inquiry_type}
- Additional Context: {context}

Your message template:  

First Line:  acknowledge their outreach and reason for reaching out to the team 

Second Line: Bridge their reason for reaching out with letting them know that Telnyx can help meet their needs

Closing:
- If the inquiry type is "Support" then direct them to first search support articles (https://support.telnyx.com/) for answers to their questions and if they can't find their answers in the support articles then they should contact support@telnyx.com
- If the status is "SQL" then strongly encourage the person to set up a meeting using this link: https://calendly.com/telnyx-sales/30min
- If the status is "Disqualified" then state that it looks like Telnyx cannot support their use case and direct them to our acceptable use policy (https://telnyx.com/acceptable-use-policy)
- If the status is "SSL" then encourage the person to use the AI-bot on Telnyx's website or portal to answer future questions
- If the status is "Unknown" then ask the person for a detailed description of how they plan to use Telnyx and what their expected monthly volume and spend will be

Ensure that when following the guidelines below you stick to the message template above.

Guidelines:
- Always reply in the same language as the "Sales Inquiry"

Respond with a JSON object:
{{
    "email_body": "the email body text"
}}"""


# =============================================================================
# Main Agent System Prompt
# =============================================================================

ORCHESTRATOR_PROMPT = """You are an intelligent sales operations agent at Telnyx.

A lead has just been handed off to you. Your job is to:
1. Gather missing information about the lead (lookup in Salesforce if needed)
2. Analyze the inquiry and qualify the lead
3. Draft and send them a response email
4. Update the person's status in Salesforce
5. Log the email sent as a task to Salesforce
6. Log all information to Google Sheets
7. Call complete_workflow with a summary

Guidelines:
- If the inquiry type is "Spam/Solicitation" then just log and skip email
- ALWAYS call update_lead_state after discovering new information from lookups
- The lead state you update will be used for Google Sheets logging
"""


# =============================================================================
# Sub-Agent Functions (use shared gpt_functions)
# =============================================================================

def run_inquiry_analysis_subagent(inquiry: str) -> Dict[str, Any]:
    """Run the inquiry classification sub-agent."""
    print("  🔬 Running inquiry type sub-agent...")
    prompt = INQUIRY_TYPE_PROMPT.format(inquiry=inquiry)
    return gpt_functions.create_response(prompt, "Classify this inquiry.", model=MODEL)


def run_qualification_subagent(inquiry: str, email: str, revenue: str, industry: str, employees: str) -> Dict[str, Any]:
    """Run the qualification sub-agent."""
    print("  🎯 Running qualification sub-agent...")
    prompt = QUALIFICATION_PROMPT.format(
        inquiry=inquiry,
        email=email,
        revenue=revenue,
        industry=industry,
        employees=employees,
    )
    return gpt_functions.create_response(prompt, "Qualify this lead.", model=MODEL)


def run_email_draft_subagent(
    first_name: str,
    inquiry: str,
    qualification_status: str,
    inquiry_type: str = "sales",
    context: str = ""
) -> Dict[str, Any]:
    """Run the email drafting sub-agent."""
    print("  ✉️ Running email draft sub-agent...")
    prompt = EMAIL_GENERATION_PROMPT.format(
        first_name=first_name,
        inquiry=inquiry,
        qualification_status=qualification_status,
        inquiry_type=inquiry_type,
        context=context
    )
    result = gpt_functions.create_response(prompt, "Draft the email.", model=MODEL)
    print(f"  ✅ Email drafted ({len(result.get('email_body', ''))} chars)")
    return result


# =============================================================================
# Tool Handler
# =============================================================================

def _truncate(value, max_len=200):
    """Truncate a string value for display."""
    s = str(value)
    return s[:max_len] + "..." if len(s) > max_len else s


def _print_tool_io(tool_name: str, arguments: Dict[str, Any], result: Any):
    """Print tool input and output in a consistent format."""
    print(f"  🔧 {tool_name}")
    print(f"     📥 Input: {_truncate(arguments, 300)}")
    print(f"     📤 Output: {_truncate(result, 300)}")




def handle_tool_call(tool_name: str, arguments: Dict[str, Any], lead_context: Dict) -> str:
    """Handle a tool call from the agent, including sub-agent calls."""
    
    # Sub-agent tools
    if tool_name == "analyze_inquiry":
        result = run_inquiry_analysis_subagent(arguments["inquiry_text"])
        _print_tool_io(tool_name, arguments, result)
        return json.dumps(result)

    elif tool_name == "qualify_lead":
        result = run_qualification_subagent(
            inquiry=arguments["inquiry_text"],
            email=arguments["email"],
            revenue=arguments.get("revenue", ""),
            industry=arguments.get("industry", ""),
            employees=arguments.get("employees", ""),
        )
        _print_tool_io(tool_name, arguments, result)
        return json.dumps(result)
    
    elif tool_name == "draft_email_response":
        result = run_email_draft_subagent(
            arguments["first_name"],
            arguments["inquiry_text"],
            arguments["qualification_status"],
            arguments.get("inquiry_type", "sales"),
            arguments.get("additional_context", "")
        )
        _print_tool_io(tool_name, arguments, result)
        return json.dumps(result)
    
    elif tool_name == "complete_workflow":
        result = {
            "status": "completed",
            "summary": arguments.get("summary", ""),
            "qualification_status": arguments.get("qualification_status", ""),
            "email_sent": arguments.get("email_sent", False),
            "gmail_response": arguments.get("gmail_response", ""),
            "sfdc_update_response": arguments.get("sfdc_update_response", ""),
            "sfdc_task_response": arguments.get("sfdc_task_response", "")
        }
        _print_tool_io(tool_name, arguments, result)
        return json.dumps(result)
    
    elif tool_name == "update_lead_state":
        # AI-managed state update - the AI decides what to store
        updates = arguments.get("updates", {})
        reason = arguments.get("reason", "")
        
        # Handle case where AI passes fields directly instead of in "updates"
        if not updates:
            # Extract any field that isn't "reason" as an update
            updates = {k: v for k, v in arguments.items() if k != "reason"}
        
        # Apply updates to lead_context
        for key, value in updates.items():
            # Convert numeric values to strings for consistency
            if isinstance(value, (int, float)):
                value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
            lead_context[key] = str(value) if value is not None else ""
        
        result = {
            "success": True,
            "fields_updated": list(updates.keys()),
            "reason": reason
        }
        _print_tool_io(tool_name, arguments, result)
        print(f"     📝 Lead state updated: {updates}")
        return json.dumps(result)
    
    elif tool_name == "log_to_sheets":
        # Special handling - pass lead_context for merging
        from tools import log_to_sheets
        result = log_to_sheets(workflow_results=arguments, lead_context=lead_context)
        _print_tool_io(tool_name, arguments, result)
        return json.dumps(result)
    
    # Standard tools
    else:
        result = execute_tool(tool_name, arguments)
        _print_tool_io(tool_name, arguments, result)
        return json.dumps(result)


# =============================================================================
# Main Agent Loop
# =============================================================================

def _extract_tool_calls(resp) -> list:
    """Extract tool calls from a Responses API response."""
    tool_calls = []
    for item in resp.output:
        # Responses API uses "function_call" type (not "tool_call")
        if getattr(item, "type", "") == "function_call":
            tool_calls.append(item)
    return tool_calls



def run_agent(lead_data: Dict[str, Any], max_iterations: int = 15) -> Dict[str, Any]:
    """
    Run the agentic workflow for a lead handoff.
    
    The agent autonomously decides what tools to call based on the situation.
    """
    print(f"\n{'='*60}")
    print(f"🤖 Starting Agentic Workflow for: {lead_data.get('email', 'Unknown')}")
    print(f"{'='*60}")
    
    # Build initial context message
    initial_message = f"""A new lead has been handed off to you. Here's what we know:

Lead ID: {lead_data.get('id', 'Unknown')}
Record Type: {lead_data.get('sfdc_type', 'Lead')}
Email: {lead_data.get('email', 'Unknown')}
First Name: {lead_data.get('first_name', 'Unknown')}
Last Name: {lead_data.get('last_name', 'Unknown')}
Company: {lead_data.get('company_name', 'Unknown')}
Sales Inquiry: {lead_data.get('sales_inquiry', 'No inquiry provided')}

Additional fields from CRM:
- Revenue: {lead_data.get('revenue', 'Unknown')}
- Industry: {lead_data.get('industry', 'Unknown')}
- Employees: {lead_data.get('employees', 'Unknown')}

Please handle this lead appropriately. Analyze their inquiry, qualify them, and respond."""

    messages = [{"role": "user", "content": initial_message}]
    
    workflow_complete = False
    iteration = 0
    final_result = {}
    
    while not workflow_complete and iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")
        
        # Call the model
        response = client.responses.create(
            model=MODEL,
            instructions=ORCHESTRATOR_PROMPT,
            input=messages,
            tools=TOOLS,
            tool_choice="required",
        )

        print(f"Response: {response.output_text}")
        
        tool_calls = _extract_tool_calls(response)
        
        # Check if done (no tool calls)
        if not tool_calls:
            print("🏁 Agent finished (no more tool calls)")
            if response.output_text:
                print(f"Final message: {response.output_text}")
            break
        
        # Process tool calls
        for tool_call in tool_calls:
            tool_name = tool_call.name
            arguments = json.loads(tool_call.arguments or "{}")
            
            # Execute the tool
            result = handle_tool_call(tool_name, arguments, lead_data)
            
            # For Responses API, add the function call first, then the output
            # 1. Add the function call that was made
            messages.append({
                "type": "function_call",
                "call_id": tool_call.call_id,
                "name": tool_call.name,
                "arguments": tool_call.arguments
            })
            
            # 2. Add the function call output
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result
            })
            
            # Check if workflow is complete
            if tool_name == "complete_workflow":
                workflow_complete = True
                final_result = json.loads(result)
                print(f"\n✅ Workflow completed!")
                print(f"   Summary: {final_result.get('summary', 'N/A')}")
    
    if iteration >= max_iterations:
        print(f"⚠️ Max iterations ({max_iterations}) reached")
    
    return {
        "success": workflow_complete,
        "iterations": iteration,
        "result": final_result,
        "messages": messages
    }


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    # Test with sample lead
    test_lead = {
        "id": "003Qk00000fyKXqIAM",
        "email": "pretorit@tcd.ie",
        "sfdc_type": "Contact",
        "first_name": "Tyron",
        "last_name": "Pretorius",
        "company_name": "Telnyx",
        "phone": "+1234567890",
        "sales_inquiry": "We need SMS and Voice APIs for our customer notification system. We expect to send around 150,000 SMS per month and make about 150,000 outbound minutes.",
        "revenue": "$10M-$50M",
        "industry": "",
        "employees": "",
        "website": "telnyx.com"
    }
    
    result = run_agent(test_lead)
    print(f"\n{'='*60}")
    print("Final Result:")
    print(json.dumps(result["result"], indent=2))

