#!/bin/bash
# Starts all 4 agents, the gateway, and the UI.
# Press Ctrl+C once to stop everything.

mkdir -p logs

echo "Starting Agent 1 (Profile)..."
python agents/agent1_profile.py    > logs/agent1.log 2>&1 &
echo "Starting Agent 2 (Risk)..."
python agents/agent2_risk.py       > logs/agent2.log 2>&1 &
echo "Starting Agent 3 (Decision)..."
python agents/agent3_decision.py   > logs/agent3.log 2>&1 &
echo "Starting Agent 4 (Compliance)..."
python agents/agent4_compliance.py > logs/agent4.log 2>&1 &

sleep 4
echo "Starting Gateway..."
python gateway/main.py             > logs/gateway.log 2>&1 &

sleep 3
echo ""
echo "Checking health..."
curl -s http://127.0.0.1:8000/health
echo ""
echo "Starting the UI at http://localhost:8501"
echo "Logs are in the logs/ folder."

# Stop everything when you press Ctrl+C
trap 'echo "Stopping..."; kill $(jobs -p) 2>/dev/null; exit' INT TERM

streamlit run ui/app.py
