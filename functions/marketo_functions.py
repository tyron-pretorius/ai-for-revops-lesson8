import requests
import json
import time
import os
import dotenv
from datetime import datetime, timedelta

dotenv.load_dotenv()

base_url = os.environ.get('MARKETO_BASE_URL')
client_id = os.environ.get('MARKETO_CLIENT_ID')
client_secret = os.environ.get('MARKETO_CLIENT_SECRET')

# Get an access token
def getToken():
    response = requests.get(
        base_url + '/identity/oauth/token?grant_type=client_credentials&client_id=' + 
        client_id + '&client_secret=' + client_secret
    )
    temp = json.loads(response.text)
    token = temp['access_token']
    remaining = temp['expires_in']
    return [token, remaining]

def lookupLead(token, filterType, filterValues, fields=None):
    """
    Look up lead(s) in Marketo by various filter types.
    
    Args:
        token: Access token for authentication
        filterType: Type of filter (e.g., 'id', 'email', 'leadPartitionId')
        filterValues: Value(s) to filter by (can be comma-separated string or list)
        fields: Optional comma-separated string of fields to return
    
    Returns:
        JSON response with lead data
    """
    url = base_url + '/rest/v1/leads.json'
    
    # Default fields if none provided
    if fields is None:
        fields = 'id,email,createdAt,firstName,lastName'
    
    # Convert list to comma-separated string if needed
    if isinstance(filterValues, list):
        filterValues = ','.join(map(str, filterValues))
    
    params = {
        'access_token': token,
        'filterType': filterType,
        'filterValues': filterValues,
        'fields': fields
    }
    
    response = requests.get(url=url, params=params)
    return response.json()

# Get an access token and make sure it has more than 60 secs of life
def checkTokenLife():
    remaining = 0
    while remaining < 60:
        time.sleep(remaining)  # if the remaining time is less than 60 secs then wait for the token to expire before getting a new one
        temp = getToken()
        token = temp[0]
        remaining = temp[1]
    return token


# Get the starting token needed to page through activities since the start date
def getStartPage(token, sinceDate):
    url = base_url + '/rest/v1/activities/pagingtoken.json'
    params = {
        'access_token': token,
        'sinceDatetime': sinceDate
    }
    response = requests.get(url=url, params=params)
    data = response.json()
    return data['nextPageToken']


# Get information for the current page, optionally filtered by lead ID(s)
def pagenation(token, nextPageToken, leadIds, activityIds):
    url = base_url + '/rest/v1/activities.json'
    params = {
        'access_token': token,
        'nextPageToken': nextPageToken,
        'leadIds': leadIds,
        'activityTypeIds': activityIds
    }
    
    response = requests.get(url=url, params=params)
    data = response.json()
    return data

def getActivitiesforLead(leadId, days_in_past = 7):

    # Configuration variables
    activityIds = [1, 2, 10]  # Activity type IDs to filter (e.g., 1= Visited Webpage , 2 = Fill Out Form,  10= Open Email)
    sinceDate = (datetime.now() - timedelta(days=days_in_past)).strftime("%Y-%m-%dT%H:%M:%S")

    # Lead ID(s) to retrieve activities for - can be a single ID or comma-separated list (up to 30)
    leadIds = [leadId] # Set to None to get all leads

    more = True
    
    # Get a token with more than 60 secs of life
    token = checkTokenLife()
    
    # Get the starting token needed to page through activities since the start date
    nextPageToken = getStartPage(token, sinceDate)
    
    # Create an empty list to store all the activity information
    activities = []
    
    # Iterate through each page and add the activity info to the list
    while more:
        # Get a token with more than 60 secs of life
        token = checkTokenLife()
        
        # Get all the information from this page (with optional lead ID filtering)
        data = pagenation(token, nextPageToken, leadIds, activityIds)
        
        # Get the next page token
        nextPageToken = data['nextPageToken']
        
        # Parse the activity information and store it in the list
        if 'result' in data:
            activity_info = data['result']
            activities = activities + activity_info
        
        # If there are more results then this will return True
        more = data['moreResult']
    
    # Return activities as list of dictionaries (native JSON format)
    return {
        'success': True,
        'lead_id': leadId,
        'days_in_past': days_in_past,
        'activity_count': len(activities),
        'activities': activities
    }