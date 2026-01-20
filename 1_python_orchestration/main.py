from flask import Flask, request, make_response, abort
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import os
import traceback

import qualification_functions
from functions import salesforce_functions, gpt_functions, googlesheets_functions, slack_functions, gmail_functions
from prompts import INQUIRY_PROMPT, EMAIL_PROMPT

app = Flask(__name__)

HEADERS = ["timestamp", "id", "email", "sfdc_type", "first_name", "last_name", "company_name", "website", "phone", "sales_inquiry","revenue", "industry", "employees", 
            "inquiry_type", "status","status_detail", "email_requirements", "email_body", "sfdc_update_response", "gmail_response", "sfdc_task_response", "error"]

GOOGLE_SHEET_NAME = 'Python'
GOOGLE_SHEET_ID = '1Yay6Bf7KEjOxWmKp_aMa_Cmn-R42hYq2ykoLd1O5_Io'


@app.route('/contact-sales', methods=['POST'])
def contact_sales():
    """Handle incoming Contact Sales webhook requests."""
    payload = request.json
    print(f"📥 Contact Sales webhook received: {payload}")

    # Initialize info as dict with empty defaults
    info = {header: '' for header in HEADERS}
    
    # Populate from payload
    for key, value in payload.items():
        if key in info:
            info[key] = value

    # Set timestamp
    dt_cst = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Chicago"))
    info["timestamp"] = dt_cst.strftime('%Y-%m-%dT%H:%M:%S%z')
    
    # Extract commonly used values
    id = payload.get("id", '')
    email = payload.get("email", '')
    first_name = payload.get("first_name", '')
    sfdc_type = payload.get("sfdc_type", '')
    sales_inquiry = payload.get("sales_inquiry", '')
    revenue = payload.get("revenue", '')
    industry = payload.get("industry", '')
    employees = payload.get("employees", '')

    try:

        inquiry_response = gpt_functions.create_response(INQUIRY_PROMPT, sales_inquiry)
        inquiry_data = inquiry_response
        inquiry_type = inquiry_data.get("category").lower()
        info["inquiry_type"] = inquiry_type

        if inquiry_type == "spam/solicitation":
            status = "Disqualified"
            status_detail = "Spam/Solicitation"
            pass

        elif inquiry_type == "support":
            email_requirements = ["Direct them to first search support articles (https://support.telnyx.com/) for answers to their questions",
                                  "Mention that if they can't find their answers in the support aritcles then they should contact support@telnyx.com."]

        else:

            status, status_detail = qualification_functions.qualify(revenue, industry, employees, email, sales_inquiry)

            if status == "SQL":
                email_requirements=["Strongly encourage the person to set up a meeting using this link: https://calendly.com/telnyx-sales/30min"]
            elif status == "SSL":
                email_requirements=["Encourage the person to use the AI-bot on Telnyx's website or portal to answer future questions"]
            elif status == "Unknown":
                email_requirements=["Ask the person for a detailed description of how they plan to use Telnyx and what their expected monthly volume and spend will be"]
            elif status == "Disqualified":
                email_requirements=["State that it looks like Telnyx cannot support their use case and direct them to our acceptable use policy (https://telnyx.com/acceptable-use-policy)"]

        info["status"] = status
        info["status_detail"] = status_detail
        
        info["email_requirements"] = str(email_requirements)
        input = f"Sales Inquiry: {sales_inquiry}\nEmail Requirements: {email_requirements}"
        email_response = gpt_functions.create_response(EMAIL_PROMPT, input)
        email_body = email_response.get("email_body")
        # Replace newlines with <br> tags for HTML email
        email_body_html = email_body.replace('\n', '<br><br>')
        email_full = f"Hi {first_name},<br><br>{email_body_html}<br><br>Best,<br>Quinn"
        info["email_body"] = email_body_html

        gmail_response = gmail_functions.send_email("tyron@theworkflowpro.com", email, '', "Telnyx Contact Sales Response", email_full, is_html=True)
        
        # Check if email was sent successfully
        if 'SENT' not in gmail_response.get('labelIds', []):
            slack_functions.send_slack_message_channel("wins", f"Contact Sales Flow Error\n\nGmail response = '{gmail_response}' for {email}")
        
        # Convert dict to string for Google Sheets (can't store dicts directly)
        info["gmail_response"] = json.dumps(gmail_response)

        # Log email as Salesforce task (only if email was sent and not support inquiry)
        if 'SENT' in gmail_response.get('labelIds', []):
            sfdc_task_response = salesforce_functions.log_sfdc_task(
                person_id=id,
                subject="Telnyx Contact Sales Response",
                body=email_body,
                direction="Outbound"
            )
            
            # Check if Salesforce task was logged successfully
            if not sfdc_task_response.get('success', False):
                slack_functions.send_slack_message_channel(
                    "wins", 
                    f"Contact Sales Flow Error\n\nSalesforce task logging failed: '{sfdc_task_response}' for {email}"
                )
            
            # Convert dict to string for Google Sheets (can't store dicts directly)
            info["sfdc_task_response"] = json.dumps(sfdc_task_response)
        else:
            info["sfdc_task_response"] = ""

        if sfdc_type == "Lead" and inquiry_type != "support":
            sfdc_update_response = salesforce_functions.update_lead_fields(id, {"Status": status})
        elif sfdc_type == "Contact" and inquiry_type != "support":
            sfdc_update_response = salesforce_functions.update_contact_fields(id, {"Lead_Status__c": status})
        
        # Check if Salesforce update was successful (status_code 204 = success)
        salesforce_status_code = sfdc_update_response.get('status_code', 0)
        if salesforce_status_code != 204:
            slack_functions.send_slack_message_channel("wins", f"Contact Sales Flow Error\n\nSalesforce response = '{sfdc_update_response}' for {email}")
        
        # Convert dict to string for Google Sheets (can't store dicts directly)
        info["sfdc_update_response"] = json.dumps(sfdc_update_response)

        info["id"] = f"https://telnyx.lightning.force.com/lightning/r/Lead/{id}/view"
        googlesheets_functions.writeRow2Sheet(info, GOOGLE_SHEET_NAME, GOOGLE_SHEET_ID, HEADERS)

        print(f"✅ Contact Sales completed for {email}")

    except Exception as e:
        traceback_str = traceback.format_exc()
        msg = f"An error occurred: {str(e)}\nTraceback: {traceback_str}"
        info['error'] = msg
        googlesheets_functions.writeRow2Sheet(info, GOOGLE_SHEET_NAME, GOOGLE_SHEET_ID, HEADERS)
        
        slack_functions.send_slack_message_channel('wins',f"Contact Sales Flow Error\n\nScript error occured for {email}\n\nhttps://docs.google.com/spreadsheets/d/1Yay6Bf7KEjOxWmKp_aMa_Cmn-R42hYq2ykoLd1O5_Io/edit")
        abort(422)

    return make_response('Successfully received request', 200)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)
