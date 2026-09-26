"""
agents/agent4_compliance.py
---------------------------
AGENT 4: Compliance and Action Orchestrator Agent     (runs on port 8104)
MCP server it uses: NotificationSystem

ITS JOB: Act on the decision and create the paper trail.

IMPORTANT RULE: this agent NEVER changes the decision. It only carries it
out. Keeping "deciding" and "doing" in separate agents is good design and
is worth saying out loud during your walkthrough.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI

from shared.mcp_client import McpToolbox
from shared.schemas import AgentTelemetry, ComplianceRequest, ComplianceResponse, ComplianceResult

app = FastAPI(title="Compliance and Action Agent")


@app.post("/analyze", response_model=ComplianceResponse)
async def analyze(request: ComplianceRequest):
    started = time.time()
    application = request.application
    decision = request.decision
    case_id = request.case_id
    toolbox = McpToolbox("notification_server.py")

    # ---- Carry out every required action through MCP tools ----
    action_data, case_data, notify_data, _audit = await toolbox.call_many([
        ("get_required_action", {"classification": decision.classification}),
        ("create_case", {
            "case_id": case_id,
            "applicant_id": application.applicant_id,
            "classification": decision.classification,
        }),
        ("send_notification", {
            "case_id": case_id,
            "classification": decision.classification,
            "applicant_id": application.applicant_id,
        }),
        ("log_audit", {
            "case_id": case_id,
            "stage": "FINAL_DECISION",
            "payload": (
                f"{decision.classification} | risk_score={decision.risk_score} "
                f"| confidence={decision.confidence} | {decision.explanation}"
            ),
        }),
    ])

    result = ComplianceResult(
        action_taken=action_data["action"],
        notification_sent=notify_data["notification_sent"],
        case_id=case_id,
        timestamp=case_data["created_at"],
        summary=(
            f"Case {case_id} for applicant {application.applicant_id} was "
            f"{decision.classification.replace('_', ' ').lower()} with a risk score of "
            f"{decision.risk_score}/100. {action_data['action']}. "
            f"Routed to {case_data['assigned_queue']}."
        ),
    )

    return ComplianceResponse(
        result=result,
        telemetry=AgentTelemetry(
            agent_name="Compliance and Action Agent",
            mcp_tools_called=toolbox.tools_called,
            llm_used=False,  # this agent is deliberately rule-driven, no AI needed
            fallback_used=False,
            latency_ms=int((time.time() - started) * 1000),
            note=f"Queued to {case_data['assigned_queue']}",
        ),
    )


@app.get("/health")
def health():
    return {"status": "ok", "agent": "compliance"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8104)
