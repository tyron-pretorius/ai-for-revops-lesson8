"""
Flask application for Module 2: Agentic AI Workflow.

Receives lead handoff notifications and processes them through
an autonomous AI agent that decides what actions to take.
"""

import json
import traceback
from flask import Flask, request, make_response, abort

from agent import run_agent

app = Flask(__name__)


@app.route('/contact-sales', methods=['POST'])
def contact_sales():
    """
    Handle incoming lead handoff notifications.
    
    The AI agent will autonomously:
    1. Analyze the inquiry
    2. Look up context from CRM
    3. Qualify the lead
    4. Draft and send an appropriate response
    """
    payload = request.json
    email = payload.get("email", "unknown")
    
    print(f"\n{'='*60}")
    print(f"📥 Lead handoff received for: {email}")
    print(f"{'='*60}")
    
    try:
        # Run the autonomous agent
        result = run_agent(payload)
        
        return make_response(
            json.dumps({
                "status": "success" if result["success"] else "incomplete",
                "email": email,
                "iterations": result["iterations"],
                "result": result["result"]
            }),
            200,
            {"Content-Type": "application/json"}
        )
        
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"\n❌ Error processing lead handoff:")
        print(traceback_str)
        
        return make_response(
            json.dumps({
                "status": "error",
                "email": email,
                "error": str(e)
            }),
            500,
            {"Content-Type": "application/json"}
        )


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return make_response(
        json.dumps({"status": "healthy", "service": "module-2-agentic"}),
        200,
        {"Content-Type": "application/json"}
    )


if __name__ == '__main__':
    print("\n🤖 Module 2: Agentic AI Workflow Server")
    print("=" * 50)
    print("Endpoints:")
    print("  POST /contact-sales - Process contact sales request")
    print("  GET  /health        - Health check")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5052)

