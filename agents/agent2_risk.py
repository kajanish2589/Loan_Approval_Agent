"""
agents/agent2_risk.py
---------------------
AGENT 2: Financial Risk Analysis Agent     (runs on port 8102)
MCP server it uses: RiskRulesDB

ITS JOB: Are the numbers safe?

NOTICE: this agent does NO maths itself. Every figure comes from an MCP
tool call. Claude only writes the explanation. That is how you prevent
the AI from inventing financial figures - a key point for your evaluation.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI

from shared.llm import ask_claude
from shared.mcp_client import McpToolbox
from shared.schemas import AgentTelemetry, LoanApplication, RiskResponse, RiskResult

app = FastAPI(title="Financial Risk Agent")

SYSTEM_PROMPT = """You are the Financial Risk Analysis Agent at a bank.

You are given figures that have ALREADY been calculated by the bank's
rule engine. Your job is to explain, in plain English, what those figures
mean for the risk of this loan.

CRITICAL RULE: Do not invent, estimate or recalculate any number.
Only refer to the numbers you are given.

Reply with raw JSON only, in exactly this shape:
{
  "reasoning": "<two or three plain sentences about the risk>"
}"""


@app.post("/analyze", response_model=RiskResponse)
async def analyze(application: LoanApplication):
    started = time.time()
    toolbox = McpToolbox("risk_rules_server.py")

    # ---- STEP 1: let the MCP server do ALL the maths ----
    emi_data = (await toolbox.call_many([
        ("calculate_emi", {
            "loan_amount": application.loan_amount,
            "tenure_months": application.tenure_months,
        }),
    ]))[0]
    emi = emi_data["monthly_emi"]

    dti_data, bands, fraud = await toolbox.call_many([
        ("compute_dti", {
            "income_monthly": application.income_monthly,
            "existing_liabilities": application.existing_liabilities_monthly,
            "emi": emi,
        }),
        ("classify_credit_and_loan", {
            "credit_score": application.credit_score,
            "loan_amount": application.loan_amount,
            "income_monthly": application.income_monthly,
        }),
        ("get_fraud_signals", {
            "applicant_id": application.applicant_id,
            "age": application.age,
            "income_monthly": application.income_monthly,
            "loan_amount": application.loan_amount,
            "existing_liabilities": application.existing_liabilities_monthly,
        }),
    ])

    dti = dti_data["dti_ratio"]
    anomalies = fraud["anomalies"]

    # ---- STEP 2: the fallback explanation, written from the real numbers ----
    fallback = {
        "reasoning": (
            f"A new EMI of {emi} brings total monthly debt to "
            f"{dti * 100:.0f}% of income, which is the {dti_data['dti_band']} band. "
            f"Credit risk is {bands['credit_score_risk_level']} and loan size risk is "
            f"{bands['loan_amount_risk']}."
        )
    }

    # ---- STEP 3: ask Claude to explain it like a human would ----
    answer, llm_used = ask_claude(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=(
            f"Monthly income: {application.income_monthly}\n"
            f"New loan EMI: {emi}\n"
            f"Existing monthly EMIs: {application.existing_liabilities_monthly}\n"
            f"Debt-to-income ratio: {dti} ({dti_data['dti_band']} band)\n"
            f"Credit score: {application.credit_score} "
            f"({bands['credit_score_risk_level']} risk)\n"
            f"Loan is {bands['loan_to_income_multiple']}x annual income "
            f"({bands['loan_amount_risk']} risk)\n"
            f"Anomalies detected: {anomalies if anomalies else 'none'}"
        ),
        fallback=fallback,
    )

    # ---- STEP 4: return validated output. Numbers come from MCP, not Claude ----
    result = RiskResult(
        dti_ratio=dti,
        monthly_emi=emi,
        credit_score_risk_level=bands["credit_score_risk_level"],
        loan_amount_risk=bands["loan_amount_risk"],
        anomalies=anomalies,
        reasoning=answer.get("reasoning", fallback["reasoning"]),
    )

    return RiskResponse(
        result=result,
        telemetry=AgentTelemetry(
            agent_name="Financial Risk Agent",
            mcp_tools_called=toolbox.tools_called,
            llm_used=llm_used,
            fallback_used=not llm_used,
            latency_ms=int((time.time() - started) * 1000),
            note=f"EMI {emi}, DTI {dti}",
        ),
    )


@app.get("/health")
def health():
    return {"status": "ok", "agent": "financial_risk"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8102)
