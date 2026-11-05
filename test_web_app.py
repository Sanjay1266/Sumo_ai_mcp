"""
Comprehensive Automated Test Suite for SUMO AI Web Application
Validates:
1. Web Application HTML template delivery (/)
2. System health and capability diagnostics (/api/system/status)
3. Corridor geocoding & preset registry (/api/presets, /api/geocode)
4. Full end-to-end simulation execution (/api/simulation/full)
5. Step-by-step pipeline endpoints (/api/simulation/step/*)
6. In-browser 2D Canvas replay telemetry (/api/simulation/replay)
7. Digital twin scenario comparison & interventions (/api/simulation/compare)
8. Environmental emissions & carbon footprint (/api/analytics/emissions)
9. Microscopic trips CSV & audit report export (/api/export/csv, /api/export/report)
10. Analytics and raw XML inspection (/api/analytics/*)
11. Multi-AI traffic engineering copilot (/api/ai/chat)
12. Simulation run history persistence (/api/history)
13. Backward MCP compatibility (/.well-known/mcp, /health)
"""

import os
import sys
import json
from fastapi.testclient import TestClient

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from web_app import app

client = TestClient(app)

def test_web_application_endpoints():
    print("=" * 68)
    print(">>> RUNNING SUMO AI WEB APPLICATION INTEGRATION TESTS <<<")
    print("=" * 68)

    # 1. Root Web App HTML
    print("\n--- Test 1: Web Application Frontend Delivery (GET /) ---")
    res = client.get("/")
    assert res.status_code == 200
    assert "SUMO AI Web Studio" in res.text
    assert "Simulation Parameters" in res.text
    assert "2D Live Replay" in res.text
    assert "Digital Twin Scenarios" in res.text
    print("Root Web Application delivery: PASSED")

    # 2. System Status & Capability Auto-Discovery
    print("\n--- Test 2: System Status Diagnostics (GET /api/system/status) ---")
    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "sumo_engine" in data
    assert "ai_keys" in data
    print(f"SUMO Engine Mode: {data['sumo_engine']['mode']}")
    print("System status diagnostics: PASSED")

    # 3. Presets & Geocoding
    print("\n--- Test 3: Corridor Presets & Geocoding ---")
    res_presets = client.get("/api/presets")
    assert res_presets.status_code == 200
    presets = res_presets.json()
    assert len(presets) >= 8
    print(f"Verified {len(presets)} curated corridor presets.")

    res_geo = client.get("/api/geocode?q=Gandhipuram")
    assert res_geo.status_code == 200
    geo_data = res_geo.json()
    assert "bbox" in geo_data
    assert len(geo_data["bbox"].split(",")) == 4
    print(f"Gandhipuram geocoded to: {geo_data['bbox']}")
    print("Presets & Geocoding: PASSED")

    # 4. Full End-to-End Simulation
    print("\n--- Test 4: Full Microscopic Simulation (POST /api/simulation/full) ---")
    res_sim = client.post("/api/simulation/full", json={
        "bbox": "Ettimadai",
        "trips": 120,
        "duration": 3600,
        "density": "normal",
        "launch_gui": False
    })
    assert res_sim.status_code == 200
    sim_data = res_sim.json()
    assert sim_data["status"] == "success"
    assert "analytics" in sim_data
    assert "trip_details" in sim_data
    assert "los" in sim_data
    print(f"Simulation Status: {sim_data['status']}")
    print(f"Level of Service : {sim_data['los']} ({sim_data.get('los_description')})")
    print(f"Loaded Vehicles  : {sim_data['analytics']['total_vehicles_loaded']}")
    print(f"Average Speed    : {sim_data['trip_details']['average_speed_kmh']} km/h")
    print("Full Simulation: PASSED")

    # 5. In-Browser 2D Replay Data
    print("\n--- Test 5: 2D Simulation Replay Trajectory Telemetry (GET /api/simulation/replay) ---")
    res_rep = client.get("/api/simulation/replay")
    assert res_rep.status_code == 200
    rep_data = res_rep.json()
    assert rep_data["status"] == "success"
    assert len(rep_data["trajectories"]) > 0
    first_veh = rep_data["trajectories"][0]
    assert "vType" in first_veh
    assert "speed_kmh" in first_veh
    print(f"Parsed {len(rep_data['trajectories'])} vehicles for 2D animated canvas replay.")
    print("2D Replay Trajectory Telemetry: PASSED")

    # 6. Digital Twin Scenario Comparison
    print("\n--- Test 6: Digital Twin Scenario Comparison (POST /api/simulation/compare) ---")
    res_cmp = client.post("/api/simulation/compare", json={
        "bbox": "Gandhipuram",
        "intervention": "signal_optimization"
    })
    assert res_cmp.status_code == 200
    cmp_data = res_cmp.json()
    assert cmp_data["status"] == "success"
    assert "baseline" in cmp_data
    assert "proposed" in cmp_data
    assert "deltas" in cmp_data
    print(f"Intervention: {cmp_data['intervention_name']}")
    print(f"Predicted Speed Gain: +{cmp_data['deltas']['speed_change_pct']}%")
    print(f"Delay Reduction     : {cmp_data['deltas']['delay_reduction_pct']}%")
    print("Digital Twin Scenario Comparison: PASSED")

    # 7. Environmental Emissions Analytics
    print("\n--- Test 7: Environmental Emissions & Green Score (GET /api/analytics/emissions) ---")
    res_eco = client.get("/api/analytics/emissions")
    assert res_eco.status_code == 200
    eco_data = res_eco.json()
    assert eco_data["status"] == "success"
    assert "total_co2_kg" in eco_data
    assert "fuel_wasted_liters" in eco_data
    print(f"Total Corridor CO2: {eco_data['total_co2_kg']} kg")
    print(f"Fuel Wasted       : {eco_data['fuel_wasted_liters']} L")
    print(f"Green Mobility    : {eco_data['green_score']}")
    print("Environmental Emissions Analytics: PASSED")

    # 8. CSV Export & Printable Report
    print("\n--- Test 8: Data Export (CSV & Executive Report) ---")
    res_csv = client.get("/api/export/csv")
    assert res_csv.status_code == 200
    assert "Trip_ID,Vehicle_Type" in res_csv.text
    print("CSV Export Generation: PASSED")

    res_rep_html = client.get("/api/export/report")
    assert res_rep_html.status_code == 200
    assert "Urban Traffic Simulation Audit Certificate" in res_rep_html.text
    print("Printable Audit Report Generation: PASSED")

    # 9. Analytics & Microscopic Telemetry
    print("\n--- Test 9: Microscopic Analytics & XML Inspector ---")
    res_stats = client.get("/api/analytics/results")
    assert res_stats.status_code == 200
    stats_data = res_stats.json()
    assert "total_vehicles_loaded" in stats_data

    res_trips = client.get("/api/analytics/trips")
    assert res_trips.status_code == 200
    trips_data = res_trips.json()
    assert "by_vehicle_type" in trips_data

    res_xml = client.get("/api/analytics/xml/stats.xml")
    assert res_xml.status_code == 200
    assert "<statistics" in res_xml.json()["content"]
    print("Analytics & XML inspection: PASSED")

    # 10. Multi-AI Copilot Reasoning
    print("\n--- Test 10: Multi-AI Traffic Engineering Copilot ---")
    res_ai = client.post("/api/ai/chat", json={
        "model": "builtin",
        "prompt": "Evaluate congestion patterns and signal timing for this corridor.",
        "simulation_data": sim_data
    })
    assert res_ai.status_code == 200
    ai_resp = res_ai.json()
    assert "response" in ai_resp
    assert len(ai_resp["response"]) > 50
    print(f"AI Copilot Response Preview: {ai_resp['response'][:100]}...")
    print("Multi-AI Copilot: PASSED")

    # 11. Simulation History
    print("\n--- Test 11: Simulation History Persistence ---")
    res_hist = client.get("/api/history")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert len(hist) >= 1

    res_save = client.post("/api/history/save", json={
        "title": "Peak Hour With Flyover",
        "notes": "Testing LOS improvement",
        "simulation_data": sim_data
    })
    assert res_save.status_code == 200
    saved_id = res_save.json()["entry"]["id"]

    res_del = client.delete(f"/api/history/{saved_id}")
    assert res_del.status_code == 200
    print("Simulation history persistence: PASSED")

    # 12. MCP Backward Compatibility
    print("\n--- Test 12: MCP Protocol Backward Compatibility ---")
    res_mcp = client.get("/.well-known/mcp")
    assert res_mcp.status_code == 200
    assert res_mcp.json()["protocol"] == "mcp"

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"
    print("MCP Protocol Backward Compatibility: PASSED")

    # 13. JSON Telemetry Export
    print("\n--- Test 13: Structured JSON Telemetry Export ---")
    res_json = client.get("/api/export/json")
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    json_data = res_json.json()
    assert "network_stats" in json_data
    assert "trip_analytics" in json_data
    print("JSON Telemetry Export: PASSED")

    # 14. Interactive Adaptive Signal Tuning
    print("\n--- Test 14: Adaptive Traffic Signal Timing Optimizer ---")
    res_tune = client.post("/api/simulation/signals/tune", json={
        "cycle_length_s": 90,
        "green_split_pct": 60,
        "amber_s": 5,
        "pedestrian_scramble": True
    })
    assert res_tune.status_code == 200
    tune_data = res_tune.json()
    assert tune_data["cycle_length_s"] == 90
    assert tune_data["green_phase_s"] == 54
    assert tune_data["throughput_capacity_vph"] > 0
    print(f"Optimal Delay Gain: +{tune_data['speed_gain_pct']}% | Throughput: {tune_data['throughput_capacity_vph']} veh/hr")
    print("Adaptive Signal Timing Optimizer: PASSED")

    print("\n" + "=" * 68)
    print(">>> ALL 14 WEB APPLICATION MODULE TESTS PASSED WITH 100% SUCCESS! <<<")
    print("=" * 68)


if __name__ == "__main__":
    test_web_application_endpoints()
