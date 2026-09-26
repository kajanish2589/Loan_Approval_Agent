"""
mcp_servers/applicant_db_server.py
----------------------------------
MCP SERVER 1: ApplicantDB  -- used by Agent 1

WHAT IS AN MCP SERVER?
  It is a small program that exposes TOOLS. An agent can call these tools
  the same way you call a function, but over a standard protocol.
  This means any agent (or any AI) can use it without custom glue code.

RULE: MCP servers NEVER call the LLM. They are pure data providers.
"""

import sys
from pathlib import Path

# Let this file import from the shared/ folder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from shared import rules

mcp = FastMCP("ApplicantDB")


@mcp.tool()
def get_applicant(applicant_id: str) -> dict:
    """Fetch the stored bank record for an applicant."""
    return rules.get_applicant_record(applicant_id)


@mcp.tool()
def get_credit_history(applicant_id: str) -> dict:
    """Fetch past defaults and account age for an applicant."""
    record = rules.get_applicant_record(applicant_id)
    return {
        "past_defaults": record["past_defaults"],
        "years_with_bank": record["years_with_bank"],
        "avg_balance": record["avg_balance"],
        "has_history": record["years_with_bank"] > 0,
    }


@mcp.tool()
def assess_employment_risk(employment_type: str, employment_years: float) -> dict:
    """Return the LOW / MEDIUM / HIGH employment risk band from the rule book."""
    band = rules.band_employment(employment_type, employment_years)
    return {
        "employment_risk": band,
        "rule_applied": f"{employment_type} with {employment_years} years -> {band}",
    }


if __name__ == "__main__":
    # Runs over stdio. The agent starts this automatically - you do NOT
    # need to run it yourself.
    mcp.run()
