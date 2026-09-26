"""
mcp_servers/notification_server.py
----------------------------------
MCP SERVER 4: NotificationSystem  -- used by Agent 4

Handles the "what do we DO about it" side: create a case file,
send the letter, write the audit log.

The audit log is written to data/audit_log.jsonl - one line per event.
Open that file during your demo to prove the system is auditable.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

mcp = FastMCP("NotificationSystem")

# Where the audit trail is written
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
AUDIT_FILE = DATA_DIR / "audit_log.jsonl"


@mcp.tool()
def create_case(case_id: str, applicant_id: str, classification: str) -> dict:
    """Open a formal case file for this application."""
    queues = {
        "APPROVED": "DISBURSEMENT_QUEUE",
        "REJECTED": "CLOSED_REJECTED",
        "MANUAL_REVIEW": "UNDERWRITING_QUEUE",
    }
    return {
        "case_id": case_id,
        "applicant_id": applicant_id,
        "status": classification,
        "assigned_queue": queues.get(classification, "UNDERWRITING_QUEUE"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


@mcp.tool()
def send_notification(case_id: str, classification: str, applicant_id: str) -> dict:
    """Pretend to email or SMS the applicant. In a real bank this calls a mail service."""
    templates = {
        "APPROVED": "Your loan has been approved. The sanction letter is on its way.",
        "REJECTED": "We are unable to approve your loan at this time.",
        "MANUAL_REVIEW": "Your application is under review. We will respond within 2 working days.",
    }
    message = templates.get(classification, "Your application has been received.")

    # This print is your proof during the demo that the action happened
    print(f"[NOTIFY] {case_id} -> {applicant_id}: {message}", file=sys.stderr)

    return {
        "notification_sent": True,
        "channel": "EMAIL",
        "message": message,
        "sent_at": datetime.now().isoformat(timespec="seconds"),
    }


@mcp.tool()
def log_audit(case_id: str, stage: str, payload: str) -> dict:
    """Append one line to the permanent audit trail."""
    entry = {
        "case_id": case_id,
        "stage": stage,
        "payload": payload,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    with open(AUDIT_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return {"logged": True, "file": str(AUDIT_FILE)}


@mcp.tool()
def get_required_action(classification: str) -> dict:
    """What the bank must do next for this verdict."""
    actions = {
        "APPROVED": "Sanction letter generated and queued for disbursement",
        "REJECTED": "Rejection letter generated with reason codes",
        "MANUAL_REVIEW": "Case assigned to the underwriting team for human review",
    }
    return {"action": actions.get(classification, "Case logged for review")}


if __name__ == "__main__":
    mcp.run()
