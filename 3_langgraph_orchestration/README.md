# Module 3: LangGraph Workflow

This module demonstrates **when and why to use LangGraph** by implementing the same Contact Sales workflow from Module 2, but with features that would be complex to build with plain Python or simple agent loops.

## Why LangGraph?

### Module 2 (Agentic) vs Module 3 (LangGraph)

| Feature | Module 2 (Agentic) | Module 3 (LangGraph) |
|---------|-------------------|---------------------|
| **Execution** | Sequential agent loop | Parallel + conditional |
| **State** | Implicit (function args) | Explicit TypedDict schema |
| **Loops** | While loops in code | Declarative graph edges |
| **Human-in-loop** | Would need manual polling | Built-in pause/resume |
| **Persistence** | Manual serialization | Automatic with checkpointing |

### When to Use LangGraph

✅ **Use LangGraph when you need:**
- Parallel task execution
- Conditional branching based on state
- Human-in-the-loop with long waits (hours/days)
- Iterative loops (review → revise → review)
- Workflow persistence/resumption

❌ **Don't need LangGraph for:**
- Simple linear workflows
- Single-turn agent responses
- No human interaction needed

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         WORKFLOW START                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   Salesforce  │  │    Marketo    │  │  Web Search   │
│    Lookup     │  │    Lookup     │  │   (OpenAI)    │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                   PARALLEL EXECUTION
                  (all 3 run at once!)
                            │
                            ▼
                ┌───────────────────────┐
                │   Analyze Inquiry     │
                │   (AI sub-agent)      │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │    Qualify Lead       │
                │   SQL/SSL/Disqual     │
                └───────────┬───────────┘
                            │
             ┌──────────────┴──────────────┐
             │                             │
        [Disqualified]               [Other status]
             │                             │
             ▼                             ▼
    ┌────────────────┐           ┌────────────────┐
    │ Skip Email     │           │ Generate Email │◄────────────┐
    └────────┬───────┘           └────────┬───────┘             │
             │                            │                      │
             │                            ▼                      │
             │                   ┌────────────────┐              │
             │                   │  AI Review     │              │
             │                   │  (Score 1-10)  │              │
             │                   └────────┬───────┘              │
             │                            │                      │
             │              ┌─────────────┴─────────────┐        │
             │              │                           │        │
             │         [Score < 7]                 [Score ≥ 7]   │
             │              │                           │        │
             │              └───────────────────────────┼────────┘
             │                    LOOP BACK!            │
             │                                          │
             │                   ┌──────────────────────┴────────┐
             │                   │                               │
             │              [SQL Lead]                      [Other]
             │                   │                               │
             │                   ▼                               │
             │         ┌────────────────┐                        │
             │         │ Send to Slack  │                        │
             │         │ for Approval   │                        │
             │         └────────┬───────┘                        │
             │                  │                                │
             │            ⏸️ PAUSE                               │
             │         (wait for human)                          │
             │                  │                                │
             │         ┌───────────────────────────────┐         │
             │         │        Human Response         │         │
             │         │  @bot approve/reject/changes  │         │
             │         └───────────────┬───────────────┘         │
             │                         │                         │
             │    ┌────────────────────┼────────────────────┐    │
             │    │                    │                    │    │
             │ [approved]         [changes]            [rejected]│
             │    │                    │                    │    │
             │    │                    └────────────────────┼────┘
             │    │                       LOOP BACK!        │
             │    │                                         │
             │    └──────────────────┬──────────────────────┘
             │                       │
             │                       ▼
             │              ┌────────────────┐
             │              │   Send Email   │
             │              └────────┬───────┘
             │                       │
             └───────────┬───────────┘
                         │
                         ▼
                ┌────────────────┐
                │  Update CRM    │
                └────────┬───────┘
                         │
                         ▼
                ┌────────────────┐
                │ Log to Sheets  │
                └────────┬───────┘
                         │
                         ▼
                    WORKFLOW END
```

---

## Key LangGraph Features Demonstrated

### 1. Parallel Execution

Three research tasks run **simultaneously**:

```python
# In graph.py - fan-out from START
builder.add_edge(START, "research_salesforce")
builder.add_edge(START, "research_marketo")
builder.add_edge(START, "research_web")

# Fan-in to next node
builder.add_edge("research_salesforce", "analyze_inquiry")
builder.add_edge("research_marketo", "analyze_inquiry")
builder.add_edge("research_web", "analyze_inquiry")
```

**Without LangGraph:** You'd need `asyncio.gather()` or `concurrent.futures`.

### 2. Conditional Loops

Email review creates an improvement loop:

```python
# Route back to generate_email if review fails
def route_after_email_review(state):
    if not state.get("email_approved_by_ai"):
        return "generate_email"  # LOOP!
    return "check_approval"

builder.add_conditional_edges(
    "review_email",
    route_after_email_review,
    {"generate_email": "generate_email", "check_approval": "check_approval"}
)
```

**Without LangGraph:** You'd need manual while loops and state tracking.

### 3. Human-in-the-Loop

Workflow pauses for Slack approval:

```python
# Node sets status and returns - workflow pauses!
def request_human_approval_node(state):
    send_slack_message(...)
    return {
        "workflow_status": "waiting_for_human",
        "human_approval": {"status": "pending", ...}
    }

# When human responds, workflow resumes from here
def process_human_response_node(state):
    status = state["human_approval"]["status"]
    if status == "changes_requested":
        return  # Will loop back to generate_email
    ...
```

**Without LangGraph:** You'd need to serialize state, poll for responses, deserialize, and resume manually.

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | Flask server with `/lead-handoff` endpoint |
| `graph.py` | LangGraph workflow definition |
| `nodes.py` | Individual workflow step functions |
| `state.py` | TypedDict schema for workflow state |
| `tools.py` | External integrations (Salesforce, Marketo, etc.) |
| `slack_listener.py` | Handles Slack approval responses |

---

## Running the Module

### 1. Start the Flask Server

```bash
cd module_3_langgraph
python main.py
```

Server runs on `http://localhost:5053`

### 2. Start the Slack Listener

In a **separate terminal**:

```bash
cd module_3_langgraph
python slack_listener.py
```

This listens for approval responses in Slack threads.

### 3. Test the Workflow

From the project root:

```bash
python test_webhook.py
```

Or send a POST request to `http://localhost:5053/lead-handoff`.

---

## Human-in-the-Loop

When an email needs approval, the workflow posts to Slack. Just reply naturally in the thread:

```
┌──────────────────────────────────────────────────────────┐
│  Slack Thread                                            │
├──────────────────────────────────────────────────────────┤
│  🤖 Bot: Email approval required for john@example.com    │
│          [email preview]                                 │
│                                                          │
│  👤 You: "Looks good, send it"                          │
│                or                                        │
│  👤 You: "Make it shorter and mention our free trial"   │
│                or                                        │
│  👤 You: "Don't send to this lead"                      │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  slack_listener.py      │
              │  (just forwards message)│
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │  Master Agent           │
              │  (interprets & decides) │
              └────────────┬────────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
         approved      changes       rejected
            │          requested         │
            ▼              │              ▼
       Send email    Loop back &     Skip email
                     regenerate
```

**Architecture Note:** The `slack_listener.py` is just a communication bridge. The **master agent** (in `process_human_response_node`) interprets the human's natural language and decides the next action. This keeps decision-making in the workflow where it belongs.

---

## Environment Variables

Required in `.env`:

```
# OpenAI
OPENAI_API_KEY=sk-...

# Salesforce
SALESFORCE_USER=...
SALESFORCE_PASSWORD=...
SALESFORCE_TOKEN=...

# Marketo
MARKETO_BASE_URL=...
MARKETO_CLIENT_ID=...
MARKETO_CLIENT_SECRET=...

# Slack (for human-in-the-loop)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_APPROVAL_CHANNEL=lead-approvals

# Google (for Gmail and Sheets)
# Uses google_api_auth.json service account file
```

---

## Learning Path

1. **Start with `state.py`** - Understand the data structure
2. **Read `graph.py`** - See how nodes connect
3. **Explore `nodes.py`** - Each workflow step explained
4. **Check `tools.py`** - External integrations
5. **Run it!** - Test with `test_webhook.py`

---

## Comparison: Module 2 vs Module 3

### Module 2 (Agentic Loop)
```python
while not done:
    response = llm.call(messages, tools)
    tool_call = response.tool_calls[0]
    result = execute_tool(tool_call)
    messages.append(result)
```
- Simple and flexible
- LLM decides tool order
- Hard to do parallel or pause/resume

### Module 3 (LangGraph)
```python
graph = StateGraph(WorkflowState)
graph.add_node("research", research_node)
graph.add_node("qualify", qualify_node)
graph.add_edge("research", "qualify")
# ... define all edges and conditions
result = graph.compile().invoke(initial_state)
```
- Explicit workflow definition
- Parallel execution built-in
- Human-in-the-loop with state persistence
