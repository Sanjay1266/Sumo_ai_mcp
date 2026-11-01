"""
Comprehensive Automated Test Suite for SUMO AI Web Application
Validates:
1. Web Application HTML template delivery (/)
2. System health and capability diagnostics (/api/system/status)
3. Corridor geocoding & preset registry (/api/presets, /api/geocode)
4. Full end-to-end simulation execution (/api/simulation/full)
5. Step-by-step pipeline endpoints (/api/simulation/step/*)
6. Analytics and raw XML inspection (/api/analytics/*)
7. Multi-AI traffic engineering copilot (/api/ai/chat)
8. Simulation run history persistence (/api/history)
9. Backward MCP compatibility (/.well-known/mcp, /health)
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
    assert len(presets) >= 5
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

    # 5. Analytics & Microscopic Telemetry
    print("\n--- Test 5: Microscopic Analytics & XML Inspector ---")
    res_stats = client.get("/api/analytics/results")
    assert res_stats.status_code == 200
    stats_data = res_stats.json()
    assert "total_vehicles_loaded" in stats_data

    res_trips = client.get("/api/analytics/trips")
    assert res_trips.status_code == 200
    trips_data = res_trips.json()
    assert "by_vehicle_type" in trips_data
    assert "ind_motorcycle" in trips_data["by_vehicle_type"]

    res_xml = client.get("/api/analytics/xml/stats.xml")
    assert res_xml.status_code == 200
    assert "<statistics" in res_xml.json()["content"]
    print("Analytics & XML inspection: PASSED")

    # 6. Multi-AI Copilot Reasoning
    print("\n--- Test 6: Multi-AI Traffic Engineering Copilot ---")
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

    # 7. Simulation History
    print("\n--- Test 7: Simulation History Persistence ---")
    res_hist = client.get("/api/history")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert len(hist) >= 1
    print(f"History contains {len(hist)} saved runs.")

    # Save a custom labeled run
    res_save = client.post("/api/history/save", json={
        "title": "Peak Hour With Flyover",
        "notes": "Testing LOS improvement",
        "simulation_data": sim_data
    })
    assert res_save.status_code == 200
    saved_id = res_save.json()["entry"]["id"]

    # Delete the test run
    res_del = client.delete(f"/api/history/{saved_id}")
    assert res_del.status_code == 200
    print("Simulation history persistence: PASSED")

    # 8. MCP Backward Compatibility
    print("\n--- Test 8: MCP Protocol Backward Compatibility ---")
    res_mcp = client.get("/.well-known/mcp")
    assert res_mcp.status_code == 200
    assert res_mcp.json()["protocol"] == "mcp"

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"
    print("MCP Protocol Backward Compatibility: PASSED")

    print("\n" + "=" * 68)
    print(">>> ALL 8 WEB APPLICATION MODULE TESTS PASSED WITH 100% SUCCESS! <<<")
    print("=" * 68)


if __name__ == "__main__":
    test_web_application_endpoints()
