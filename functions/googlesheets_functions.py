from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os
import time

MAX_REQUESTS_PER_MINUTE = 60
TIME_INTERVAL = 60 / MAX_REQUESTS_PER_MINUTE

# Get absolute path to service account file (in parent directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(SCRIPT_DIR, '..', 'google_api_auth.json')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Authenticate and construct service
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

def writeRow2Sheet(dict, sheet_name, spreadsheet_id, headers):
    """
    Write a row to Google Sheets.
    
    Args:
        row_dict: Dictionary with column names as keys
        sheet_name: Name of the sheet tab
        spreadsheet_id: Google Sheets ID
        headers: List of column headers (defines order)
    """
    time.sleep(TIME_INTERVAL)

    # Convert dict to list in header order
    row_data = [dict.get(h, '') for h in headers]
    values = [row_data]

    range_name = f'{sheet_name}!A2'

    sheet = service.spreadsheets()
    body = {'values': values}
    
    result = sheet.values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body=body).execute()

    print(f"{result.get('updates').get('updatedCells')} cells updated.")