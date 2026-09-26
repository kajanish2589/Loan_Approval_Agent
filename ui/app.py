"""
ui/app.py
---------
THE CHATBOT UI - built with Streamlit. (runs on port 8501)

Start it with:   streamlit run ui/app.py

THREE WAYS TO FILL THE FORM
  1. Chat       - one question at a time
  2. Quick form - every field on one screen
  3. Paste JSON - paste a whole application at once
"""

import json

import requests
import streamlit as st

GATEWAY = "http://127.0.0.1:8000"

EMPLOYMENT_OPTIONS = ["SALARIED", "SELF_EMPLOYED", "CONTRACT", "UNEMPLOYED"]

# field, question shown to the user, type, example value
QUESTIONS = [
    ("applicant_id", "What is your applicant ID?", "text", "APP001"),
    ("age", "How old are you?", "int", "38"),
    ("income_monthly", "What is your monthly income?", "float", "150000"),
    ("employment_type", "What is your employment type?", "choice", "SALARIED"),
    ("employment_years", "How many years in your current job?", "float", "12"),
    ("credit_score", "What is your credit score? (300 to 900)", "int", "790"),
    ("loan_amount", "How much would you like to borrow?", "float", "4000000"),
    ("tenure_months", "Over how many months? (6 to 360)", "int", "120"),
    ("existing_liabilities_monthly", "What do your current EMIs add up to per month?", "float", "8000"),
    ("location", "Which city are you in?", "text", "Chennai"),
]

SAMPLES = {
    "Strong applicant": {
        "applicant_id": "APP001", "age": 38, "income_monthly": 150000,
        "employment_type": "SALARIED", "employment_years": 12, "credit_score": 790,
        "loan_amount": 4000000, "tenure_months": 120,
        "existing_liabilities_monthly": 8000, "location": "Chennai",
    },
    "Weak applicant": {
        "applicant_id": "APP002", "age": 29, "income_monthly": 40000,
        "employment_type": "UNEMPLOYED", "employment_years": 0, "credit_score": 540,
        "loan_amount": 3000000, "tenure_months": 60,
        "existing_liabilities_monthly": 20000, "location": "Mumbai",
    },
    "Borderline applicant": {
        "applicant_id": "APP003", "age": 34, "income_monthly": 75000,
        "employment_type": "CONTRACT", "employment_years": 3, "credit_score": 620,
        "loan_amount": 2500000, "tenure_months": 144,
        "existing_liabilities_monthly": 4000, "location": "Chennai",
    },
    "Large loan, thin credit": {
        "applicant_id": "APP004", "age": 41, "income_monthly": 100000,
        "employment_type": "SALARIED", "employment_years": 6, "credit_score": 660,
        "loan_amount": 5000000, "tenure_months": 180,
        "existing_liabilities_monthly": 5000, "location": "Mumbai",
    },
}

# Plain text badges instead of emoji
VERDICT_STYLE = {
    "APPROVED": ("[ APPROVED ]", "success"),
    "REJECTED": ("[ REJECTED ]", "error"),
    "MANUAL_REVIEW": ("[ MANUAL REVIEW ]", "warning"),
}

st.set_page_config(page_title="Loan Approval Assistant", layout="wide")


# ===============================================================
# HELPERS
# ===============================================================
def clean_number(raw, want_int: bool):
    """
    Turn whatever was typed or pasted into a number.

    People paste things like "1,50,000" or " 45000 " or "Rs 40000".
    We strip all of that instead of rejecting it.
    """
    if raw is None:
        return None

    text = str(raw).strip()
    if not text:
        return None

    text = "".join(ch for ch in text if ch in "0123456789.-")

    if not text or text in {"-", ".", "-."}:
        return None

    try:
        return int(float(text)) if want_int else float(text)
    except ValueError:
        return None


def build_application(raw_values: dict):
    """Convert the raw text answers into the payload the API expects."""
    payload = {}
    problems = []

    for field, _question, kind, _example in QUESTIONS:
        raw = raw_values.get(field)

        if kind in ("text", "choice"):
            value = str(raw).strip() if raw is not None else ""
            if not value:
                problems.append(f"{field} is empty")
            payload[field] = value
        else:
            value = clean_number(raw, want_int=(kind == "int"))
            if value is None:
                problems.append(f"{field} is not a valid number (you typed: {raw!r})")
            payload[field] = value

    return payload, problems


def affordability_warning(payload: dict):
    """
    A friendly heads-up BEFORE submitting.

    A very common confusion is entering a loan that is far too large for
    the income, which always comes back REJECTED because the debt-to-income
    ratio breaks the hard limit. This explains why, up front.
    """
    income = payload.get("income_monthly")
    loan = payload.get("loan_amount")
    tenure = payload.get("tenure_months")

    if not all(isinstance(v, (int, float)) and v for v in (income, loan, tenure)):
        return None

    rate = 0.10 / 12
    emi = loan * rate * (1 + rate) ** tenure / ((1 + rate) ** tenure - 1)
    liabilities = payload.get("existing_liabilities_monthly") or 0
    dti = (emi + liabilities) / income

    if dti > 0.65:
        return (
            f"Heads up: this loan works out to about {emi:,.0f} per month. "
            f"With your existing EMIs that is {dti * 100:.0f} percent of your income. "
            f"Anything above 65 percent is rejected automatically. "
            f"Try a smaller loan or a longer tenure."
        )
    return None


def submit(payload: dict):
    """Send the application to the gateway."""
    with st.spinner("The agents are reviewing your application..."):
        try:
            reply = requests.post(f"{GATEWAY}/api/v1/loan/apply", json=payload, timeout=180)
        except Exception as error:
            st.error(f"Could not reach the gateway at {GATEWAY}: {error}")
            st.caption("Start it with: python gateway/main.py")
            return

    if reply.status_code == 200:
        st.session_state.result = reply.json()
        st.rerun()
    elif reply.status_code == 422:
        st.error("The application was rejected by validation:")
        try:
            for item in reply.json().get("detail", []):
                where = " -> ".join(str(p) for p in item.get("loc", [])[1:])
                st.write(f"- **{where}**: {item.get('msg')}")
        except Exception:
            st.code(reply.text)
    else:
        st.error(f"Error {reply.status_code}")
        st.code(reply.text)


def load_sample(data: dict):
    """Fill every answer box from a sample, as text so it stays editable."""
    st.session_state.answers = {k: str(v) for k, v in data.items()}
    st.session_state.step = len(QUESTIONS)
    st.session_state.result = None


# ===============================================================
# SESSION MEMORY
# ===============================================================
st.session_state.setdefault("step", 0)
st.session_state.setdefault("answers", {})
st.session_state.setdefault("result", None)


# ===============================================================
# SIDEBAR
# ===============================================================
with st.sidebar:
    st.header("System status")

    try:
        health = requests.get(f"{GATEWAY}/health", timeout=5).json()
        if health.get("ready"):
            st.success("All 4 agents are running")
        else:
            st.error("Some agents are not running")

        for agent, status in health.get("agents", {}).items():
            if status == "up":
                st.write(f"UP    - {agent}")
            else:
                st.write(f"DOWN  - {agent}")
    except Exception:
        st.error("Gateway is not reachable")
        st.caption("Start it with: python gateway/main.py")

    st.divider()

    if st.button("Start a new application", use_container_width=True):
        st.session_state.step = 0
        st.session_state.answers = {}
        st.session_state.result = None
        st.rerun()

    st.divider()
    st.subheader("Load a sample")
    for label, data in SAMPLES.items():
        if st.button(label, use_container_width=True):
            load_sample(data)
            st.rerun()


# ===============================================================
# MAIN
# ===============================================================
st.title("Loan Approval Assistant")
st.caption("Powered by 4 AI agents working together")

# ---------------------------------------------------------------
# RESULT VIEW
# ---------------------------------------------------------------
if st.session_state.result is not None:
    result = st.session_state.result
    decision = result.get("decision") or {}
    verdict = decision.get("classification", "UNKNOWN")

    badge, style = VERDICT_STYLE.get(verdict, ("[ UNKNOWN ]", "info"))
    getattr(st, style)(f"### {badge}")
    st.caption(f"Case ID: {result.get('case_id')}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Risk score", f"{decision.get('risk_score', 0)}/100")
    col2.metric("Confidence", f"{decision.get('confidence', 0) * 100:.0f}%")

    dti_value = (result.get("risk") or {}).get("dti_ratio")
    col3.metric("Debt-to-income", dti_value if dti_value is not None else "-")

    # Explain a very high DTI in plain language
    if isinstance(dti_value, (int, float)) and dti_value > 1:
        st.warning(
            f"A debt-to-income ratio of {dti_value} means the monthly repayment "
            f"is about {dti_value * 100:.0f} percent of the stated income - far "
            f"more than the applicant earns. The loan amount is too large for "
            f"this income, or the tenure is too short."
        )

    st.subheader("Why")
    st.info(decision.get("explanation", "No explanation available"))

    st.subheader("Key factors")
    for factor in decision.get("key_factors", []):
        st.write(f"- {factor}")

    st.divider()
    st.subheader("What each agent found")

    profile = result.get("profile")
    if profile:
        with st.expander("Agent 1 - Applicant Profile"):
            c1, c2 = st.columns(2)
            c1.metric("Income stability", f"{profile['income_stability_score']}/100")
            c2.metric("Employment risk", profile["employment_risk"])
            st.write(f"**Credit history:** {profile['credit_history_summary']}")
            st.write(f"**Reasoning:** {profile['reasoning']}")
            if profile.get("completeness_flags"):
                st.warning("Flags: " + ", ".join(profile["completeness_flags"]))

    risk = result.get("risk")
    if risk:
        with st.expander("Agent 2 - Financial Risk"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Monthly EMI", f"{risk['monthly_emi']:,.0f}")
            c2.metric("Credit risk", risk["credit_score_risk_level"])
            c3.metric("Loan size risk", risk["loan_amount_risk"])
            st.write(f"**Reasoning:** {risk['reasoning']}")
            if risk.get("anomalies"):
                st.warning("Anomalies: " + ", ".join(risk["anomalies"]))

    with st.expander("Agent 3 - Loan Decision"):
        st.write(f"**Verdict:** {verdict}")
        st.write(f"**Risk score:** {decision.get('risk_score')}/100")
        st.write(f"**Explanation:** {decision.get('explanation')}")

    compliance = result.get("compliance")
    if compliance:
        with st.expander("Agent 4 - Compliance and Action"):
            st.write(f"**Action taken:** {compliance['action_taken']}")
            st.write(f"**Notification sent:** {compliance['notification_sent']}")
            st.write(f"**Summary:** {compliance['summary']}")

    st.divider()
    with st.expander("Workflow trace (the order things happened)"):
        for line in result.get("trace", []):
            st.text(f"- {line}")

    with st.expander("Agent telemetry (which MCP tools were called)"):
        for item in result.get("telemetry", []):
            st.write(f"**{item['agent_name']}** - {item['latency_ms']} ms")
            st.caption(f"MCP tools: {', '.join(item['mcp_tools_called']) or 'none'}")
            st.caption(f"Model used: {item['llm_used']} | Note: {item['note']}")

    with st.expander("Raw JSON"):
        st.code(json.dumps(result, indent=2), language="json")

    if result.get("errors"):
        st.error("Errors: " + "; ".join(result["errors"]))

    if st.button("Submit another application", type="primary"):
        st.session_state.step = 0
        st.session_state.answers = {}
        st.session_state.result = None
        st.rerun()

# ---------------------------------------------------------------
# INPUT VIEW - three tabs
# ---------------------------------------------------------------
else:
    tab_chat, tab_form, tab_json = st.tabs(["Chat", "Quick form", "Paste JSON"])
    answers = st.session_state.answers

    # ---- TAB 1: one question at a time ----
    with tab_chat:
        step = st.session_state.step

        if step < len(QUESTIONS):
            st.progress(step / len(QUESTIONS), text=f"Question {step + 1} of {len(QUESTIONS)}")
            field, question, kind, example = QUESTIONS[step]

            with st.chat_message("assistant"):
                st.write(question)

            with st.form(key=f"chat_form_{step}", clear_on_submit=False):
                if kind == "choice":
                    current = answers.get(field, example)
                    index = EMPLOYMENT_OPTIONS.index(current) if current in EMPLOYMENT_OPTIONS else 0
                    value = st.selectbox("Choose one", EMPLOYMENT_OPTIONS,
                                         index=index, label_visibility="collapsed")
                else:
                    value = st.text_input(
                        "Your answer",
                        value=answers.get(field, ""),
                        placeholder=f"for example: {example}",
                        label_visibility="collapsed",
                    )

                col_a, col_b = st.columns(2)
                go_next = col_a.form_submit_button("Next", type="primary", use_container_width=True)
                go_back = col_b.form_submit_button("Back", use_container_width=True,
                                                   disabled=(step == 0))

                if go_next:
                    text = str(value).strip()
                    if not text:
                        st.warning("Please type an answer.")
                    elif kind in ("int", "float") and clean_number(text, kind == "int") is None:
                        st.warning(f"That is not a number. Try something like {example}.")
                    else:
                        answers[field] = text
                        st.session_state.step += 1
                        st.rerun()

                if go_back:
                    st.session_state.step = max(0, step - 1)
                    st.rerun()

            if answers:
                with st.expander("Your answers so far"):
                    st.json(answers)

        else:
            st.success("All questions answered.")
            payload, problems = build_application(answers)
            st.json(payload)

            if problems:
                for problem in problems:
                    st.error(problem)
                st.caption("Fix these in the Quick form tab.")
            else:
                warning = affordability_warning(payload)
                if warning:
                    st.warning(warning)
                if st.button("Submit application", type="primary", use_container_width=True):
                    submit(payload)

    # ---- TAB 2: everything on one screen ----
    with tab_form:
        st.caption("Fill or paste every field here, then submit. Tab moves between boxes.")

        with st.form("quick_form"):
            columns = st.columns(2)
            typed = {}

            for index, (field, question, kind, example) in enumerate(QUESTIONS):
                target = columns[index % 2]
                label = field.replace("_", " ").capitalize()

                if kind == "choice":
                    current = answers.get(field, example)
                    position = EMPLOYMENT_OPTIONS.index(current) if current in EMPLOYMENT_OPTIONS else 0
                    typed[field] = target.selectbox(label, EMPLOYMENT_OPTIONS,
                                                    index=position, key=f"qf_{field}")
                else:
                    typed[field] = target.text_input(
                        label,
                        value=answers.get(field, ""),
                        placeholder=str(example),
                        key=f"qf_{field}",
                    )

            if st.form_submit_button("Submit application", type="primary", use_container_width=True):
                st.session_state.answers = {k: str(v) for k, v in typed.items()}
                payload, problems = build_application(typed)

                if problems:
                    for problem in problems:
                        st.error(problem)
                else:
                    warning = affordability_warning(payload)
                    if warning:
                        st.warning(warning)
                    submit(payload)

    # ---- TAB 3: paste a whole application ----
    with tab_json:
        st.caption("Paste a complete application as JSON. Useful for repeating a test quickly.")

        example_json = json.dumps(SAMPLES["Strong applicant"], indent=2)
        pasted = st.text_area("Application JSON", value=example_json, height=320)

        if st.button("Submit this JSON", type="primary", use_container_width=True):
            try:
                payload = json.loads(pasted)
            except json.JSONDecodeError as error:
                st.error(f"That is not valid JSON: {error}")
            else:
                for field, _q, kind, _e in QUESTIONS:
                    if kind in ("int", "float") and field in payload:
                        payload[field] = clean_number(payload[field], kind == "int")

                st.session_state.answers = {k: str(v) for k, v in payload.items()}
                submit(payload)
