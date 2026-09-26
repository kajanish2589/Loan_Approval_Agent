"""
mcp_servers/decision_synthesis_server.py
----------------------------------------
MCP SERVER 3: DecisionSynthesis  -- used by Agent 3

This server owns the GUARDRAIL: the decision that maths alone would make.
Agent 3 compares Claude's verdict against this one. If they disagree,
a human reviews the case. That single idea is the strongest part of
your design - be ready to explain it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from shared import rules

mcp = FastMCP("DecisionSynthesis")


@mcp.tool()
def get_decision_matrix() -> dict:
    """Return the cut-off points that turn a risk score into a verdict."""
    return {
        "approve_below": rules.RULES["approve_below"],
        "reject_above": rules.RULES["reject_above"],
        "confidence_floor": rules.RULES["confidence_floor"],
        "note": "Scores between the two cut-offs go to MANUAL_REVIEW.",
    }


@mcp.tool()
def calculate_risk_score(credit_band: str, dti_band: str,
                         employment_band: str, loan_band: str) -> dict:
    """Combine the four risk bands into one score from 0 to 100."""
    score = rules.calculate_risk_score(credit_band, dti_band, employment_band, loan_band)
    return {
        "risk_score": score,
        "breakdown": {
            "credit": f"{credit_band} x {rules.WEIGHTS['credit']}",
            "dti": f"{dti_band} x {rules.WEIGHTS['dti']}",
            "employment": f"{employment_band} x {rules.WEIGHTS['employment']}",
            "loan_size": f"{loan_band} x {rules.WEIGHTS['loan_size']}",
        },
    }


@mcp.tool()
def rule_based_verdict(risk_score: int) -> dict:
    """The verdict that pure maths would give, with no AI involved."""
    verdict = rules.rule_based_decision(risk_score)
    return {"verdict": verdict, "risk_score": risk_score}


@mcp.tool()
def check_hard_rejects(employment_type: str, credit_score: int, dti_ratio: float) -> dict:
    """Check the instant-rejection rules. These override everything else."""
    reason = rules.hard_reject_reason(employment_type, credit_score, dti_ratio)
    return {"is_hard_reject": reason is not None, "reason": reason}


@mcp.tool()
def get_policy_limits(location: str) -> dict:
    """Some cities have tighter maximum loan amounts."""
    return rules.get_policy_limit(location)


if __name__ == "__main__":
    mcp.run()
