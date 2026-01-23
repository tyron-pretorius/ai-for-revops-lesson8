"""
Slack Listener - Communication Bridge for Human-in-the-Loop

This script is a PURE COMMUNICATION BRIDGE between Slack and the workflow server.
It does NOT run any workflow logic - it just forwards messages to main.py.

All workflow execution happens in main.py, keeping concerns cleanly separated:
- slack_listener.py: Receives Slack messages, forwards to main.py
- main.py: Owns all workflow execution (start and resume)

This keeps the listener simple and ensures all workflow logic is in one place.
"""

import sys
import os
import re
import json
import logging
import fcntl
import requests
from typing import Optional, Dict, Any

# Add module directory to path for local imports
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Main.py server URL for forwarding human responses
MAIN_SERVER_URL = os.environ.get("MAIN_SERVER_URL", "http://localhost:5053")

# File-based store for pending workflows (shared between main.py and slack_listener.py)
# In production, use Redis or a database!
PENDING_WORKFLOWS_FILE = os.path.join(MODULE_DIR, ".pending_workflows.json")


# =============================================================================
# PENDING WORKFLOW STORAGE
# These functions are used by both main.py and slack_listener.py
# =============================================================================

def _load_pending_workflows() -> Dict[str, Dict[str, Any]]:
    """Load pending workflows from file."""
    try:
        if os.path.exists(PENDING_WORKFLOWS_FILE):
            with open(PENDING_WORKFLOWS_FILE, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load pending workflows: {e}")
    return {}


def _save_pending_workflows(workflows: Dict[str, Dict[str, Any]]) -> None:
    """Save pending workflows to file."""
    try:
        with open(PENDING_WORKFLOWS_FILE, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(workflows, f, indent=2, default=str)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except IOError as e:
        logger.error(f"Could not save pending workflows: {e}")


def register_pending_workflow(channel: str, thread_ts: str, workflow_state: Dict[str, Any], thread_id: str = None) -> str:
    """Register a workflow that is waiting for human input."""
    workflow_key = f"{channel}:{thread_ts}"
    workflows = _load_pending_workflows()
    workflows[workflow_key] = {
        "state": workflow_state,
        "thread_id": thread_id
    }
    _save_pending_workflows(workflows)
    logger.info(f"📝 Registered pending workflow: {workflow_key} (thread_id: {thread_id})")
    return workflow_key


def get_pending_workflow(channel: str, thread_ts: str) -> Optional[Dict[str, Any]]:
    """Get a pending workflow by channel and thread. Returns dict with 'state' and 'thread_id'."""
    workflow_key = f"{channel}:{thread_ts}"
    workflows = _load_pending_workflows()
    return workflows.get(workflow_key)


def remove_pending_workflow(channel: str, thread_ts: str) -> None:
    """Remove a workflow from pending_workflows file (after it completes)."""
    workflow_key = f"{channel}:{thread_ts}"
    workflows = _load_pending_workflows()
    workflows.pop(workflow_key, None)
    _save_pending_workflows(workflows)


# =============================================================================
# SLACK APP - Pure Communication Bridge
# =============================================================================

def create_slack_app() -> App:
    """
    Create Slack app that forwards messages to main.py.
    
    This is a PURE BRIDGE - no workflow logic here.
    All messages are forwarded to main.py's /human-response endpoint.
    """
    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    bot_user_id = None
    
    try:
        bot_user_id = app.client.auth_test()["user_id"]
        logger.info(f"🤖 Bot user ID: {bot_user_id}")
    except Exception as e:
        logger.error(f"Failed to get bot user ID: {e}")
    
    def strip_bot_mention(text: str) -> str:
        """Remove bot mention from message text."""
        if not text:
            return ""
        if bot_user_id:
            text = text.replace(f"<@{bot_user_id}>", "")
        text = re.sub(r"<@[^>]+>", "", text)
        return text.strip()
    
    @app.event("app_mention")
    def handle_message(event, say):
        """
        Receive Slack message and forward to main.py for processing.
        
        This is a pure bridge - we just:
        1. Validate the message is in a thread
        2. Check there's a pending workflow
        3. Forward to main.py's /human-response endpoint
        4. Relay the response back to Slack
        """
        channel = event.get("channel")
        user = event.get("user")
        ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        raw_text = event.get("text", "")
        
        logger.info(f"📨 Message from {user}: {raw_text[:50]}...")
        
        # Must be in a thread
        if not thread_ts:
            say(
                text="💡 Please reply in the thread of the approval request.",
                thread_ts=ts
            )
            return
        
        # Quick check if there's a pending workflow (for fast feedback)
        pending = get_pending_workflow(channel, thread_ts)
        if not pending:
            say(
                text="❓ No pending approval found for this thread.",
                thread_ts=thread_ts
            )
            return
        
        # Get the human's message (strip bot mention)
        human_message = strip_bot_mention(raw_text).strip()
        
        if not human_message:
            say(
                text="💬 What would you like me to do with this email?",
                thread_ts=thread_ts
            )
            return
        
        # Forward to main.py for workflow processing
        logger.info(f"📤 Forwarding to main.py: {human_message}")
        say(text="🤔 Processing your response...", thread_ts=thread_ts)
        
        try:
            response = requests.post(
                f"{MAIN_SERVER_URL}/human-response",
                json={
                    "channel": channel,
                    "thread_ts": thread_ts,
                    "human_message": human_message,
                    "reviewer": user
                },
                timeout=120  # Workflow might take time
            )
            
            result = response.json()
            status = result.get("status")
            
            logger.info(f"📥 Response from main.py: {status}")
            
            if status == "waiting_for_approval":
                # Email was regenerated, show new draft
                new_body = result.get("email_body", "")
                version = result.get("email_draft_version", 0)
                say(
                    text=f"💬 I've updated the email (v{version}). Here's the new draft:\n\n```{new_body}```\n\nWhat do you think?",
                    thread_ts=thread_ts
                )
            elif status == "completed":
                if result.get("email_sent"):
                    say(text="✅ Email sent!", thread_ts=thread_ts)
                elif result.get("human_decision") == "rejected":
                    say(text="❌ Email not sent (rejected).", thread_ts=thread_ts)
                else:
                    say(text="✅ Workflow completed.", thread_ts=thread_ts)
            elif status == "error":
                error_msg = result.get("error", "Unknown error")
                say(text=f"⚠️ Error: {error_msg[:100]}", thread_ts=thread_ts)
            else:
                say(text=f"ℹ️ Status: {status}", thread_ts=thread_ts)
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ Cannot connect to main.py server")
            say(
                text="⚠️ Cannot connect to the workflow server. Is main.py running?",
                thread_ts=thread_ts
            )
        except requests.exceptions.Timeout:
            logger.error("❌ Request to main.py timed out")
            say(
                text="⚠️ Request timed out. The workflow is taking longer than expected.",
                thread_ts=thread_ts
            )
        except Exception as e:
            logger.error(f"❌ Error forwarding to main.py: {e}")
            say(text=f"⚠️ Something went wrong: {str(e)[:100]}", thread_ts=thread_ts)
    
    return app


def start_listener():
    """Start the Slack listener."""
    print("\n" + "=" * 60)
    print("🤖 Module 3: Slack Listener (Communication Bridge)")
    print("=" * 60)
    print("\nThis is a PURE BRIDGE - no workflow logic runs here.")
    print(f"All messages are forwarded to: {MAIN_SERVER_URL}")
    print("\nListening for messages in approval threads...")
    print("\n" + "=" * 60 + "\n")
    
    app = create_slack_app()
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()


if __name__ == "__main__":
    start_listener()