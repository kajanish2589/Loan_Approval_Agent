"""
agents/agent1_profile.py
------------------------
AGENT 1: Applicant Profile Agent     (runs on port 8101)
MCP server it uses: ApplicantDB

ITS JOB: Who is this person? How stable are they?

THE PATTERN EVERY AGENT FOLLOWS (learn this once, it repeats 4 times):
  1. Get facts from its MCP server        <- real data
  2. Work out a safe fallback answer      <- so we never depend on the AI
  3. Ask Claude for the human judgement   <- opinion and explanation
  4. Validate with Pydantic and return    <- guaranteed clean output
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI

from shared.llm import ask_claude
from shared.mcp_client import McpToolbox
from shared.schemas import AgentTelemetry, LoanApplication, ProfileResponse, ProfileResult

app = FastAPI(title="Applicant Profile Agent")

SYSTEM_PROMPT = """You are the Applicant Profile Agent at a bank.

Your job is to judge how STABLE this applicant's income and employment are.
You are given real data from the bank's database. Use only that data.
Never invent numbers.

Reply with raw JSON only, in exactly this shape:
{
  "income_stability_score": <integer 0-100, higher is more stable>,
  "credit_history_summary": "<one clear sentence>",
  "reasoning": "<two sentences explaining your score>"
}"""


@app.post("/analyze", response_model=ProfileResponse)
async def analyze(application: LoanApplication):
    started = time.time()
    toolbox = McpToolbox("applicant_db_server.py")

    # ---- STEP 1: get the facts from the MCP server ----
    record, credit_history, employment = await toolbox.call_many([
        ("get_applicant", {"applicant_id": application.applicant_id}),
        ("get_credit_history", {"applicant_id": application.applicant_id}),
        ("assess_employment_risk", {
            "employment_type": application.employment_type,
            "employment_years": application.employment_years,
        }),
    ])

    employment_risk = employment["employment_risk"]

    # ---- STEP 2: note anything missing or concerning ----
    flags = []
    if application.employment_years < 1:
        flags.append("Less than 1 year in current employment")
    if not credit_history["has_history"]:
        flags.append("No banking history with us")
    if credit_history["past_defaults"] > 0:
        flags.append(f"{credit_history['past_defaults']} past default(s) on record")

    # ---- STEP 3: a simple score we can always fall back on ----
    stability = 50
    if application.employment_type == "SALARIED":
        stability += 20
    if application.employment_years >= 5:
        stability += 20
    elif application.employment_years >= 2:
        stability += 10
    if credit_history["past_defaults"] > 0:
        stability -= 25
    stability = max(0, min(100, stability))

    fallback = {
        "income_stability_score": stability,
        "credit_history_summary": (
            f"Credit score {application.credit_score} with "
            f"{credit_history['past_defaults']} past default(s) and "
            f"{credit_history['years_with_bank']} years of banking history."
        ),
        "reasoning": (
            f"{application.employment_type} for {application.employment_years} years "
            f"gives {employment_risk} employment risk."
        ),
    }

    # ---- STEP 4: ask Claude for the human-readable judgement ----
    answer, llm_used = ask_claude(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=(
            f"Applicant: {record['name']}\n"
            f"Age: {application.age}\n"
            f"Employment: {application.employment_type} for {application.employment_years} years\n"
            f"Monthly income: {application.income_monthly}\n"
            f"Credit score: {application.credit_score}\n"
            f"Past defaults: {credit_history['past_defaults']}\n"
            f"Years with our bank: {credit_history['years_with_bank']}\n"
            f"Average balance: {credit_history['avg_balance']}\n"
            f"Employment risk band from the rule book: {employment_risk}"
        ),
        fallback=fallback,
    )

    # ---- STEP 5: return a validated result ----
    # Note: employment_risk always comes from the RULE BOOK, never from Claude.
    result = ProfileResult(
        income_stability_score=int(answer.get("income_stability_score", stability)),
        employment_risk=employment_risk,
        credit_history_summary=answer.get("credit_history_summary", fallback["credit_history_summary"]),
        completeness_flags=flags,
        reasoning=answer.get("reasoning", fallback["reasoning"]),
    )

    return ProfileResponse(
        result=result,
        telemetry=AgentTelemetry(
            agent_name="Applicant Profile Agent",
            mcp_tools_called=toolbox.tools_called,
            llm_used=llm_used,
            fallback_used=not llm_used,
            latency_ms=int((time.time() - started) * 1000),
            note=f"Looked up {record['name']}",
        ),
    )


@app.get("/health")
def health():
    return {"status": "ok", "agent": "applicant_profile"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8101)
