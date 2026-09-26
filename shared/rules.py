"""
shared/rules.py
---------------
The bank's RULE BOOK plus a small fake database.

THE BIG IDEA OF THIS PROJECT
    Claude gives opinions and plain-English explanations.
    THIS FILE gives hard numbers and hard rules.
    Numbers must always come from here, never from Claude's imagination.

Every threshold is at the top so you can change one LIVE during your
evaluation and show a decision flip. That is one of the things you are
scored on.
"""

# ===============================================================
# THRESHOLDS  <-- EDIT THESE LIVE DURING THE DEMO
# ===============================================================
RULES = {
    "dti_low": 0.35,            # debt-to-income up to 0.35 is comfortable
    "dti_medium": 0.50,         # up to 0.50 is acceptable, above is risky
    "credit_good": 680,         # at or above this = LOW credit risk
    "credit_fair": 600,         # at or above this = MEDIUM, below = HIGH
    "safe_loan_multiple": 5.0,  # loan should be at most 5x yearly income
    "approve_below": 35,        # risk score under 35 -> APPROVED
    "reject_above": 70,         # risk score over 70  -> REJECTED
    "confidence_floor": 0.70,   # Claude unsure? -> MANUAL_REVIEW
    "min_credit_score": 500,    # below this = instant rejection
    "max_dti": 0.65,            # above this = instant rejection
}

# How much each factor matters in the final score. Must add up to 1.0
WEIGHTS = {"credit": 0.35, "dti": 0.30, "employment": 0.20, "loan_size": 0.15}

# Turning a band into points. LOW is safe, HIGH is risky.
BAND_POINTS = {"LOW": 10, "MEDIUM": 50, "HIGH": 90}

ANNUAL_INTEREST_RATE = 0.10  # 10% per year, used for the EMI calculation


# ===============================================================
# FAKE DATABASE
# In a real bank this would be DB2 / Oracle / Postgres.
# ===============================================================
APPLICANT_DB = {
    "APP001": {"name": "Ravi Kumar",  "past_defaults": 0, "years_with_bank": 8, "avg_balance": 250000},
    "APP002": {"name": "Sneha Patil", "past_defaults": 2, "years_with_bank": 1, "avg_balance": 4000},
    "APP003": {"name": "Arun Menon",  "past_defaults": 0, "years_with_bank": 2, "avg_balance": 60000},
    "APP004": {"name": "Divya Nair",  "past_defaults": 1, "years_with_bank": 5, "avg_balance": 90000},
    "APP005": {"name": "Imran Shaikh", "past_defaults": 0, "years_with_bank": 0, "avg_balance": 15000},
    "APP010": {"name": "Kajanish B S", "past_defaults": 0, "years_with_bank": 10, "avg_balance": 60000},
}

# Some cities have tighter lending limits
POLICY_LIMITS = {
    "Mumbai": {"max_loan": 10000000},
    "Chennai": {"max_loan": 8000000},
    "Default": {"max_loan": 5000000},
}


def get_applicant_record(applicant_id: str) -> dict:
    """Look up bank history. Returns safe defaults if we have never seen them."""
    return APPLICANT_DB.get(
        applicant_id,
        {"name": "Unknown Applicant", "past_defaults": 0, "years_with_bank": 0, "avg_balance": 0},
    )


def get_policy_limit(location: str) -> dict:
    return POLICY_LIMITS.get(location, POLICY_LIMITS["Default"])


# ===============================================================
# CALCULATIONS  (pure maths, no AI)
# ===============================================================
def monthly_emi(loan_amount: float, tenure_months: int) -> float:
    """Standard EMI formula. Returns the monthly payment."""
    r = ANNUAL_INTEREST_RATE / 12
    n = tenure_months
    if r == 0:
        return round(loan_amount / n, 2)
    emi = loan_amount * r * (1 + r) ** n / ((1 + r) ** n - 1)
    return round(emi, 2)


def compute_dti(income_monthly: float, existing_liabilities: float, emi: float) -> float:
    """Debt-to-Income = all monthly debt divided by monthly income."""
    if income_monthly <= 0:
        return 1.0
    return round((existing_liabilities + emi) / income_monthly, 3)


# ---- turning raw numbers into LOW / MEDIUM / HIGH bands ----
def band_dti(dti: float) -> str:
    if dti <= RULES["dti_low"]:
        return "LOW"
    if dti <= RULES["dti_medium"]:
        return "MEDIUM"
    return "HIGH"


def band_credit(score: int) -> str:
    if score >= RULES["credit_good"]:
        return "LOW"
    if score >= RULES["credit_fair"]:
        return "MEDIUM"
    return "HIGH"


def band_loan_size(loan_amount: float, income_monthly: float) -> str:
    yearly_income = income_monthly * 12
    if yearly_income <= 0:
        return "HIGH"
    multiple = loan_amount / yearly_income
    if multiple <= RULES["safe_loan_multiple"] * 0.6:
        return "LOW"
    if multiple <= RULES["safe_loan_multiple"]:
        return "MEDIUM"
    return "HIGH"


def band_employment(employment_type: str, years: float) -> str:
    if employment_type == "UNEMPLOYED":
        return "HIGH"
    if employment_type == "SALARIED" and years >= 3:
        return "LOW"
    if years < 1:
        return "HIGH"
    return "MEDIUM"


# ===============================================================
# THE GUARDRAIL  (the decision with NO AI involved)
# ===============================================================
def calculate_risk_score(credit_band: str, dti_band: str, employment_band: str, loan_band: str) -> int:
    """Combine four bands into one number: 0 = very safe, 100 = very risky."""
    score = (
        BAND_POINTS[credit_band] * WEIGHTS["credit"]
        + BAND_POINTS[dti_band] * WEIGHTS["dti"]
        + BAND_POINTS[employment_band] * WEIGHTS["employment"]
        + BAND_POINTS[loan_band] * WEIGHTS["loan_size"]
    )
    return int(round(score))


def rule_based_decision(risk_score: int) -> str:
    """The plain-maths verdict."""
    if risk_score < RULES["approve_below"]:
        return "APPROVED"
    if risk_score > RULES["reject_above"]:
        return "REJECTED"
    return "MANUAL_REVIEW"


def hard_reject_reason(employment_type: str, credit_score: int, dti: float):
    """Instant rejections. Returns a reason, or None if the application is fine."""
    if employment_type == "UNEMPLOYED":
        return "Applicant is currently unemployed"
    if credit_score < RULES["min_credit_score"]:
        return f"Credit score {credit_score} is below the minimum of {RULES['min_credit_score']}"
    if dti > RULES["max_dti"]:
        return f"Debt-to-income ratio {dti} exceeds the maximum of {RULES['max_dti']}"
    return None
