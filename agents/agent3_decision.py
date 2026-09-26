"""
agents/agent3_decision.py
-------------------------
AGENT 3: Loan Decision Agent     (runs on port 8103)
MCP server it uses: DecisionSynthesis

ITS JOB: Approve, reject, or send to a human?

THIS IS THE MOST IMPORTANT AGENT. Explain this one carefully in your
evaluation. The key idea:

    Claude makes a judgement.
    The rule book makes a judgement.
    If they DISAGREE, we trust neither and a human reviews the case.

That is what makes an AI decision defensible to a bank regulator.

Also note: this agent reads Agent 1 and Agent 2's RESULTS. It never
goes back to the raw application data to recalculate anything.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI

from shared import rules
from shared.llm import ask_claude
from shared.mcp_client import McpToolbox
from shared.schemas import AgentTelemetry, DecisionRequest, DecisionResponse, DecisionResult

app = FastAPI(title="Loan Decision Agent")

SYSTEM_PROMPT = """You are the Loan Decision Agent at a bank.

Two other agents have already analysed this application. Using ONLY their
findings, decide the outcome.

Choose one:
  APPROVED       - clearly safe to lend
  REJECTED       - clearly too risky
  MANUAL_REVIEW  - genuinely borderline, or something needs a human eye

Be honest about your confidence. If the evidence is mixed, say so with a
lower confidence number - it is better to send a case to a human than to
guess.

Reply with raw JSON only, in exactly this shape:
{
  "classification": "APPROVED" | "REJECTED" | "MANUAL_REVIEW",
  "confidence": <number between 0.0 and 1.0>,
  "key_factors": ["<short factor>", "<short factor>", "<short factor>"],
  "explanation": "<2 to 4 plain sentences a customer would understand, no jargon>"
}"""


@app.post("/analyze", response_model=DecisionResponse)
async def analyze(request: DecisionRequest):
    started = time.time()
    application = request.application
    profile = request.profile
    risk = request.risk
    toolbox = McpToolbox("decision_synthesis_server.py")

    # ---- STEP 1: instant-rejection check. This beats everything else ----
    hard_check = await toolbox.call("check_hard_rejects", {
        "employment_type": application.employment_type,
        "credit_score": application.credit_score,
        "dti_ratio": risk.dti_ratio,
    })

    if hard_check["is_hard_reject"]:
        reason = hard_check["reason"]
        return DecisionResponse(
            result=DecisionResult(
                classification="REJECTED",
                risk_score=95,
                confidence=1.0,
                key_factors=[reason],
                explanation=(
                    f"This application was rejected automatically because it breaks "
                    f"a mandatory lending rule: {reason.lower()}. No further review is needed."
                ),
            ),
            telemetry=AgentTelemetry(
                agent_name="Loan Decision Agent",
                mcp_tools_called=toolbox.tools_called,
                llm_used=False,
                fallback_used=False,
                latency_ms=int((time.time() - started) * 1000),
                note="Hard reject rule fired - Claude was not consulted",
            ),
        )

    # ---- STEP 2: the GUARDRAIL - what pure maths says ----
    score_data = await toolbox.call("calculate_risk_score", {
        "credit_band": risk.credit_score_risk_level,
        "dti_band": rules.band_dti(risk.dti_ratio),
        "employment_band": profile.employment_risk,
        "loan_band": risk.loan_amount_risk,
    })
    risk_score = score_data["risk_score"]

    rule_data = await toolbox.call("rule_based_verdict", {"risk_score": risk_score})
    rule_verdict = rule_data["verdict"]

    fallback = {
        "classification": rule_verdict,
        "confidence": 0.85,
        "key_factors": [
            f"Overall risk score {risk_score} out of 100",
            f"Debt-to-income {risk.dti_ratio} ({rules.band_dti(risk.dti_ratio)} band)",
            f"Credit risk {risk.credit_score_risk_level}",
            f"Employment risk {profile.employment_risk}",
        ],
        "explanation": (
            f"The overall risk score is {risk_score} out of 100, so the rule book "
            f"verdict is {rule_verdict.replace('_', ' ').lower()}."
        ),
    }

    # ---- STEP 3: what Claude says ----
    answer, llm_used = ask_claude(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=(
            f"=== FROM THE PROFILE AGENT ===\n"
            f"Income stability score: {profile.income_stability_score}/100\n"
            f"Employment risk: {profile.employment_risk}\n"
            f"Credit history: {profile.credit_history_summary}\n"
            f"Warning flags: {profile.completeness_flags or 'none'}\n"
            f"Its reasoning: {profile.reasoning}\n\n"
            f"=== FROM THE RISK AGENT ===\n"
            f"Debt-to-income ratio: {risk.dti_ratio}\n"
            f"Monthly EMI: {risk.monthly_emi}\n"
            f"Credit risk: {risk.credit_score_risk_level}\n"
            f"Loan size risk: {risk.loan_amount_risk}\n"
            f"Anomalies: {risk.anomalies or 'none'}\n"
            f"Its reasoning: {risk.reasoning}\n\n"
            f"=== FROM THE RULE ENGINE ===\n"
            f"Calculated risk score: {risk_score} out of 100\n"
            f"Loan requested: {application.loan_amount} over {application.tenure_months} months"
        ),
        fallback=fallback,
    )

    ai_verdict = answer.get("classification", rule_verdict)
    confidence = float(answer.get("confidence", 0.8))
    factors = list(answer.get("key_factors", fallback["key_factors"]))
    explanation = str(answer.get("explanation", fallback["explanation"]))

    # ---- STEP 4: THE SAFETY RULE. Explain this one in your walkthrough ----
    final_verdict = ai_verdict
    note = "AI and rule book agreed"

    if ai_verdict != rule_verdict:
        final_verdict = "MANUAL_REVIEW"
        factors.append(f"AI said {ai_verdict} but the rule book said {rule_verdict}")
        explanation += (
            " The AI assessment and the bank's rule book did not agree, "
            "so this case has been passed to a human underwriter."
        )
        note = f"DISAGREEMENT: ai={ai_verdict} rules={rule_verdict}"

    elif confidence < rules.RULES["confidence_floor"]:
        final_verdict = "MANUAL_REVIEW"
        factors.append(
            f"Confidence {confidence} is below the required {rules.RULES['confidence_floor']}"
        )
        explanation += " Confidence was too low for an automatic decision."
        note = f"LOW CONFIDENCE: {confidence}"

    result = DecisionResult(
        classification=final_verdict,
        risk_score=risk_score,
        confidence=confidence,
        key_factors=factors,
        explanation=explanation.strip(),
    )

    return DecisionResponse(
        result=result,
        telemetry=AgentTelemetry(
            agent_name="Loan Decision Agent",
            mcp_tools_called=toolbox.tools_called,
            llm_used=llm_used,
            fallback_used=not llm_used,
            latency_ms=int((time.time() - started) * 1000),
            note=note,
        ),
    )


@app.get("/health")
def health():
    return {"status": "ok", "agent": "loan_decision"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8103)
