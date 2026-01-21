"""
Shared OpenAI Responses API Functions

This module provides reusable functions for making OpenAI Responses API calls.
Used across all modules (python_orchestration, module_2_agentic, module_3_langgraph).

We use the Responses API exclusively (not Chat Completions) because:
- Supports stored prompts (pmpt_xxx)
- Native web search tool
- Consistent interface across all modules
"""

import os
import json
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-5"  # Default model


def create_response(
    prompt: str,
    input_text: str = "",
    model: str = MODEL,
    tools: Optional[List[Dict]] = None
):
    """
    Call OpenAI Responses API with a prompt and input.
    
    Args:
        prompt: Either a stored prompt ID (pmpt_xxx) or instruction text
        input_text: The user input to process
        model: Model to use (default: gpt-5)
        temperature: Ignored (not supported by gpt-5 in Responses API)
        tools: Optional list of tools (e.g., [{"type": "web_search_preview"}])
        
    Returns:
        - With tools: Raw response object (caller handles parsing)
        - Without tools: Parsed JSON response
    """
    if tools:
        # Tool mode (e.g., web search) - return raw response for caller to parse
        # Use 'input' as a user message for the model to process with tools
        return client.responses.create(
            model=model,
            tools=tools,
            input=[
                {"role": "user", "content": prompt}
            ]
        )
    else:
        # JSON mode
        resp = client.responses.create(
            model=model,
            instructions=prompt,
            input=[
                {"role": "system", "content": "Return ONLY valid JSON."},
                {"role": "user", "content": input_text},
            ],
            text={"format": {"type": "json_object"}}
        )
        return json.loads(resp.output_text)


if __name__ == "__main__":
    # Test the function
    result = create_response(
        prompt="Classify this inquiry into: Sales Inquiry, Support, Spam, or Empty. Respond with JSON: {\"category\": \"...\"}",
        input_text="I want to buy SMS services for my business"
    )
    print("Result:", result)
