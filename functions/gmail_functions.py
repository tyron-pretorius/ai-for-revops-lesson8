import base64
import os
from email.message import EmailMessage
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(SCRIPT_DIR, '..', 'google_api_auth.json')
EMAIL = "tyron@theworkflowpro.com"

# Define the scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service(user_email):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    delegated_credentials = credentials.with_subject(user_email)
    return build('gmail', 'v1', credentials=delegated_credentials)

def send_email(to, cc, subject, message_text, reply_to="", is_html=False):
    # Create the email message
    service = get_gmail_service("tyron@theworkflowpro.com")
    
    message = EmailMessage()
    message['From'] = EMAIL
    message['To'] = to
    message['Cc'] = cc
    message['Subject'] = subject
    message['Reply-To'] = reply_to  # Set Reply-To header if provided
    
    if is_html:
        # Set HTML content
        message.set_content(message_text, subtype='html')
    else:
        # Set plain text content
        message.set_content(message_text)

    # Encode the message to base64
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    body = {'raw': raw_message}

    # Send the message
    sent_message = service.users().messages().send(userId='me', body=body).execute()
    return sent_message

if __name__ == "__main__":
    result =send_email("tyron@theworkflowpro.com", "tyron@telnyx.com",'', "Test Subject", "Test Message")
    print(result)