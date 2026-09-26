# Agentic AI Loan Approval System

A multi-agent AI system that reads a loan application and decides **APPROVED**, **REJECTED**, or **MANUAL_REVIEW** — and explains why.

Built with the exact stack from the case study: Streamlit, FastAPI, LangGraph, FastMCP, and Claude Sonnet 4.6.

---

## Start here (5 steps)

```bash
# 1. Go into the folder
cd loan_agent

# 2. Install everything
pip install -r requirements.txt

# 3. Set up your API key
in .env file         
# Now open .env and paste your key after ANTHROPIC_API_KEY=

# 4. Check everything works
python check_setup_test.py

# 5. Start it all
bash run_all.sh               # Windows: run_all.bat
```

Then open **http://localhost:8501** in your browser.

> **If your API key is not ready**, set `USE_MOCK=true` in `.env`. The whole system still runs end to end using the rule engine instead of Claude. Nothing breaks.

---

## What runs where

| Process | Port | Start it with |
|---|---|---|
| Agent 1 — Applicant Profile | 8101 | `python agents/agent1_profile.py` |
| Agent 2 — Financial Risk | 8102 | `python agents/agent2_risk.py` |
| Agent 3 — Loan Decision | 8103 | `python agents/agent3_decision.py` |
| Agent 4 — Compliance & Action | 8104 | `python agents/agent4_compliance.py` |
| Gateway (FastAPI) | 8000 | `python gateway/main.py` |
| Chatbot UI (Streamlit) | 8501 | `streamlit run ui/app.py` |

The **4 MCP servers do not need starting**. Each agent launches its own automatically.

Check everything is alive: **http://127.0.0.1:8000/health**

---

## How it flows

```
          Streamlit UI (8501)
                 |
          Gateway API (8000)
                 |
          LangGraph orchestrator
                 |
             validate
               /    \          <-- these two run AT THE SAME TIME
        Agent 1      Agent 2
               \    /
              Agent 3
                 |
        route by the verdict
          /      |      \
   approved  rejected  human review
          \      |      /
              Agent 4
                 |
                END
```

---

## The files

```
loan_agent/
├── check_setup_test.py          <- run this first and run after changing any threshold
├── run_all.sh / .bat       <- starts everything
│
├── shared/                 <- code every part uses
│   ├── schemas.py          <- all data shapes (READ THIS FIRST)
│   ├── rules.py            <- the rule book + thresholds  <-- EDIT FOR DEMO
│   ├── llm.py              <- the Claude helper
│   └── mcp_client.py       <- how agents call MCP tools
│
├── mcp_servers/            <- 4 tool servers, no AI inside
│   ├── applicant_db_server.py
│   ├── risk_rules_server.py
│   ├── decision_synthesis_server.py
│   └── notification_server.py
│
├── agents/                 <- 4 FastAPI agents
│   ├── agent1_profile.py
│   ├── agent2_risk.py
│   ├── agent3_decision.py  <- the most important one
│   └── agent4_compliance.py
│
├── orchestrator/graph.py   <- the LangGraph flow (python orchestrator/graph.py run this to show flow diagram)
├── gateway/main.py         <- the API front door
└── ui/app.py               <- the chatbot
```

---

## The one idea that makes this system good

**Claude gives opinions. The rule book gives numbers. If they disagree, a human decides.**

- Every financial figure — EMI, DTI, risk score — comes from an **MCP tool call**, never from Claude. This is why the AI cannot invent numbers.
- Agent 3 gets a verdict from Claude *and* a verdict from the rule engine. If they differ, the case is forced to `MANUAL_REVIEW`.
- If Claude is unreachable, every agent falls back to the rule engine and keeps working.

Say this out loud in your evaluation. It is the difference between a demo and a system a bank could actually use.

---

## Reading order, if you are new to this

1. `shared/schemas.py` — the data shapes
2. `shared/rules.py` — the maths and thresholds
3. `mcp_servers/applicant_db_server.py` — what an MCP tool looks like
4. `agents/agent1_profile.py` — the 5-step pattern every agent follows
5. `agents/agent3_decision.py` — where the AI and the rules are compared
6. `orchestrator/graph.py` — how it is all wired together

---

## For the live-modification part of your evaluation

Practise these until each takes under two minutes.

**1. Flip a decision by changing one number**
Open `shared/rules.py`, change `"approve_below": 35` to `50`, restart Agent 3, resubmit the borderline sample. It now approves.

**2. Add a new rule**
Add a threshold to `RULES`, use it in `hard_reject_reason()`, restart Agent 3.

**3. Add a new MCP tool**
Add a `@mcp.tool()` function in any server file, then call it from that server's agent. No restart of other services needed.

**4. Add a 5th agent**
Copy `agent4_compliance.py`, change the port, add a node and an edge in `orchestrator/graph.py`.

**5. Change the routing**
Edit `route_by_decision()` in `orchestrator/graph.py` to add a new branch.

**6. Show the flow diagram**
```bash
python orchestrator/graph.py
```

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: shared` | Run commands from inside the `loan_agent` folder |
| An agent shows DOWN on `/health` | Check `logs/agentN.log` — usually a port already in use |
| `model not found` from Claude | Try `CLAUDE_MODEL=claude-sonnet-4-5` in `.env` |
| Everything gets rejected | Your test loan is too big for the income. DTI over 0.65 is an instant reject |
| Claude is slow or failing | Set `USE_MOCK=true` in `.env` and carry on |
| Port already in use | Change the port in the agent file and in `orchestrator/graph.py` |

---

## Audit trail

Every decision is appended to `data/audit_log.jsonl`, one line per case. Open it during your walkthrough to show the system is auditable.
