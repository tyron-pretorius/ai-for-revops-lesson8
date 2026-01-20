#!/usr/bin/env python3
"""
Simple webhook test script for Contact Sales API.

Usage:
    python test_webhook.py
"""

import requests


def send_webhook():
    """Send a test webhook to the local API."""
    
    payload = {
        "id": "003Qk00000fyKXqIAM",
        "email": "pretorit@tcd.ie",
        "sfdc_type": "Contact",
        "first_name": "Tyron",
        "last_name": "Pretorius",
        "company_name": "Trinity College Dublin",
        "phone": "+1234567890",
        "sales_inquiry": "We need SMS and Voice APIs for our customer notification system. We expect to send around 50,000 SMS per month and make about 50,000 outbound minutes.",
        "revenue": "",
        "industry": "",
        "employees": "",
        "website": "tcd.ie"
    }
    
    url = "http://localhost:5053/contact-sales"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        print("Sending webhook to local API...")
        print(f"Payload: {payload}")
        response = requests.post(url, json=payload, headers=headers)
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.text}")
        
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to localhost:5050")
        print("Make sure your Flask app is running with: python python_orchestration/main.py")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    send_webhook()
