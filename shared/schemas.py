"""
shared/schemas.py
-----------------
Every data shape in the project lives here.

Think of these as FORMS. Data must fill in the form correctly or Pydantic
rejects it. This is what stops bad data from reaching your agents.

Build this file FIRST. Everything else imports from it.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Short names so we don't repeat ourselves
RiskBand = Literal["LOW", "MEDIUM", "HIGH"]
Verdict = Literal["APPROVED", "REJECTED", "MANUAL_REVIEW"]


# ===============================================================
# 1. INPUT - what the user submits
# ===============================================================
class LoanApplication(BaseModel):
    applicant_id: str
    age: int = Field(ge=18, le=75)
    income_monthly: float = Field(gt=0)
    employment_type: Literal["SALARIED", "SELF_EMPLOYED", "CONTRACT", "UNEMPLOYED"]
    employment_years: float = Field(ge=0)
    credit_score: int = Field(ge=300, le=900)
    loan_amount: float = Field(gt=0)
    tenure_months: int = Field(ge=6, le=360)
    existing_liabilities_monthly: float = Field(ge=0)
    location: str = "Unknown"
    application_timestamp: datetime = Field(default_factory=datetime.now)


# ===============================================================
# 2. AGENT OUTPUTS - one model per agent
# ===============================================================
class ProfileResult(BaseModel):
    """Agent 1 answers: who is this person?"""
    income_stability_score: int = Field(ge=0, le=100)
    employment_risk: RiskBand
    credit_history_summary: str
    completeness_flags: List[str] = []
    reasoning: str


class RiskResult(BaseModel):
    """Agent 2 answers: are the numbers safe?"""
    dti_ratio: float
    monthly_emi: float
    credit_score_risk_level: RiskBand
    loan_amount_risk: RiskBand
    anomalies: List[str] = []
    reasoning: str


class DecisionResult(BaseModel):
    """Agent 3 answers: approve, reject, or ask a human?"""
    classification: Verdict
    risk_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    key_factors: List[str] = []
    explanation: str


class ComplianceResult(BaseModel):
    """Agent 4 answers: what did we DO about it?"""
    action_taken: str
    notification_sent: bool
    case_id: str
    timestamp: str
    summary: str


# ===============================================================
# 3. TELEMETRY - proof of what each agent actually did
#    (this is what makes your system "explainable" and "auditable")
# ===============================================================
class AgentTelemetry(BaseModel):
    agent_name: str
    mcp_tools_called: List[str] = []
    llm_used: bool = False
    fallback_used: bool = False
    latency_ms: int = 0
    note: str = ""


# ===============================================================
# 4. WRAPPERS - what agents send back over HTTP
# ===============================================================
class ProfileResponse(BaseModel):
    result: ProfileResult
    telemetry: AgentTelemetry


class RiskResponse(BaseModel):
    result: RiskResult
    telemetry: AgentTelemetry


class DecisionResponse(BaseModel):
    result: DecisionResult
    telemetry: AgentTelemetry


class ComplianceResponse(BaseModel):
    result: ComplianceResult
    telemetry: AgentTelemetry


# Agent 3 needs Agent 1 + Agent 2 results as its input
class DecisionRequest(BaseModel):
    application: LoanApplication
    profile: ProfileResult
    risk: RiskResult


class ComplianceRequest(BaseModel):
    application: LoanApplication
    decision: DecisionResult
    case_id: str


# ===============================================================
# 5. FINAL RESPONSE - what the gateway returns to the UI
# ===============================================================
class FinalResponse(BaseModel):
    case_id: str
    application: LoanApplication
    profile: Optional[ProfileResult] = None
    risk: Optional[RiskResult] = None
    decision: Optional[DecisionResult] = None
    compliance: Optional[ComplianceResult] = None
    telemetry: List[AgentTelemetry] = []
    trace: List[str] = []
    errors: List[str] = []
