# Module 2: Agentic AI Workflow

This module demonstrates an **autonomous AI agent** that handles lead handoffs by deciding what actions to take using OpenAI function calling.

## Key Concept: Agent Decides What To Do

Unlike Module 1 (plain Python) where the code dictates the exact sequence, here the **AI agent reasons** about what it needs to do:

```
Module 1 (Deterministic):
  classify() → qualify() → generate_email() → send()
  
Module 2 (Agentic):
  Agent thinks: "I need to understand this inquiry first"
  Agent calls: analyze_inquiry tool
  Agent thinks: "The volumes are mentioned, let me calculate spend"
  Agent calls: calculate_monthly_spend tool
  Agent thinks: "This is a high-value lead, I should..."
  ...continues reasoning...
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                        │
│                    (Main reasoning loop)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  "A lead has been handed off. What should I do?"            │
│                                                              │
│  Agent decides to call tools based on reasoning:            │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │  Sub-Agent:     │  │  Sub-Agent:     │                   │
│  │  Inquiry        │  │  Spend          │                   │
│  │  Analysis       │  │  Calculator     │                   │
│  └────────┬────────┘  └────────┬────────┘                   │
│           │                    │                             │
│  ┌────────┴────────────────────┴────────┐                   │
│  │                                       │                   │
│  │        Available Tools                │                   │
│  │  • lookup_person_in_salesforce       │                   │
│  │  • analyze_inquiry (sub-agent)       │                   │
│  │  • calculate_monthly_spend (sub-agent)│                  │
│  │  • qualify_lead                       │                   │
│  │  • draft_email_response (sub-agent)  │                   │
│  │  • send_email                         │                   │
│  │  • update_salesforce_status          │                   │
│  │  • log_to_sheets                      │                   │
│  │  • complete_workflow                  │                   │
│  │                                       │                   │
│  └───────────────────────────────────────┘                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Sub-Agents

The orchestrator can delegate specialized tasks to sub-agents:

### 1. Inquiry Analysis Sub-Agent
Deeply analyzes the sales inquiry to understand:
- Type (sales/support/spam)
- Use case
- Volume mentions
- Urgency
- Prohibited use cases

### 2. Spend Calculation Sub-Agent
Calculates estimated monthly spend based on:
- SMS volumes → $0.004/msg
- Voice minutes → $0.005/min
- Data usage → $12.50/GB
- Phone numbers → $1.00/number/month
- SIMs → $2.00/SIM/month

### 3. Email Draft Sub-Agent
Creates personalized email responses based on qualification status.

## Why This Matters

**Flexibility**: The agent can adapt to different situations:
- If no volumes mentioned → Agent decides to ask for more info
- If spam detected → Agent skips email and just logs
- If high urgency → Agent prioritizes quick response

**Extensibility**: Add new tools without changing the flow:
- Add a "research_company" tool
- The agent will decide when to use it

**Transparency**: You can see the agent's reasoning in the message history.

## Running

```bash
cd module_2_agentic
python main.py
# Server runs on http://localhost:5052

# Test with curl:
curl -X POST http://localhost:5052/lead-handoff \
  -H "Content-Type: application/json" \
  -d '{
    "id": "00Q123",
    "email": "test@company.com",
    "first_name": "John",
    "sales_inquiry": "We need SMS API for 100k messages/month",
    "revenue": "$10M-$50M",
    "sfdc_type": "Lead"
  }'
```

## Example Agent Reasoning

```
--- Iteration 1 ---
🔧 Tool call: analyze_inquiry
  🔬 Running inquiry analysis sub-agent...
  ✅ Analysis complete: sales - Looking for SMS API provider...

--- Iteration 2 ---
🔧 Tool call: calculate_monthly_spend
  💰 Running spend calculation sub-agent...
  ✅ Spend calculated: $2,400.00

--- Iteration 3 ---
🔧 Tool call: qualify_lead
  Result: SQL (High estimated monthly spend)

--- Iteration 4 ---
🔧 Tool call: draft_email_response
  ✉️ Running email draft sub-agent...
  ✅ Email drafted (147 chars)

--- Iteration 5 ---
🔧 Tool call: send_email
🔧 Tool call: update_salesforce_status
🔧 Tool call: log_to_sheets

--- Iteration 6 ---
🔧 Tool call: complete_workflow

✅ Workflow completed!
   Summary: Qualified as SQL based on $2,400/mo spend estimate. Sent response encouraging demo meeting.
```

## vs Module 1

| Aspect | Module 1 | Module 2 |
|--------|----------|----------|
| Flow | Fixed sequence | Agent decides |
| Branching | if/else | Agent reasoning |
| New capabilities | Code changes | Add tools |
| Transparency | Print statements | Message history |
| Adaptability | Limited | High |

