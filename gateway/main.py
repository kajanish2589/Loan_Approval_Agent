"""
gateway/main.py
---------------
THE MICROSERVICE LAYER - the front door of the system. (runs on port 8000)

The Streamlit UI talks ONLY to this. It never talks to agents directly.
That keeps the UI simple and lets you change the agents without touching it.

Open http://127.0.0.1:8000/docs in a browser to try the API by hand.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.graph import AGENTS, run_loan_application
from shared.schemas import FinalResponse, LoanApplication

app = FastAPI(
    title="Loan Approval Gateway",
    description="Agentic AI loan approval system. Submit an application, get an explained decision.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# A simple in-memory store so you can look a case up again.
# A real bank would use a database here.
CASE_STORE: dict[str, dict] = {}


@app.post("/api/v1/loan/apply", response_model=FinalResponse)
async def apply_for_loan(application: LoanApplication):
    """
    Submit a loan application and get a full, explained decision back.
    This runs the whole 4-agent LangGraph workflow.
    """
    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"

    try:
        state = await run_loan_application(application.model_dump(), case_id=case_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"The workflow failed: {error}")

    response = FinalResponse(
        case_id=case_id,
        application=application,
        profile=state.get("profile"),
        risk=state.get("risk"),
        decision=state.get("decision"),
        compliance=state.get("compliance"),
        telemetry=state.get("telemetry", []),
        trace=state.get("trace", []),
        errors=state.get("errors", []),
    )

    CASE_STORE[case_id] = response.model_dump(mode="json")
    return response


@app.get("/api/v1/loan/case/{case_id}")
async def get_case(case_id: str):
    """Look up a case you submitted earlier."""
    if case_id not in CASE_STORE:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return CASE_STORE[case_id]


@app.get("/api/v1/loan/cases")
async def list_cases():
    """List every case from this session."""
    return {
        "count": len(CASE_STORE),
        "cases": [
            {
                "case_id": cid,
                "applicant_id": data["application"]["applicant_id"],
                "classification": (data.get("decision") or {}).get("classification"),
                "risk_score": (data.get("decision") or {}).get("risk_score"),
            }
            for cid, data in CASE_STORE.items()
        ],
    }


@app.get("/health")
async def health():
    """
    Check the gateway AND all four agents.
    Run this first if something is not working - it tells you which
    agent did not start.
    """
    statuses = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in AGENTS.items():
            health_url = url.replace("/analyze", "/health")
            try:
                reply = await client.get(health_url)
                statuses[name] = "up" if reply.status_code == 200 else "unhealthy"
            except Exception:
                statuses[name] = "DOWN"

    all_up = all(value == "up" for value in statuses.values())
    return {
        "gateway": "up",
        "agents": statuses,
        "ready": all_up,
        "hint": None if all_up else "Start the missing agents, then refresh.",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
