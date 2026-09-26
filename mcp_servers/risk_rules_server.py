"""
mcp_servers/risk_rules_server.py
--------------------------------
MCP SERVER 2: RiskRulesDB  -- used by Agent 2

This server owns all the MATHS. Agent 2 is not allowed to calculate
anything itself, and Claude is definitely not allowed to. Every number
in the final decision can be traced back to a tool call here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from shared import rules

mcp = FastMCP("RiskRulesDB")


@mcp.tool()
def get_risk_rules() -> dict:
    """Return the current threshold rule book."""
    return {"thresholds": rules.RULES, "weights": rules.WEIGHTS}


@mcp.tool()
def calculate_emi(loan_amount: float, tenure_months: int) -> dict:
    """Work out the monthly instalment for a loan."""
    emi = rules.monthly_emi(loan_amount, tenure_months)
    return {
        "monthly_emi": emi,
        "total_repayment": round(emi * tenure_months, 2),
        "interest_rate": rules.ANNUAL_INTEREST_RATE,
    }


@mcp.tool()
def compute_dti(income_monthly: float, existing_liabilities: float, emi: float) -> dict:
    """Work out the debt-to-income ratio and its risk band."""
    dti = rules.compute_dti(income_monthly, existing_liabilities, emi)
    return {
        "dti_ratio": dti,
        "dti_band": rules.band_dti(dti),
        "explanation": f"({existing_liabilities} + {emi}) / {income_monthly} = {dti}",
    }


@mcp.tool()
def classify_credit_and_loan(credit_score: int, loan_amount: float, income_monthly: float) -> dict:
    """Return the credit risk band and the loan size risk band."""
    yearly = income_monthly * 12
    return {
        "credit_score_risk_level": rules.band_credit(credit_score),
        "loan_amount_risk": rules.band_loan_size(loan_amount, income_monthly),
        "loan_to_income_multiple": round(loan_amount / yearly, 2) if yearly else None,
    }


@mcp.tool()
def get_fraud_signals(applicant_id: str, age: int, income_monthly: float,
                      loan_amount: float, existing_liabilities: float) -> dict:
    """Look for anything that seems suspicious or unusual."""
    anomalies = []

    if loan_amount > income_monthly * 12 * 8:
        anomalies.append("Loan is more than 8x annual income")
    if existing_liabilities > income_monthly * 0.5:
        anomalies.append("Existing EMIs already consume over 50% of income")
    if age < 23 and income_monthly > 300000:
        anomalies.append("Unusually high income for the stated age")

    record = rules.get_applicant_record(applicant_id)
    if record["past_defaults"] >= 2:
        anomalies.append(f"{record['past_defaults']} past defaults on record")

    return {"anomalies": anomalies, "anomaly_count": len(anomalies)}


if __name__ == "__main__":
    mcp.run()
