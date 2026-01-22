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
from prompts import INQUIRY_TYPE_PROMPT, QUALIFICATION_PROMPT, EMAIL_GENERATION_PROMPT, ORCHESTRATOR_PROMPT

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o"

# Salesforce API field names -> standard field names
SFDC_FIELD_MAPPING = {
    "Industry_Cb__c": "industry",
    "Employees_Cb__c": "employees",
    "Revenue_Cb__c": "revenue",
    "Website": "website",
    "Phone": "phone",
    "Company": "company_name",
    "FirstName": "first_name",
    "LastName": "last_name",
}


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


def _map_sfdc_to_context(sf_data: Dict, context: Dict) -> Dict:
    """Map Salesforce fields to standard names and update context. Returns mapped fields."""
    mapped = {}
    for sf_field, std_field in SFDC_FIELD_MAPPING.items():
        if sf_field in sf_data and sf_data[sf_field] is not None:
            value = sf_data[sf_field]
            # Convert numeric values to clean strings
            if isinstance(value, float) and value.is_integer():
                value = str(int(value))
            else:
                value = str(value)
            context[std_field] = value
            mapped[std_field] = value
    return mapped




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
    
    elif tool_name == "lookup_person_in_salesforce":
        # Special handling - map Salesforce fields to standard names and update lead_context
        result = execute_tool(tool_name, arguments)
        _print_tool_io(tool_name, arguments, result)
        
        if isinstance(result, dict) and result.get("success") and "data" in result:
            mapped = _map_sfdc_to_context(result["data"], lead_context)
            if mapped:
                print(f"     📝 Lead context updated: {mapped}")
        
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
        for i, tool_call in enumerate(tool_calls):
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
            
            # Add line break between tool calls (but not after the last one)
            if i < len(tool_calls) - 1:
                print()
            
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

