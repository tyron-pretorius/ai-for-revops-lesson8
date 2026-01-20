from simple_salesforce import Salesforce
import os, dotenv
from typing import Dict, Any
from datetime import datetime

dotenv.load_dotenv()

def sfdc_connection():
    username = os.environ["SALESFORCE_USER"]
    password = os.environ["SALESFORCE_PASSWORD"]
    security_token = os.environ["SALESFORCE_TOKEN"]

    return Salesforce(
        username=username,
        password=password,
        security_token=security_token,
        client_id="Replit",
    )

def update_lead_fields(lead_id: str, lead_fields: Dict[str, Any]) -> dict:
    """
    Update fields on an existing Lead.
    
    Args:
        lead_id: The Salesforce Lead Id to update
        lead_fields: Dictionary of field names and values to update on the lead
    
    Returns:
        dict: {'success': True, 'lead_id': lead_id} if successful, or error dict if failed
    """
    sf = sfdc_connection()
    
    # Update the lead with provided fields
    result = sf.Lead.update(lead_id, lead_fields)
    
    # simple-salesforce returns HTTP status code (204) on success, or a dict on error
    # Convert to consistent dict format
    if isinstance(result, dict):
        # Error case - return as is
        return result
    else:
        # Success case - wrap in dict
        return {
            'success': True,
            'lead_id': lead_id,
            'status_code': result
        }

def update_contact_fields(contact_id: str, contact_fields: Dict[str, Any]) -> dict:
    """
    Update fields on an existing Contact.
    
    Args:
        contact_id: The Salesforce Contact Id to update
        contact_fields: Dictionary of field names and values to update on the contact
    
    Returns:
        dict: {'success': True, 'contact_id': contact_id} if successful
    """
    sf = sfdc_connection()
    
    # Update the contact with provided fields
    result = sf.Contact.update(contact_id, contact_fields)
    
    # simple-salesforce returns HTTP status code (204) on success, or a dict on error
    # Convert to consistent dict format
    if isinstance(result, dict):
        # Error case - return as is
        return result
    else:
        # Success case - wrap in dict
        return {
            'success': True,
            'contact_id': contact_id,
            'status_code': result
        }

def log_sfdc_task(person_id: str, subject: str, body: str, direction: str = "Inbound"):
    """
    Create a Task in Salesforce to log email activity.
    
    Args:
        person_id: Contact or Lead ID (WhoId)
        subject: Email subject
        body: Email body content
        direction: 'Inbound' or 'Outbound' (default: 'Inbound')
        activity_date: Activity date in YYYY-MM-DD format (default: today)
        sender_email: Sender email address (default: None)
        record_type_id: Record Type ID for the task (default: '012f100000116jjAAA')
        owner_id: Owner ID for the task (default: '005Qk000001pqtdIAA')
        created_by_tool: Tool that created the task (default: 'Email Responder')
    
    Returns:
        Dictionary with 'success' (bool) and 'id' (task ID) if successful, or error info
    """
    
    sf = sfdc_connection()
    
    # Default activity date to today if not provided
    activity_date = datetime.now().strftime('%Y-%m-%d')
    
    task_fields = {
        'RecordTypeId': '012f100000116jjAAA',
        'WhoId': person_id,
        'Subject': subject,
        'ActivityDate': activity_date,
        'Status': 'Completed',
        'OwnerId': '005Qk000001pqtdIAA',
        'Description': body,
        'Type': 'Email',
        'TaskSubType': 'Email',
        'Task_Direction__c': direction,
    }
    
    try:
        response = sf.Task.create(task_fields)
        return {'success': True, 'id': response['id']}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def lookup_person_fields(sfdc_type: str, record_id: str, fields: list[str] | str) -> dict:
    """
    Lookup a Lead or Contact by ID and return specified fields.
    
    Args:
        sfdc_type: "Lead" or "Contact"
        record_id: Salesforce record ID
        fields: List of API field names or comma-separated string
    
    Returns:
        dict with 'success' and 'data' or 'error'
    """
    if not record_id:
        return {"success": False, "error": "record_id is required"}
    if sfdc_type not in ("Lead", "Contact"):
        return {"success": False, "error": "sfdc_type must be 'Lead' or 'Contact'"}
    
    # Normalize fields
    if isinstance(fields, str):
        fields_list = [f.strip() for f in fields.split(",") if f.strip()]
    else:
        fields_list = [f.strip() for f in fields if f and f.strip()]
    
    if "Id" not in fields_list:
        fields_list.insert(0, "Id")
    
    fields_str = ", ".join(fields_list)
    sf = sfdc_connection()
    
    try:
        query = f"SELECT {fields_str} FROM {sfdc_type} WHERE Id = '{record_id}' LIMIT 1"
        result = sf.query(query)
        records = result.get("records", [])
        if not records:
            return {"success": False, "error": "Record not found"}
        return {"success": True, "data": records[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}