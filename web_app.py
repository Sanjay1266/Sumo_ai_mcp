"""
SUMO AI Web Application – High-Performance Traffic Simulation & Multi-AI Analytics Platform
Converts the SUMO AI MCP server into a full-featured, production-ready Web Application.
"""

import os
import sys
import json
import time
import shutil
import urllib.parse
import urllib.request
import webbrowser
import asyncio
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Form, HTTPException, Depends, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import security_utils
import sumo_server
import ai_router

# =============================================================================
# FASTAPI APP INITIALIZATION & CORS
# =============================================================================

app = FastAPI(
    title="SUMO AI Web Application",
    description="Interactive Urban Traffic Simulation, Microscopic Telemetry & Multi-AI Engineering Platform",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# =============================================================================
# IN-MEMORY HISTORY & SIMULATION EVENT QUEUE
# =============================================================================

SIMULATION_HISTORY: List[Dict[str, Any]] = []
SIMULATION_EVENT_SUBSCRIBERS: List[asyncio.Queue] = []

async def broadcast_event(event_type: str, data: Dict[str, Any]):
    """Broadcasts a live simulation status event to all connected SSE clients."""
    message = json.dumps({"type": event_type, "timestamp": time.time(), "data": data})
    for queue in list(SIMULATION_EVENT_SUBSCRIBERS):
        try:
            await queue.put(message)
        except Exception:
            if queue in SIMULATION_EVENT_SUBSCRIBERS:
                SIMULATION_EVENT_SUBSCRIBERS.remove(queue)

# Pre-load initial sample run into history from existing XML files
try:
    if os.path.exists("stats.xml") and os.path.exists("tripinfo.xml"):
        initial_stats = sumo_server.analyze_results()
        initial_trips = sumo_server.analyze_trip_details()
        if "error" not in initial_stats:
            SIMULATION_HISTORY.append({
                "id": "run_initial_001",
                "timestamp": time.time(),
                "formatted_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "location": "Gandhipuram, Coimbatore",
                "bbox": "76.9550,10.9950,76.9800,11.0200",
                "trips": initial_stats.get("total_vehicles_loaded", 100),
                "duration": 3600,
                "density": "normal",
                "speed_kmh": initial_trips.get("average_speed_kmh", 29.5),
                "time_loss_s": initial_trips.get("average_time_loss_s", 67.4),
                "congestion_index": initial_trips.get("congestion_index", 0.28),
                "los": "LOS C",
                "analytics": initial_stats,
                "trip_details": initial_trips
            })
except Exception:
    pass

# =============================================================================
# PRESET CORRIDORS REGISTRY
# =============================================================================

PRESET_CORRIDORS = [
    {
        "id": "gandhipuram",
        "name": "Gandhipuram Cross Cut Road",
        "city": "Coimbatore, Tamil Nadu",
        "bbox": "76.9550,10.9950,76.9800,11.0200",
        "center": [11.0075, 76.9675],
        "zoom": 15,
        "description": "Dense commercial arterial corridor with high motorcycle & auto-rickshaw density.",
        "icon": "🏙️"
    },
    {
        "id": "chennai_central",
        "name": "Chennai Central & Poonamallee High Rd",
        "city": "Chennai, Tamil Nadu",
        "bbox": "80.2600,13.0650,80.2850,13.0900",
        "center": [13.0775, 80.2725],
        "zoom": 15,
        "description": "Multi-modal transit hub connecting suburban rail, metro, buses, and freight.",
        "icon": "🚆"
    },
    {
        "id": "ettimadai",
        "name": "Ettimadai – Amrita Vishwa Vidyapeetham",
        "city": "Coimbatore, Tamil Nadu",
        "bbox": "76.8900,10.8950,76.9150,10.9150",
        "center": [10.9050, 76.9025],
        "zoom": 15,
        "description": "Suburban university campus peripheral network with mixed local & student traffic.",
        "icon": "🎓"
    },
    {
        "id": "silk_board",
        "name": "Silk Board Junction & Hosur Road",
        "city": "Bangalore, Karnataka",
        "bbox": "77.6150,12.9100,77.6350,12.9300",
        "center": [12.9200, 77.6250],
        "zoom": 15,
        "description": "Notorious IT corridor bottleneck with intense peak-hour congestion.",
        "icon": "🚦"
    },
    {
        "id": "connaught_place",
        "name": "Connaught Place Radial Corridors",
        "city": "New Delhi",
        "bbox": "77.2100,28.6250,77.2300,28.6450",
        "center": [28.6350, 77.2200],
        "zoom": 15,
        "description": "Colcentric geometric circular hub with multiple radial arterial avenues.",
        "icon": "🏛️"
    },
    {
        "id": "bkc_mumbai",
        "name": "Bandra-Kurla Complex (BKC)",
        "city": "Mumbai, Maharashtra",
        "bbox": "72.8550,19.0550,72.8750,19.0750",
        "center": [19.0650, 72.8650],
        "zoom": 15,
        "description": "Modern financial central business district with planned boulevard grids.",
        "icon": "💼"
    },
    {
        "id": "hitec_city",
        "name": "Hitec City & Cyber Towers",
        "city": "Hyderabad, Telangana",
        "bbox": "78.3750,17.4450,78.3950,17.4650",
        "center": [17.4550, 78.3850],
        "zoom": 15,
        "description": "Rapidly growing tech corridor featuring flyovers, underpasses, and metro piers.",
        "icon": "⚡"
    },
    {
        "id": "peelamedu",
        "name": "Peelamedu – Avinashi Road",
        "city": "Coimbatore, Tamil Nadu",
        "bbox": "76.9950,11.0150,77.0200,11.0400",
        "center": [11.0275, 77.0075],
        "zoom": 15,
        "description": "Primary eastern arterial corridor home to airport access, colleges, and IT parks.",
        "icon": "✈️"
    }
]

# Supported AI Model Registry
SUPPORTED_AI_MODELS = [
    {
        "id": "builtin",
        "name": "Built-in Traffic Engineering Expert",
        "provider": "SUMO AI Native",
        "icon": "🧠",
        "description": "Completely offline, rule-based traffic engineering agent powered by Highway Capacity Manual standards.",
        "requires_key": False
    },
    {
        "id": "gemini",
        "name": "Google Gemini 1.5 / 2.0 Flash",
        "provider": "Google Cloud",
        "icon": "🔵",
        "description": "High-speed multi-modal LLM with deep urban mobility reasoning capabilities.",
        "requires_key": True
    },
    {
        "id": "claude",
        "name": "Anthropic Claude 3.5 Sonnet",
        "provider": "Anthropic",
        "icon": "🟣",
        "description": "State-of-the-art analytical intelligence for geometric road layout and signal design.",
        "requires_key": True
    },
    {
        "id": "gpt4",
        "name": "OpenAI GPT-4o",
        "provider": "OpenAI",
        "icon": "🟢",
        "description": "Advanced general reasoning agent for holistic urban transport planning.",
        "requires_key": True
    },
    {
        "id": "ollama",
        "name": "Ollama Local LLM (Llama 3 / DeepSeek)",
        "provider": "Local Host",
        "icon": "🦙",
        "description": "100% private and on-device offline LLM inference via local Ollama daemon.",
        "requires_key": False
    }
]

# Request / Response Schemas
class SimulationParameters(BaseModel):
    bbox: str = Field(default="Gandhipuram", description="Place name, corridor preset, or bounding box coordinates")
    trips: Optional[int] = Field(default=600, ge=1, le=5000)
    duration: Optional[int] = Field(default=3600, ge=10, le=86400)
    density: Optional[str] = Field(default="normal")
    vehicle_mix: Optional[Dict[str, float]] = None
    launch_gui: Optional[bool] = Field(default=False)

class StepNetworkRequest(BaseModel):
    bbox: str

class StepRoutesRequest(BaseModel):
    trips: Optional[int] = 600
    duration: Optional[int] = 3600
    density: Optional[str] = "normal"
    vehicle_mix: Optional[Dict[str, float]] = None

class StepGuiRequest(BaseModel):
    auto_start: Optional[bool] = True
    delay: Optional[int] = 150

class AiChatPayload(BaseModel):
    model: Optional[str] = "builtin"
    prompt: str
    simulation_data: Optional[Dict[str, Any]] = None
    api_key: Optional[str] = None

class SaveRunPayload(BaseModel):
    title: Optional[str] = ""
    notes: Optional[str] = ""
    simulation_data: Dict[str, Any]

# =============================================================================
# WEB APPLICATION ROOT & CORE ENDPOINTS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_web_application():
    """Serves the primary Single-Page SUMO AI Web Application."""
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>SUMO AI Web Application</h1><p>Template loading...</p>")


@app.get("/api/system/status")
async def get_system_status():
    """Returns system runtime diagnostics, binary paths, and environment configuration."""
    sumo_home = os.environ.get("SUMO_HOME", "")
    sumo_bin = sumo_server.find_sumo_binary("sumo")
    sumo_gui_bin = sumo_server.find_sumo_binary("sumo-gui")
    netconvert_bin = sumo_server.find_sumo_binary("netconvert")
    python_bin = sumo_server.get_python_executable()

    sumo_found = bool(shutil.which(sumo_bin) or os.path.exists(sumo_bin))
    sumo_gui_found = bool(shutil.which(sumo_gui_bin) or os.path.exists(sumo_gui_bin))
    netconvert_found = bool(shutil.which(netconvert_bin) or os.path.exists(netconvert_bin))

    return {
        "status": "healthy",
        "mode": "standalone_web_application",
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "python_bin": python_bin,
        "sumo_engine": {
            "available": sumo_found,
            "mode": "Native Eclipse SUMO" if sumo_found else "High-Fidelity Synthetic Simulation Engine",
            "binary": sumo_bin,
            "sumo_home": sumo_home
        },
        "sumo_gui": {
            "available": sumo_gui_found,
            "binary": sumo_gui_bin
        },
        "netconvert": {
            "available": netconvert_found,
            "binary": netconvert_bin
        },
        "ai_keys": {
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "ollama": True,
            "builtin": True
        }
    }


@app.get("/api/presets")
async def list_presets():
    """Returns the list of curated urban traffic corridor presets."""
    return PRESET_CORRIDORS


@app.get("/api/geocode")
async def geocode_location(q: str = Query(..., description="Location or area name to resolve")):
    """
    Resolves any place name to coordinates and a clamped SUMO bounding box.
    Returns center latitude/longitude, bounding box string, and display metadata.
    """
    safe_query = security_utils.sanitize_location_query(q)
    bbox_str = sumo_server.resolve_location_to_bbox(safe_query)
    parts = [float(x) for x in bbox_str.split(",")]

    center_lon = (parts[0] + parts[2]) / 2.0
    center_lat = (parts[1] + parts[3]) / 2.0

    return {
        "query": safe_query,
        "bbox": bbox_str,
        "min_lon": parts[0],
        "min_lat": parts[1],
        "max_lon": parts[2],
        "max_lat": parts[3],
        "center": [center_lat, center_lon],
        "display_name": f"{safe_query.title()} Corridor"
    }


# =============================================================================
# SIMULATION EXECUTION API (FULL & STEP-BY-STEP)
# =============================================================================

@app.post("/api/simulation/full")
async def run_full_simulation_api(params: SimulationParameters):
    """
    Executes the entire microscopic simulation pipeline end-to-end:
    Geocoding -> OSM Network -> Indian Mixed Routes -> SUMO Physics -> Microscopic Analytics.
    """
    safe_bbox = security_utils.sanitize_location_query(params.bbox)
    safe_trips, safe_duration, safe_density = security_utils.clamp_simulation_parameters(
        trips=params.trips or 600,
        duration=params.duration or 3600,
        density=params.density
    )

    await broadcast_event("step_start", {"step": "geocoding", "message": f"Resolving corridor '{safe_bbox}'..."})
    time.sleep(0.1)

    result = sumo_server.run_full_simulation(
        bbox=safe_bbox,
        trips=safe_trips,
        duration=safe_duration,
        density=safe_density,
        launch_gui=params.launch_gui or False
    )

    # Compute Level of Service (LOS)
    delay = 0.0
    speed = 0.0
    cong = 0.0
    if result.get("trip_details") and not result["trip_details"].get("error"):
        delay = result["trip_details"].get("average_time_loss_s", 0.0)
        speed = result["trip_details"].get("average_speed_kmh", 0.0)
        cong = result["trip_details"].get("congestion_index", 0.0)

    los_letter = "B"
    los_desc = "Stable Flow"
    if delay < 10:
        los_letter, los_desc = "A", "Free Flow"
    elif delay < 20:
        los_letter, los_desc = "B", "Stable Flow"
    elif delay < 35:
        los_letter, los_desc = "C", "Fair Flow"
    elif delay < 55:
        los_letter, los_desc = "D", "Dense Flow"
    elif delay < 80:
        los_letter, los_desc = "E", "Unstable Flow"
    else:
        los_letter, los_desc = "F", "Forced Breakdown"

    result["los"] = f"LOS {los_letter}"
    result["los_description"] = los_desc

    # Save to history automatically
    run_entry = {
        "id": f"run_{int(time.time())}_{len(SIMULATION_HISTORY)+1}",
        "timestamp": time.time(),
        "formatted_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "location": safe_bbox,
        "bbox": result.get("bbox", safe_bbox),
        "trips": safe_trips,
        "duration": safe_duration,
        "density": safe_density,
        "speed_kmh": round(speed, 1),
        "time_loss_s": round(delay, 1),
        "congestion_index": round(cong, 4),
        "los": f"LOS {los_letter}",
        "analytics": result.get("analytics", {}),
        "trip_details": result.get("trip_details", {})
    }
    SIMULATION_HISTORY.insert(0, run_entry)

    await broadcast_event("simulation_complete", run_entry)

    return result


@app.post("/api/simulation/step/network")
async def step_network(req: StepNetworkRequest):
    """Step 1: Network Generation from OpenStreetMap / Synthetic Corridor."""
    safe_bbox = security_utils.sanitize_location_query(req.bbox)
    res = sumo_server.generate_network(safe_bbox)
    return {"status": "success" if not res.startswith("Error") else "error", "message": res}


@app.post("/api/simulation/step/routes")
async def step_routes(req: StepRoutesRequest):
    """Step 2: Generate Indian Mixed Traffic Routes & Sublane Config."""
    safe_trips, safe_duration, safe_density = security_utils.clamp_simulation_parameters(
        trips=req.trips or 600,
        duration=req.duration or 3600,
        density=req.density
    )
    res = sumo_server.generate_routes(trips=safe_trips, duration=safe_duration, density=safe_density)
    return {"status": "success" if not res.startswith("Error") else "error", "message": res}


@app.post("/api/simulation/step/execute")
async def step_execute():
    """Step 3: Headless Microscopic Simulation Run."""
    res = sumo_server.run_headless_simulation()
    return {"status": "success" if not res.startswith("Error") else "error", "message": res}


@app.post("/api/simulation/step/gui")
async def step_gui(req: StepGuiRequest):
    """Step 3b: Launch Desktop Visual SUMO GUI."""
    res = sumo_server.run_gui_simulation(auto_start=req.auto_start, delay=req.delay or 150)
    return {"status": "success" if not res.startswith("Error") else "error", "message": res}


# =============================================================================
# ANALYTICS & RAW XML INSPECTION ENDPOINTS
# =============================================================================

@app.get("/api/analytics/results")
async def get_analytics_results():
    """Parses and returns network-wide statistics from stats.xml."""
    return sumo_server.analyze_results()


@app.get("/api/analytics/trips")
async def get_analytics_trips():
    """Parses and returns microscopic vehicle trip details & breakdown from tripinfo.xml."""
    return sumo_server.analyze_trip_details()


@app.get("/api/analytics/xml/{file_name}")
async def inspect_xml_file(file_name: str):
    """
    Safely reads and returns raw XML simulation files
    ('stats.xml', 'tripinfo.xml', 'mymap.sumocfg', 'mymap.net.xml', 'mymap.rou.xml', 'vtypes.add.xml').
    """
    allowed_files = [
        "stats.xml", "tripinfo.xml", "mymap.sumocfg",
        "mymap.net.xml", "mymap.rou.xml", "vtypes.add.xml", "gui-settings.xml"
    ]
    clean_name = os.path.basename(file_name).strip()
    if clean_name not in allowed_files:
        raise HTTPException(status_code=400, detail=f"Access denied. Allowed files: {', '.join(allowed_files)}")

    if not os.path.exists(clean_name):
        raise HTTPException(status_code=404, detail=f"File '{clean_name}' has not been generated yet. Please run a simulation first.")

    with open(clean_name, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    return {
        "file_name": clean_name,
        "size_bytes": os.path.getsize(clean_name),
        "content": content
    }


# =============================================================================
# MULTI-AI MODEL REASONING & CHAT COPILOT
# =============================================================================

@app.get("/api/ai/models")
async def get_ai_models():
    """Returns the list of supported AI models and their integration status."""
    return SUPPORTED_AI_MODELS


@app.post("/api/ai/chat")
async def ai_chat(payload: AiChatPayload):
    """
    Multi-AI Traffic Engineering Reasoning Assistant.
    Routes queries and simulation telemetry to Gemini, Claude, GPT-4o, Ollama, or Built-in Expert.
    """
    try:
        response = ai_router.query_ai_model(
            model=payload.model or "builtin",
            prompt=payload.prompt,
            simulation_data=payload.simulation_data,
            api_key=payload.api_key
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI query failed: {str(e)}")


# =============================================================================
# SIMULATION HISTORY MANAGEMENT
# =============================================================================

@app.get("/api/history")
async def get_history():
    """Returns the history of recent simulation runs."""
    return SIMULATION_HISTORY


@app.post("/api/history/save")
async def save_history_entry(payload: SaveRunPayload):
    """Saves a labeled simulation run into the persistence history."""
    run_entry = {
        "id": f"saved_{int(time.time())}_{len(SIMULATION_HISTORY)+1}",
        "timestamp": time.time(),
        "formatted_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": payload.title or "Custom Scenario",
        "notes": payload.notes or "",
        "simulation_data": payload.simulation_data
    }
    SIMULATION_HISTORY.insert(0, run_entry)
    return {"status": "success", "entry": run_entry}


@app.delete("/api/history/{run_id}")
async def delete_history_entry(run_id: str):
    """Deletes a run entry from history."""
    global SIMULATION_HISTORY
    SIMULATION_HISTORY = [r for r in SIMULATION_HISTORY if r.get("id") != run_id]
    return {"status": "success", "remaining": len(SIMULATION_HISTORY)}


# =============================================================================
# REAL-TIME SERVER-SENT EVENTS (SSE) STREAM
# =============================================================================

@app.get("/api/stream/events")
async def stream_simulation_events(request: Request):
    """Server-Sent Events endpoint streaming real-time simulation progress and logs."""
    queue = asyncio.Queue()
    SIMULATION_EVENT_SUBSCRIBERS.append(queue)

    async def event_generator():
        try:
            # Send initial connection handshake
            yield {"event": "connected", "data": json.dumps({"status": "ready", "time": time.time()})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {"event": "simulation_event", "data": data}
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield {"event": "ping", "data": json.dumps({"heartbeat": time.time()})}
        finally:
            if queue in SIMULATION_EVENT_SUBSCRIBERS:
                SIMULATION_EVENT_SUBSCRIBERS.remove(queue)

    return EventSourceResponse(event_generator())


# =============================================================================
# OAUTH 2.1 & MCP BACKWARD COMPATIBILITY ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "SUMO AI Web Application & MCP Bridge",
        "version": "2.0.0",
        "timestamp": time.time()
    }

@app.get("/.well-known/mcp")
@app.get("/mcp/info")
async def mcp_discovery():
    return {
        "protocol": "mcp",
        "version": "1.0",
        "name": "SUMO Traffic Simulation Server",
        "transports": {
            "sse": "/sse",
            "messages": "/messages/"
        },
        "endpoints": {
            "web_ui": "/",
            "api_docs": "/docs",
            "health": "/health"
        }
    }

# Mount FastMCP SSE handlers for backward MCP compatibility
try:
    app.mount("", sumo_server.mcp.sse_app())
except Exception as e:
    security_utils.logger.warning(f"FastMCP mount notice: {e}")


# =============================================================================
# CLI LAUNCHER & STANDALONE EXECUTION
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="SUMO AI Web Application Server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Port to listen on (default: 8000)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open web application in default browser")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"

    print("=" * 72)
    print("   🚦 SUMO AI WEB APPLICATION – URBAN TRAFFIC SIMULATION PLATFORM")
    print(f"   Python: {sys.version.split()[0]} | Environment: Ready")
    print("=" * 72)
    print(f"  [*] Web Application Interface : {url}")
    print(f"  [*] API Documentation (Swagger): {url}/docs")
    print(f"  [*] Live SSE Progress Stream   : {url}/api/stream/events")
    print(f"  [*] MCP Discovery Endpoint     : {url}/.well-known/mcp")
    print("=" * 72)

    if args.open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(url)
        import threading
        threading.Thread(target=_open, daemon=True).start()

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
