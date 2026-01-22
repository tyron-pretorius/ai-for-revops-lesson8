import csv
import os
import sys

# Add parent directory to Python path to allow imports from functions module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions import gpt_functions
from prompts import QUALIFICATION_PROMPT

# Get absolute path to CSV file (in same directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FREEMAIL_CSV = os.path.join(SCRIPT_DIR, 'Freemail Domains.csv')

def is_freemail(email):
    # Read freemail domains from CSV file
    with open(FREEMAIL_CSV, 'r') as csvfile:
        reader = csv.reader(csvfile)
        freemail_domains = [row[0] for row in reader]

    # Extract domain from email address
    domain = email.split('@')[-1]

    # Check if domain is in freemail domains list
    return domain in freemail_domains


def qualify(revenue, industry, employees,email, sales_inquiry):

    revenue_values = ["$0-$1M", "$1M-$10M", "$10M-$50M", "$50M-$100M", "$100M-$250M", "$250M-$500M", "$500M-$1B", "$1B-$10B", "$10B+"]

    if is_freemail(email):
      status = "SSL"
      status_detail = "freemail"
    elif revenue and revenue not in revenue_values[:3]:
      status = "SQL"
      status_detail = "revenue >= $50m"
    elif industry == "Internet Software & Services" and int(employees) >= 100:
      status = "SQL"
      status_detail = "industry = Internet Software & Services and employees >= 100"
    else:
      ai_qualification_response = gpt_functions.create_response(QUALIFICATION_PROMPT, sales_inquiry)
      status = ai_qualification_response.get("status")
      status_detail = ai_qualification_response.get("reason")


    return status, status_detail