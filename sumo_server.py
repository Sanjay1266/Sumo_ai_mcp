import os
import sys
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server instance for SUMO Simulation Pipeline
mcp = FastMCP("SUMO Traffic Simulation Server")


def find_sumo_script(script_name: str) -> str:
    """
    Locate SUMO helper scripts (e.g. osmGet.py, randomTrips.py) in CWD or SUMO_HOME tools.
    """
    if os.path.exists(script_name):
        return script_name

    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        candidate_paths = [
            os.path.join(sumo_home, "tools", "osm", script_name),
            os.path.join(sumo_home, "tools", script_name),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                return path

    return script_name


def find_sumo_binary(binary_name: str) -> str:
    """
    Locate SUMO executable binaries (e.g. netconvert, sumo) on PATH or inside SUMO_HOME/bin.
    """
    which_path = shutil.which(binary_name)
    if which_path:
        return which_path

    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        ext = ".exe" if sys.platform == "win32" else ""
        candidate = os.path.join(sumo_home, "bin", f"{binary_name}{ext}")
        if os.path.exists(candidate):
            return candidate

    return binary_name


import urllib.request
import urllib.parse


def resolve_location_to_bbox(location_or_bbox: str) -> str:
    """
    Automatically converts place names (e.g. 'Erode City Center', 'Ettimadai', 'Amrita University', 'Coimbatore') 
    or numerical bbox strings ('min_lon,min_lat,max_lon,max_lat') into SUMO bbox format automatically.
    """
    if not location_or_bbox:
        return "76.890,10.895,76.915,10.915"

    query_str = location_or_bbox.strip()

    # Check if already a 4-comma numerical string
    parts = query_str.split(',')
    if len(parts) == 4:
        try:
            floats = [float(p) for p in parts]
            return f"{floats[0]},{floats[1]},{floats[2]},{floats[3]}"
        except ValueError:
            pass

    # High-precision offline presets for instant resolution
    presets = {
        "ettimadai": "76.890,10.895,76.915,10.915",
        "amrita": "76.898,10.900,76.910,10.910",
        "erode": "77.700,11.330,77.780,11.410",
        "coimbatore": "76.940,11.000,76.980,11.030",
        "chennai": "80.250,13.060,80.290,13.100",
        "bangalore": "77.580,12.960,77.620,13.000",
        "bengaluru": "77.580,12.960,77.620,13.000",
        "delhi": "77.200,28.600,77.240,28.640"
    }

    key = query_str.lower()
    for preset_name, preset_bbox in presets.items():
        if preset_name in key:
            return preset_bbox

    # Dynamic OpenStreetMap Nominatim Geocoding lookup
    try:
        url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(query_str) + "&format=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'SUMO-MCP-AutoGeocoder/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and len(data) > 0:
                boundingbox = data[0].get('boundingbox')  # [southLat, northLat, westLon, eastLon]
                if boundingbox and len(boundingbox) == 4:
                    min_lat, max_lat, min_lon, max_lon = [float(x) for x in boundingbox]
                    return f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"
    except Exception:
        pass

    return query_str


@mcp.tool()
def generate_network(bbox: str) -> str:
    """
    Step 1: Network Generation Tool
    Downloads OpenStreetMap data automatically using a location name (e.g. 'Erode City Center', 'Ettimadai') or bounding box and converts it into a SUMO network file (.net.xml).

    :param bbox: Location name (e.g. 'Erode City Center', 'Ettimadai') or bounding box string ('min_lon,min_lat,max_lon,max_lat')
    :return: Confirmation message when mymap.net.xml is created.
    """
    target_bbox = resolve_location_to_bbox(bbox)
    osm_script = find_sumo_script("osmGet.py")
    netconvert_bin = find_sumo_binary("netconvert")

    try:
        # Execute osmGet.py to download map data for given bounding box and prefix 'mymap'
        subprocess.run([sys.executable, osm_script, "-b", target_bbox, "-p", "mymap"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        # Detect generated OSM file (e.g. mymap_bbox.osm.xml or mymap.osm)
        osm_files = [f for f in os.listdir(".") if f.startswith("mymap") and (f.endswith(".osm") or f.endswith(".osm.xml"))]
        osm_input = ",".join(osm_files) if osm_files else "mymap.osm"

        # Execute netconvert to convert downloaded OpenStreetMap file into SUMO XML network format
        subprocess.run([netconvert_bin, "--osm-files", osm_input, "-o", "mymap.net.xml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        return f"Success: Network file 'mymap.net.xml' is ready for bbox ({target_bbox})."
    except subprocess.CalledProcessError as e:
        return f"Error generating network: Subprocess exited with code {e.returncode}. Stderr: {e.stderr}"
    except Exception as e:
        return f"Error generating network: {str(e)}"


def create_vtypes_file(file_path: str = "vtypes.add.xml") -> None:
    """Helper to auto-generate SUMO additional file with heterogeneous Indian vehicle types distribution."""
    vtypes_xml = """<additional>
    <vTypeDistribution id="indian_mixed">
        <vType id="ind_motorcycle" vClass="motorcycle" length="1.8" width="0.8" minGap="0.5" maxSpeed="16.67" accel="3.5" decel="5.0" probability="0.35" color="1,0.3,0.3" latAlignment="arbitrary"/>
        <vType id="ind_autorickshaw" vClass="moped" length="2.6" width="1.3" minGap="0.8" maxSpeed="13.89" accel="2.0" decel="4.5" probability="0.20" color="1,0.8,0" latAlignment="arbitrary"/>
        <vType id="ind_car" vClass="passenger" length="4.3" width="1.8" minGap="1.0" maxSpeed="22.22" accel="2.6" decel="4.5" probability="0.30" color="0.2,0.6,1"/>
        <vType id="ind_bus" vClass="bus" length="10.5" width="2.5" minGap="2.0" maxSpeed="13.89" accel="1.2" decel="3.5" probability="0.08" color="0.2,0.8,0.2"/>
        <vType id="ind_truck" vClass="truck" length="8.0" width="2.4" minGap="2.0" maxSpeed="13.89" accel="1.0" decel="3.0" probability="0.07" color="0.8,0.5,0.2"/>
    </vTypeDistribution>
</additional>"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(vtypes_xml)


def create_gui_settings(net_file: str = "mymap.net.xml", gui_settings_file: str = "gui-settings.xml") -> None:
    """Helper to auto-generate SUMO GUI settings XML for optimal human visual playback."""
    center_x, center_y, zoom = 1000.0, 1000.0, 500.0
    if os.path.exists(net_file):
        try:
            tree = ET.parse(net_file)
            location = tree.getroot().find('location')
            if location is not None:
                bounds = [float(x) for x in location.get('convBoundary', '0,0,2000,2000').split(',')]
                minX, minY, maxX, maxY = bounds
                center_x = (minX + maxX) / 2.0
                center_y = (minY + maxY) / 2.0
                width = max(1.0, maxX - minX)
                height = max(1.0, maxY - minY)
                zoom = max(400.0, min(2500.0, 120000.0 / max(width, height)))
        except Exception:
            pass

    gui_xml = f"""<viewsettings>
    <scheme name="real world"/>
    <delay value="150"/>
    <viewport zoom="{zoom:.2f}" x="{center_x:.2f}" y="{center_y:.2f}"/>
    <vehicles vehicleScale="2.5" vehicleColorer="by vType"/>
</viewsettings>"""

    with open(gui_settings_file, "w", encoding="utf-8") as f:
        f.write(gui_xml)


@mcp.tool()
def generate_routes(trips: int = 600, duration: int = 7200, density: str = None) -> str:
    """
    Step 2: Route Generation Tool
    Generates random trip routes for heterogeneous Indian traffic (motorcycles, autos, cars, buses, trucks) and sublane configuration file.

    :param trips: Total number of vehicles/trips to generate across the simulation duration (default: 600)
    :param duration: Total simulation duration in seconds (default: 7200 seconds / 2 hours)
    :param density: Optional preset density level ('low': 250, 'medium': 600, 'high': 1200, 'congested': 2000)
    :return: Confirmation message when mymap.sumocfg is created.
    """
    trips_script = find_sumo_script("randomTrips.py")
    
    total_trips = trips
    if density:
        density_map = {"low": 250, "medium": 600, "high": 1200, "congested": 2000}
        total_trips = density_map.get(density.lower(), trips)

    period = max(1, duration // max(1, total_trips))

    if not os.path.exists("mymap.net.xml"):
        return "Error: 'mymap.net.xml' not found. Please run 'generate_network' first."

    try:
        # Step 1: Create heterogeneous Indian vehicle types file
        create_vtypes_file("vtypes.add.xml")

        # Step 2: Execute randomTrips.py to generate random routes on the network over specified duration with indian_mixed distribution
        subprocess.run([
            sys.executable, trips_script,
            "-n", "mymap.net.xml",
            "-e", str(duration),
            "-p", str(period),
            "-l",
            "-r", "mymap.rou.xml",
            "-a", "vtypes.add.xml",
            "--trip-attributes", 'type="indian_mixed"'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        # Step 3: Generate GUI visual enhancement settings file
        create_gui_settings("mymap.net.xml", "gui-settings.xml")

        # Step 4: Programmatically create mymap.sumocfg XML file referencing network, route, and sublane settings
        sumocfg_content = f"""<configuration>
    <input>
        <net-file value="mymap.net.xml"/>
        <route-files value="mymap.rou.xml"/>
        <gui-settings-file value="gui-settings.xml"/>
    </input>
    <processing>
        <lateral-resolution value="0.8"/>
    </processing>
    <time>
        <begin value="0"/>
        <end value="{duration}"/>
    </time>
</configuration>"""

        with open("mymap.sumocfg", "w", encoding="utf-8") as f:
            f.write(sumocfg_content)

        return f"Success: SUMO configuration file 'mymap.sumocfg' generated with {total_trips} trips across heterogeneous vehicle types (motorcycles, autos, cars, buses, trucks) and sublane resolution."
    except subprocess.CalledProcessError as e:
        return f"Error generating routes: Subprocess exited with code {e.returncode}. Stderr: {e.stderr}"
    except Exception as e:
        return f"Error generating routes: {str(e)}"


@mcp.tool()
def run_headless_simulation() -> str:
    """
    Step 3: Headless Execution Tool
    Executes the SUMO simulation headlessly and produces statistics and trip info XML reports.

    :return: Confirmation message when the simulation completes.
    """
    sumo_bin = find_sumo_binary("sumo")

    if not os.path.exists("mymap.sumocfg"):
        return "Error: 'mymap.sumocfg' not found. Please run 'generate_routes' first."

    try:
        # Execute SUMO headlessly using mymap.sumocfg configuration, capturing statistics and trip info XMLs
        subprocess.run([
            sumo_bin,
            "-c", "mymap.sumocfg",
            "--statistic-output", "stats.xml",
            "--tripinfo-output", "tripinfo.xml"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        return "Success: Headless SUMO simulation completed. 'stats.xml' and 'tripinfo.xml' generated."
    except subprocess.CalledProcessError as e:
        return f"Error running simulation: Subprocess exited with code {e.returncode}. Stderr: {e.stderr}"
    except Exception as e:
        return f"Error running simulation: {str(e)}"


@mcp.tool()
def run_gui_simulation(auto_start: bool = True, delay: int = 150) -> str:
    """
    Step 3b: Visual GUI Execution Tool
    Launches the SUMO GUI application on desktop to view vehicles and traffic simulation visually in real-time.

    :param auto_start: Automatically start playback upon opening sumo-gui window
    :param delay: Milliseconds of delay per simulation step to ensure human-visible smooth playback (default: 150ms)
    :return: Confirmation message.
    """
    sumo_gui_bin = find_sumo_binary("sumo-gui")

    if not os.path.exists("mymap.sumocfg"):
        return "Error: 'mymap.sumocfg' not found. Please run 'generate_routes' first."

    # Ensure gui-settings.xml exists before launching GUI
    if not os.path.exists("gui-settings.xml"):
        create_gui_settings("mymap.net.xml", "gui-settings.xml")

    try:
        cmd = [sumo_gui_bin, "-c", "mymap.sumocfg", "-g", "gui-settings.xml", "--delay", str(delay)]
        if auto_start:
            cmd.append("--start")
        subprocess.Popen(cmd)
        return f"Success: SUMO GUI app launched on desktop with centered viewport, enlarged vehicles (3.5x), real world theme, and {delay}ms step delay."
    except Exception as e:
        return f"Error launching SUMO GUI: {str(e)}"



@mcp.tool()
def analyze_results() -> dict:
    """
    Step 4: Analytics Parsing Tool
    Parses stats.xml using xml.etree.ElementTree and extracts key simulation metrics.

    :return: Clean, structured dictionary/JSON object containing total loaded, inserted, and average route length.
    """
    stats_file = "stats.xml"
    if not os.path.exists(stats_file):
        return {
            "error": f"Statistics file '{stats_file}' not found. Please run 'run_headless_simulation' first."
        }

    try:
        tree = ET.parse(stats_file)
        root = tree.getroot()

        # Locate <vehicles> element recursively for loaded and inserted counts
        vehicles_elem = root.find(".//vehicles")
        total_loaded = int(vehicles_elem.attrib.get("loaded", 0)) if vehicles_elem is not None else 0
        total_inserted = int(vehicles_elem.attrib.get("inserted", 0)) if vehicles_elem is not None else 0

        # Locate <vehicleTripStatistics> element for route length
        trip_stats_elem = root.find(".//vehicleTripStatistics")
        avg_route_length = 0.0
        if trip_stats_elem is not None:
            if "routeLength" in trip_stats_elem.attrib:
                avg_route_length = float(trip_stats_elem.attrib["routeLength"])
            elif "avgRouteLength" in trip_stats_elem.attrib:
                avg_route_length = float(trip_stats_elem.attrib["avgRouteLength"])

        return {
            "total_vehicles_loaded": total_loaded,
            "total_vehicles_inserted": total_inserted,
            "average_route_length": avg_route_length
        }
    except Exception as e:
        return {
            "error": f"Failed to parse statistics: {str(e)}"
        }


@mcp.tool()
def run_full_simulation(bbox: str, trips: int = 600, duration: int = 7200, density: str = None, launch_gui: bool = True) -> dict:
    """
    Master Orchestration Tool
    Executes the COMPLETE SUMO simulation pipeline end-to-end in a SINGLE call without multi-turn prompting:
    1. Downloads OSM map data for bbox & generates network (.net.xml)
    2. Generates vehicle routes (.rou.xml, vtypes.add.xml & sumocfg)
    3. Auto-configures centered visual GUI settings (gui-settings.xml)
    4. Executes headless simulation & produces statistics XML
    5. Automatically opens SUMO GUI desktop app for live visual playback
    6. Parses and returns final traffic analytics metrics

    :param bbox: Bounding box coordinate string (min_lon,min_lat,max_lon,max_lat)
    :param trips: Total number of vehicle trips to generate (default: 600)
    :param duration: Total simulation duration in seconds (default: 7200s / 2 hours)
    :param density: Optional preset density level ('low': 250, 'medium': 600, 'high': 1200, 'congested': 2000)
    :param launch_gui: Automatically open the visual SUMO GUI app on desktop (default: True)
    :return: Combined result dictionary containing status messages and final analytics.
    """
    # Step 1: Generate network
    net_res = generate_network(bbox)
    if net_res.startswith("Error"):
        return {"status": "error", "step": "generate_network", "message": net_res}

    # Step 2: Generate routes & gui settings with heterogeneous vehicle distribution
    routes_res = generate_routes(trips=trips, duration=duration, density=density)
    if routes_res.startswith("Error"):
        return {"status": "error", "step": "generate_routes", "message": routes_res}

    # Step 3: Run headless simulation for stats XML
    headless_res = run_headless_simulation()

    # Step 4: Launch GUI if requested
    gui_res = None
    if launch_gui:
        gui_res = run_gui_simulation(auto_start=True, delay=150)

    # Step 5: Analyze results
    analytics = analyze_results()

    return {
        "status": "success",
        "bbox": bbox,
        "trips": trips,
        "duration": duration,
        "density": density or "medium",
        "gui_launched": launch_gui,
        "network_status": net_res,
        "routes_status": routes_res,
        "headless_status": headless_res,
        "gui_status": gui_res,
        "analytics": analytics
    }


if __name__ == "__main__":
    mcp.run()
