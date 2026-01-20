import os, requests

slack_token = os.environ["SLACK_BOT_TOKEN"]

def send_slack_message_channel(channel_name, message):
  url = 'https://slack.com/api/chat.postMessage'
  headers = {
      'Authorization':
      f'Bearer {slack_token}',
      'Content-Type': 'application/json',
  }

  payload = {
      'channel': f'#{channel_name}',
      'text': message
  }

  response = requests.post(url, headers=headers, json=payload, timeout=90)
  return response.json()