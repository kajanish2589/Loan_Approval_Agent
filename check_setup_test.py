"""
WHAT IT DOES
  PART 1 - Setup check    (Python, packages, .env, rule engine, model call,etc..)
  PART 2 - Logic tests    (the 6 golden scenarios, no servers, no internet)

  PART 2 only runs if PART 1 passes.

WHICH PROBLEMS STOP THE TESTS?
  BLOCKING  - wrong Python version, missing packages, broken rule engine.
              The tests cannot run without these.
  WARNING   - missing .env, no API key, model call failed.
              The logic tests do not use the model, so by default they still
              run. Use --strict if you want these to stop the tests too.

Exit code: 0 = everything passed, 1 = something failed.
This file is plain ASCII on purpose, so it prints correctly on Windows.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

LINE = "=" * 70

REQUIRED_PACKAGES = ["streamlit", "fastapi", "uvicorn", "langgraph", "fastmcp",
                     "anthropic", "pydantic", "httpx", "requests", "dotenv"]


# ======================================================================
# PART 1 - SETUP CHECK
# Every check returns (passed: bool, blocking: bool)
# ======================================================================

def check_python():
    print("\n1. Python version")
    version = sys.version_info
    print(f"   Found {version.major}.{version.minor}")
    if version >= (3, 10):
        print("   OK")
        return True, True
    print("   PROBLEM  You need Python 3.10 or newer.")
    return False, True


def check_packages():
    print("\n2. Required packages")
    missing = []
    for package in REQUIRED_PACKAGES:
        try:
            __import__(package)
            print(f"   OK       {package}")
        except ImportError:
            print(f"   MISSING  {package}")
            missing.append(package)

    if missing:
        print("\n   Fix with:  pip install -r requirements.txt")
        return False, True
    return True, True


def check_config():
    print("\n3. Configuration")
    env_file = Path(__file__).parent / ".env"

    if not env_file.exists():
        print("   MISSING  .env file")
        print("   Fix with:  copy .env.example .env      (Windows)")
        print("              cp .env.example .env        (Mac/Linux)")
        return False, False

    print("   OK       .env exists")

    try:
        from shared.llm import diagnose
        info = diagnose()
    except Exception as error:
        print(f"   PROBLEM  Could not read the configuration: {error}")
        return False, False

    print(f"   anthropic SDK version: {info['sdk_version']}")
    ok = True

    if not info["sdk_supports_base_url"]:
        print("   PROBLEM  This SDK is too old to talk to OpenRouter.")
        print("            Fix with:  pip install -U anthropic")
        ok = False

    if info["provider"] == "openrouter":
        print("   OK       Using OPENROUTER")
        print(f"            key ends with ...{info['key_tail']}")
        print(f"            endpoint: {info['base_url']}")
        print(f"            model:    {info['model']}")
        if "/" not in info["model"]:
            print("   WARNING  OpenRouter needs a 'vendor/model' name,")
            print("            for example anthropic/claude-haiku-4-5")
    elif info["provider"] == "anthropic":
        print("   OK       Using ANTHROPIC directly")
        print(f"            key ends with ...{info['key_tail']}")
        print(f"            model: {info['model']}")
    else:
        print("   PROBLEM  No API key found. Add ONE of these to .env:")
        print("              OPENROUTER_API_KEY=sk-or-v1-...")
        print("              ANTHROPIC_API_KEY=sk-ant-...")
        ok = False

    print(f"   Mock mode: {info['mock']}")
    return ok, False


def check_rule_engine():
    print("\n4. Rule engine")
    try:
        from shared import rules

        emi = rules.monthly_emi(4000000, 120)
        dti = rules.compute_dti(150000, 8000, emi)
        score = rules.calculate_risk_score("LOW", rules.band_dti(dti), "LOW", "MEDIUM")
        verdict = rules.rule_based_decision(score)

        print(f"   EMI on 40 lakh over 120 months = {emi}")
        print(f"   DTI = {dti} ({rules.band_dti(dti)})")
        print(f"   Risk score = {score} -> {verdict}")
        print("   OK")
        return True, True
    except Exception as error:
        print(f"   PROBLEM  {error}")
        return False, True


def check_model():
    print("\n5. Model connection")
    try:
        from shared.llm import MODEL, USE_MOCK, ask_claude
    except Exception as error:
        print(f"   PROBLEM  {error}")
        return False, False

    if USE_MOCK:
        print("   Running in MOCK mode - the model will not be called.")
        print("   Set USE_MOCK=false in .env to use the real model.")
        return True, False

    try:
        answer, used = ask_claude(
            system_prompt='Reply with raw JSON only: {"status": "ok"}',
            user_prompt="Say ok.",
            fallback={"status": "fallback"},
        )
    except Exception as error:
        print(f"   PROBLEM  {error}")
        return False, False

    if used:
        print(f"   OK       Model responded. Using {MODEL}")
        print(f"            reply: {answer}")
        return True, False

    print("   PROBLEM  The call failed and fell back. See the error above.")
    print("            Common causes and fixes:")
    print("              'unexpected keyword argument'  -> pip install -U anthropic")
    print("              'model not found'              -> use anthropic/claude-haiku-4-5")
    print("              '401' or '403'                 -> bad or rotated API key")
    print("              '402'                          -> no credit on OpenRouter")
    print("              'connection'                   -> END_POINT should be")
    print("                                                https://openrouter.ai/api")
    return False, False


def run_setup_check(strict: bool) -> bool:
    """Run every setup check. Returns True if it is safe to run the tests."""
    print(LINE)
    print("PART 1 - SETUP CHECK")
    print(LINE)

    results = {
        "Python version": check_python(),
        "Packages": check_packages(),
        "Configuration": check_config(),
        "Rule engine": check_rule_engine(),
        "Model connection": check_model(),
    }

    print("\n" + "-" * 70)
    print("SETUP SUMMARY")
    blocking_failures = []
    warnings = []

    for name, (passed, blocking) in results.items():
        if passed:
            status = "OK"
        elif blocking or strict:
            status = "FAIL"
            blocking_failures.append(name)
        else:
            status = "WARNING"
            warnings.append(name)
        print(f"   {status:<8} {name}")

    if blocking_failures:
        print(f"\nSetup FAILED: {', '.join(blocking_failures)}")
        print("Fix the problems above, then run this file again.")
        print("The logic tests were NOT run.")
        return False

    if warnings:
        print(f"\nSetup passed with warnings: {', '.join(warnings)}")
        print("The logic tests do not need the model, so they will still run.")
        print("The full system will not work with Claude until these are fixed.")
    else:
        print("\nSetup PASSED.")

    return True


# ======================================================================
# PART 2 - LOGIC TESTS  (the 6 golden scenarios)
# ======================================================================

SCENARIOS = [
    ("1. Strong salaried applicant", "APPROVED", dict(
        applicant_id="APP001", age=38, income_monthly=150000, employment_type="SALARIED",
        employment_years=12, credit_score=790, loan_amount=4000000, tenure_months=120,
        existing_liabilities_monthly=8000, location="Chennai")),

    ("2. Unemployed, poor credit", "REJECTED", dict(
        applicant_id="APP002", age=29, income_monthly=40000, employment_type="UNEMPLOYED",
        employment_years=0, credit_score=540, loan_amount=3000000, tenure_months=60,
        existing_liabilities_monthly=20000, location="Mumbai")),

    ("3. Contract worker, fair credit", "MANUAL_REVIEW", dict(
        applicant_id="APP003", age=34, income_monthly=75000, employment_type="CONTRACT",
        employment_years=3, credit_score=620, loan_amount=2500000, tenure_months=144,
        existing_liabilities_monthly=4000, location="Chennai")),

    ("4. Large loan, average credit", "MANUAL_REVIEW", dict(
        applicant_id="APP004", age=41, income_monthly=100000, employment_type="SALARIED",
        employment_years=6, credit_score=660, loan_amount=5000000, tenure_months=180,
        existing_liabilities_monthly=5000, location="Mumbai")),

    ("5. Over-leveraged already", "REJECTED", dict(
        applicant_id="APP005", age=45, income_monthly=60000, employment_type="SELF_EMPLOYED",
        employment_years=8, credit_score=610, loan_amount=2000000, tenure_months=60,
        existing_liabilities_monthly=32000, location="Mumbai")),

    ("6. New to bank, short tenure job", "MANUAL_REVIEW", dict(
        applicant_id="APP005", age=26, income_monthly=85000, employment_type="SALARIED",
        employment_years=0.5, credit_score=700, loan_amount=2600000, tenure_months=144,
        existing_liabilities_monthly=6000, location="Chennai")),
]


def evaluate(application):
    """Run the same maths the agents run, without any servers."""
    from shared import rules

    emi = rules.monthly_emi(application.loan_amount, application.tenure_months)
    dti = rules.compute_dti(application.income_monthly,
                            application.existing_liabilities_monthly, emi)

    hard = rules.hard_reject_reason(application.employment_type,
                                    application.credit_score, dti)
    if hard:
        return "REJECTED", 95, dti, emi, f"hard reject: {hard}"

    credit_band = rules.band_credit(application.credit_score)
    dti_band = rules.band_dti(dti)
    employment_band = rules.band_employment(application.employment_type,
                                            application.employment_years)
    loan_band = rules.band_loan_size(application.loan_amount, application.income_monthly)

    score = rules.calculate_risk_score(credit_band, dti_band, employment_band, loan_band)
    verdict = rules.rule_based_decision(score)
    bands = f"credit={credit_band} dti={dti_band} emp={employment_band} size={loan_band}"
    return verdict, score, dti, emi, bands


def run_logic_tests() -> bool:
    """Run the 6 golden scenarios and the schema check. Returns True if all pass."""
    from shared.schemas import DecisionResult, LoanApplication, ProfileResult, RiskResult

    print("\n" + LINE)
    print("PART 2 - DECISION LOGIC TEST (6 golden scenarios)")
    print(LINE)

    passed = 0
    for name, expected, data in SCENARIOS:
        try:
            application = LoanApplication(**data)
            verdict, score, dti, emi, detail = evaluate(application)
        except Exception as error:
            print(f"\nERROR {name}")
            print(f"      {error}")
            continue

        ok = verdict == expected
        passed += ok
        print(f"\n{'PASS' if ok else 'FAIL'}  {name}")
        print(f"      expected {expected}, got {verdict}")
        print(f"      EMI {emi:,.0f}  DTI {dti}  risk score {score}")
        print(f"      {detail}")

    print("\nSchema check:")
    schemas_ok = True
    try:
        DecisionResult(classification="APPROVED", risk_score=20, confidence=0.9,
                       key_factors=["test"], explanation="test")
        ProfileResult(income_stability_score=80, employment_risk="LOW",
                      credit_history_summary="test", reasoning="test")
        RiskResult(dti_ratio=0.3, monthly_emi=1000, credit_score_risk_level="LOW",
                   loan_amount_risk="LOW", reasoning="test")
        print("   OK - all schemas valid")
    except Exception as error:
        print(f"   FAIL - {error}")
        schemas_ok = False

    print("\n" + "-" * 70)
    print(f"RESULT: {passed} of {len(SCENARIOS)} scenarios passed")
    return passed == len(SCENARIOS) and schemas_ok


# ======================================================================
# MAIN
# ======================================================================

def main() -> int:
    strict = "--strict" in sys.argv

    if not run_setup_check(strict):
        print("\n" + LINE)
        print("FINAL: SETUP FAILED - tests skipped")
        print(LINE)
        return 1

    tests_ok = run_logic_tests()

    print("\n" + LINE)
    if tests_ok:
        print("FINAL: ALL CHECKS PASSED")
        print("Start the system with:")
        print("   Windows:   run_all.bat")
        print("   Mac/Linux: bash run_all.sh")
    else:
        print("FINAL: SOME LOGIC TESTS FAILED")
        print("If you changed a threshold in shared/rules.py, that is expected -")
        print("check the scenarios above to see which verdicts moved.")
    print(LINE)
    return 0 if tests_ok else 1


if __name__ == "__main__":
    sys.exit(main())
