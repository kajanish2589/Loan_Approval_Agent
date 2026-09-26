"""
orchestrator/graph.py
---------------------
THE ORCHESTRATION ENGINE - built with LangGraph.

This is the file your evaluator will ask about most. Understand it well.

WHAT LANGGRAPH DOES
  It runs your agents in the right order, passes data between them, and
  lets you branch based on results. You describe the flow as a graph of
  NODES (steps) and EDGES (arrows between steps).

THE FLOW
                       START
                         |
                    [validate]
                       /    \\          <-- these two run AT THE SAME TIME
            [profile]        [risk]         because neither needs the other
                       \\    /
                     [decision]
                         |
                   <route by verdict>
                    /    |     \\
           [approved] [rejected] [human_review]
                    \\    |     /
                   [compliance]
                         |
                        END
"""

import sys
import uuid
from pathlib import Path
from typing import Annotated, List, Optional, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from langgraph.graph import END, START, StateGraph

from shared.schemas import (
    AgentTelemetry,
    ComplianceResult,
    DecisionResult,
    LoanApplication,
    ProfileResult,
    RiskResult,
)

# Where each agent lives
AGENTS = {
    "profile": "http://127.0.0.1:8101/analyze",
    "risk": "http://127.0.0.1:8102/analyze",
    "decision": "http://127.0.0.1:8103/analyze",
    "compliance": "http://127.0.0.1:8104/analyze",
}

TIMEOUT = 90.0


# ===============================================================
# THE STATE - the shared notebook that every node reads and writes
# ===============================================================
def add(existing: list, new: list) -> list:
    """
    Tells LangGraph to APPEND to these lists instead of overwriting them.
    This matters because profile and risk run in parallel - without this,
    whichever finishes last would wipe out the other's notes.
    """
    return (existing or []) + (new or [])


class LoanState(TypedDict):
    case_id: str
    application: dict
    profile: Optional[dict]
    risk: Optional[dict]
    decision: Optional[dict]
    compliance: Optional[dict]
    trace: Annotated[List[str], add]
    telemetry: Annotated[List[dict], add]
    errors: Annotated[List[str], add]


# ===============================================================
# A helper to call an agent over HTTP
# ===============================================================
async def call_agent(name: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(AGENTS[name], json=payload)
        response.raise_for_status()
        return response.json()


def _json_ready(application: dict) -> dict:
    """Make sure the timestamp is a string before sending it over HTTP."""
    return LoanApplication(**application).model_dump(mode="json")


# ===============================================================
# THE NODES - each one is a step in the flow
# ===============================================================
async def validate_node(state: LoanState) -> dict:
    """Check the application is well formed before we spend money on AI calls."""
    try:
        LoanApplication(**state["application"])
        return {"trace": ["Validation passed"]}
    except Exception as error:
        return {"trace": ["Validation FAILED"], "errors": [f"Invalid application: {error}"]}


async def profile_node(state: LoanState) -> dict:
    """Run Agent 1."""
    try:
        response = await call_agent("profile", _json_ready(state["application"]))
        return {
            "profile": response["result"],
            "telemetry": [response["telemetry"]],
            "trace": ["Agent 1 (Profile) finished"],
        }
    except Exception as error:
        return {"errors": [f"Profile agent failed: {error}"], "trace": ["Agent 1 FAILED"]}


async def risk_node(state: LoanState) -> dict:
    """Run Agent 2. Runs at the same time as Agent 1."""
    try:
        response = await call_agent("risk", _json_ready(state["application"]))
        return {
            "risk": response["result"],
            "telemetry": [response["telemetry"]],
            "trace": ["Agent 2 (Risk) finished"],
        }
    except Exception as error:
        return {"errors": [f"Risk agent failed: {error}"], "trace": ["Agent 2 FAILED"]}


async def decision_node(state: LoanState) -> dict:
    """Run Agent 3, feeding it the results of Agents 1 and 2."""
    # If either earlier agent died, we cannot decide safely - ask a human.
    if not state.get("profile") or not state.get("risk"):
        return {
            "decision": DecisionResult(
                classification="MANUAL_REVIEW",
                risk_score=50,
                confidence=0.0,
                key_factors=["An analysis agent was unavailable"],
                explanation="Part of the automated analysis could not run, so a human must review this application.",
            ).model_dump(),
            "trace": ["Agent 3 skipped - sent to human review"],
        }

    try:
        response = await call_agent("decision", {
            "application": _json_ready(state["application"]),
            "profile": state["profile"],
            "risk": state["risk"],
        })
        return {
            "decision": response["result"],
            "telemetry": [response["telemetry"]],
            "trace": [f"Agent 3 (Decision) said {response['result']['classification']}"],
        }
    except Exception as error:
        return {"errors": [f"Decision agent failed: {error}"], "trace": ["Agent 3 FAILED"]}


# ---- the three branch nodes. They just record which path we took ----
async def approved_node(state: LoanState) -> dict:
    return {"trace": ["Path: APPROVED - preparing sanction"]}


async def rejected_node(state: LoanState) -> dict:
    return {"trace": ["Path: REJECTED - preparing rejection letter"]}


async def human_review_node(state: LoanState) -> dict:
    return {"trace": ["Path: MANUAL REVIEW - queued for a human underwriter"]}


async def compliance_node(state: LoanState) -> dict:
    """Run Agent 4. Every path ends up here."""
    if not state.get("decision"):
        return {"errors": ["No decision to act on"], "trace": ["Agent 4 skipped"]}

    try:
        response = await call_agent("compliance", {
            "application": _json_ready(state["application"]),
            "decision": state["decision"],
            "case_id": state["case_id"],
        })
        return {
            "compliance": response["result"],
            "telemetry": [response["telemetry"]],
            "trace": ["Agent 4 (Compliance) finished"],
        }
    except Exception as error:
        return {"errors": [f"Compliance agent failed: {error}"], "trace": ["Agent 4 FAILED"]}


# ===============================================================
# THE ROUTER - this is the conditional edge
# ===============================================================
def route_by_decision(state: LoanState) -> str:
    """
    Look at the verdict and pick which branch to take next.
    LangGraph calls this AFTER decision_node and uses the returned
    string to choose the next node.
    """
    decision = state.get("decision")
    if not decision:
        return "human_review"

    verdict = decision.get("classification", "MANUAL_REVIEW")
    return {
        "APPROVED": "approved",
        "REJECTED": "rejected",
        "MANUAL_REVIEW": "human_review",
    }.get(verdict, "human_review")


# ===============================================================
# BUILDING THE GRAPH
# ===============================================================
def build_graph():
    graph = StateGraph(LoanState)

    # 1. Register every node
    graph.add_node("validate", validate_node)
    graph.add_node("profile", profile_node)
    graph.add_node("risk", risk_node)
    graph.add_node("decision", decision_node)
    graph.add_node("approved", approved_node)
    graph.add_node("rejected", rejected_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("compliance", compliance_node)

    # 2. Draw the arrows
    graph.add_edge(START, "validate")

    # FAN OUT: validate points to BOTH agents, so they run in parallel
    graph.add_edge("validate", "profile")
    graph.add_edge("validate", "risk")

    # FAN IN: decision waits for BOTH to finish before it runs
    graph.add_edge("profile", "decision")
    graph.add_edge("risk", "decision")

    # THE CONDITIONAL EDGE: pick a branch based on the verdict
    graph.add_conditional_edges(
        "decision",
        route_by_decision,
        {"approved": "approved", "rejected": "rejected", "human_review": "human_review"},
    )

    # All three branches join back together at compliance
    graph.add_edge("approved", "compliance")
    graph.add_edge("rejected", "compliance")
    graph.add_edge("human_review", "compliance")
    graph.add_edge("compliance", END)

    return graph.compile()


# Build it once when this file is imported
LOAN_GRAPH = build_graph()


async def run_loan_application(application: dict, case_id: str | None = None) -> dict:
    """The single entry point. The gateway calls this."""
    case_id = case_id or f"CASE-{uuid.uuid4().hex[:8].upper()}"

    initial_state: LoanState = {
        "case_id": case_id,
        "application": application,
        "profile": None,
        "risk": None,
        "decision": None,
        "compliance": None,
        "trace": [f"Case {case_id} started"],
        "telemetry": [],
        "errors": [],
    }

    return await LOAN_GRAPH.ainvoke(initial_state)


def print_diagram():
    """Print the flow chart. Handy to show during your walkthrough."""
    print(LOAN_GRAPH.get_graph().draw_ascii())


if __name__ == "__main__":
    print_diagram()
