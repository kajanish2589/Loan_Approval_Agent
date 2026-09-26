@echo off
REM Starts all 4 agents, the gateway, and the UI.
REM Each one opens in its own window so you can read its logs.

echo Starting Agent 1 (Profile)...
start "Agent1-Profile" cmd /k python agents\agent1_profile.py
timeout /t 2 >nul

echo Starting Agent 2 (Risk)...
start "Agent2-Risk" cmd /k python agents\agent2_risk.py
timeout /t 2 >nul

echo Starting Agent 3 (Decision)...
start "Agent3-Decision" cmd /k python agents\agent3_decision.py
timeout /t 2 >nul

echo Starting Agent 4 (Compliance)...
start "Agent4-Compliance" cmd /k python agents\agent4_compliance.py
timeout /t 3 >nul

echo Starting Gateway...
start "Gateway" cmd /k python gateway\main.py
timeout /t 3 >nul

echo Starting the UI...
start "UI" cmd /k streamlit run ui\app.py

echo.
echo All started. Open http://localhost:8501 in your browser.
pause
