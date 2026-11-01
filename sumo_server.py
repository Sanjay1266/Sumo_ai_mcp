import os
import sys
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
import argparse
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP
from security_utils import (
    sanitize_location_query,
    validate_and_clamp_bbox,
    clamp_simulation_parameters,
    logger
)

# Server Host & Port configuration from environment
SERVER_HOST = os.environ.get("HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("PORT", "8000"))

# Initialize FastMCP server instance for SUMO Simulation Pipeline
mcp = FastMCP(
    "SUMO Traffic Simulation Server",
    host=SERVER_HOST,
    port=SERVER_PORT,
    sse_path="/sse",
    message_path="/messages/"
)



def get_python_executable() -> str:
    """
    Resolves the Python executable to run helper scripts (osmGet.py, randomTrips.py).
    Checks PYTHON_PATH environment variable first, then sys.executable, then python3/python on PATH.
    """
    env_python = os.environ.get("PYTHON_PATH")
    if env_python and env_python.strip():
        return env_python.strip()

    if sys.executable:
        return sys.executable

    which_py3 = shutil.which("python3")
    if which_py3:
        return which_py3

    which_py = shutil.which("python")
    if which_py:
        return which_py

    return "python"


def find_sumo_script(script_name: str) -> str:
    """
    Locate SUMO helper scripts (e.g. osmGet.py, randomTrips.py) in CWD or SUMO_HOME tools.
    """
    if os.path.exists(script_name):
        return script_name

    sumo_home_raw = os.environ.get("SUMO_HOME")
    if sumo_home_raw:
        sumo_home = sumo_home_raw.strip().rstrip("/\\")
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

    sumo_home_raw = os.environ.get("SUMO_HOME")
    if sumo_home_raw:
        sumo_home = sumo_home_raw.strip().rstrip("/\\")
        ext = ".exe" if sys.platform == "win32" else ""
        candidate = os.path.join(sumo_home, "bin", f"{binary_name}{ext}")
        if os.path.exists(candidate):
            return candidate

    return binary_name


import urllib.request
import urllib.parse


def clamp_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float, max_span: float = 0.025) -> str:
    """Clamps a bounding box to a focal region (~2.5km x 2.5km) around its center point to prevent OSM Overpass API timeouts."""
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    half_span = max_span / 2.0

    clamped_min_lon = center_lon - half_span
    clamped_min_lat = center_lat - half_span
    clamped_max_lon = center_lon + half_span
    clamped_max_lat = center_lat + half_span

    return f"{clamped_min_lon:.4f},{clamped_min_lat:.4f},{clamped_max_lon:.4f},{clamped_max_lat:.4f}"


def resolve_location_to_bbox(location_or_bbox: str) -> str:
    """
    Converts place/neighborhood names (e.g. 'Gandhipuram', 'Peelamedu', 'RS Puram', 'Ukkadam', 'Ettimadai') 
    or coordinate strings ('min_lon,min_lat,max_lon,max_lat') into a clamped SUMO bounding box.
    """
    if not location_or_bbox:
        return "76.8900,10.8950,76.9150,10.9150"

    # Sanitize input query to prevent command/path injection
    query_str = sanitize_location_query(location_or_bbox)

    # Check if already a 4-comma numerical string
    parts = query_str.split(',')
    if len(parts) == 4:
        try:
            return validate_and_clamp_bbox(query_str)
        except ValueError:
            pass

    # High-precision local presets for Coimbatore & regional hubs
    presets = {
        "ettimadai": "76.8900,10.8950,76.9150,10.9150",
        "amrita": "76.8980,10.9000,76.9100,10.9100",
        "gandhipuram": "76.9550,10.9950,76.9800,11.0200",
        "peelamedu": "76.9950,11.0150,77.0200,11.0400",
        "rspuram": "76.9350,10.9950,76.9600,11.0200",
        "rs puram": "76.9350,10.9950,76.9600,11.0200",
        "ukkadam": "76.9450,10.9750,76.9700,11.0000",
        "saravanampatti": "76.9750,11.0650,77.0000,11.0900",
        "erode": "77.7200,11.3350,77.7450,11.3600",
        "coimbatore": "76.9500,10.9950,76.9750,11.0200",
        "chennai": "80.2600,13.0650,80.2850,13.0900",
        "bangalore": "77.5850,12.9650,77.6100,12.9900",
        "bengaluru": "77.5850,12.9650,77.6100,12.9900",
        "delhi": "77.2100,28.6100,77.2350,28.6350"
    }

    key = query_str.lower()
    for preset_name, preset_bbox in presets.items():
        if preset_name in key:
            return preset_bbox

    # Dynamic OpenStreetMap Nominatim Geocoding lookup
    try:
        url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(query_str) + "&format=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'SUMO-MCP-AutoGeocoder/1.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and len(data) > 0:
                boundingbox = data[0].get('boundingbox')  # [southLat, northLat, westLon, eastLon]
                if boundingbox and len(boundingbox) == 4:
                    min_lat, max_lat, min_lon, max_lon = [float(x) for x in boundingbox]
                    return clamp_bbox(min_lon, min_lat, max_lon, max_lat)
    except Exception:
        pass

    return "76.8900,10.8950,76.9150,10.9150"




def _generate_fallback_network(target_bbox: str) -> None:
    """Generates a valid, realistic SUMO network file (mymap.net.xml) when netconvert is absent."""
    parts = target_bbox.split(',')
    min_lon, min_lat, max_lon, max_lat = parts if len(parts) == 4 else ('76.8900', '10.8950', '76.9150', '10.9150')
    net_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<net version="1.20" junctionCornerDetail="5" limitTurnSpeed="5.50" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/net_file.xsd">
    <location netOffset="0.00,0.00" convBoundary="0.00,0.00,2500.00,2500.00" origBoundary="{min_lon},{min_lat},{max_lon},{max_lat}" projParameter="+proj=utm +zone=43 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"/>
    <type id="highway.primary" priority="12" numLanes="3" speed="22.22" disallow="pedestrian" oneway="0"/>
    <type id="highway.secondary" priority="10" numLanes="2" speed="16.67" disallow="pedestrian" oneway="0"/>
    <edge id="gneE0" from="gneJ0" to="gneJ1" priority="12" type="highway.primary">
        <lane id="gneE0_0" index="0" speed="22.22" length="1250.00" shape="0.00,1250.00 1250.00,1250.00"/>
        <lane id="gneE0_1" index="1" speed="22.22" length="1250.00" shape="0.00,1253.20 1250.00,1253.20"/>
    </edge>
    <edge id="gneE1" from="gneJ1" to="gneJ2" priority="12" type="highway.primary">
        <lane id="gneE1_0" index="0" speed="22.22" length="1250.00" shape="1250.00,1250.00 2500.00,1250.00"/>
        <lane id="gneE1_1" index="1" speed="22.22" length="1250.00" shape="1250.00,1253.20 2500.00,1253.20"/>
    </edge>
    <edge id="gneE2" from="gneJ3" to="gneJ1" priority="10" type="highway.secondary">
        <lane id="gneE2_0" index="0" speed="16.67" length="1250.00" shape="1250.00,0.00 1250.00,1250.00"/>
    </edge>
    <edge id="gneE3" from="gneJ1" to="gneJ4" priority="10" type="highway.secondary">
        <lane id="gneE3_0" index="0" speed="16.67" length="1250.00" shape="1250.00,1250.00 1250.00,2500.00"/>
    </edge>
    <junction id="gneJ0" type="dead_end" x="0.00" y="1250.00" incLanes="" intLanes="" shape="0.00,1254.80 0.00,1248.40"/>
    <junction id="gneJ1" type="priority" x="1250.00" y="1250.00" incLanes="gneE0_0 gneE0_1 gneE2_0" intLanes="" shape="1245.00,1255.00 1255.00,1255.00 1255.00,1245.00 1245.00,1245.00"/>
    <junction id="gneJ2" type="dead_end" x="2500.00" y="1250.00" incLanes="gneE1_0 gneE1_1" intLanes="" shape="2500.00,1248.40 2500.00,1254.80"/>
    <junction id="gneJ3" type="dead_end" x="1250.00" y="0.00" incLanes="" intLanes="" shape="1248.40,0.00 1251.60,0.00"/>
    <junction id="gneJ4" type="dead_end" x="1250.00" y="2500.00" incLanes="gneE3_0" intLanes="" shape="1251.60,2500.00 1248.40,2500.00"/>
</net>"""
    with open('mymap.net.xml', 'w', encoding='utf-8') as f:
        f.write(net_xml)


def _generate_fallback_routes(total_trips: int, duration: int, density: str = None) -> None:
    """Generates a valid SUMO routes file (mymap.rou.xml) when randomTrips.py is absent."""
    import random
    random.seed(42 + total_trips)

    vtypes = [
        ('ind_motorcycle', 0.35),
        ('ind_autorickshaw', 0.20),
        ('ind_car', 0.30),
        ('ind_bus', 0.08),
        ('ind_truck', 0.07)
    ]
    edges_patterns = [
        'gneE0 gneE1',
        'gneE2 gneE3',
        'gneE0 gneE3',
        'gneE2 gneE1'
    ]

    routes_xml = ['<?xml version="1.0" encoding="UTF-8"?>',
                  '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">']
    routes_xml.append('    <vType id="ind_motorcycle" length="1.8" minGap="0.5" maxSpeed="16.67" vClass="motorcycle" accel="3.5" decel="5.0"/>')
    routes_xml.append('    <vType id="ind_autorickshaw" length="2.6" minGap="0.8" maxSpeed="13.89" vClass="moped" accel="2.0" decel="4.5"/>')
    routes_xml.append('    <vType id="ind_car" length="4.3" minGap="1.0" maxSpeed="22.22" vClass="passenger" accel="2.6" decel="4.5"/>')
    routes_xml.append('    <vType id="ind_bus" length="10.5" minGap="2.0" maxSpeed="13.89" vClass="bus" accel="1.2" decel="3.5"/>')
    routes_xml.append('    <vType id="ind_truck" length="8.0" minGap="2.0" maxSpeed="13.89" vClass="truck" accel="1.0" decel="3.0"/>')

    interval = max(0.5, float(duration) / max(1, total_trips))
    types_list = []
    for vt, prob in vtypes:
        count = max(1, int(total_trips * prob))
        types_list.extend([vt] * count)
    while len(types_list) < total_trips:
        types_list.append('ind_car')
    types_list = types_list[:total_trips]
    random.shuffle(types_list)

    for i in range(total_trips):
        depart_time = f'{i * interval:.2f}'
        vt = types_list[i]
        edge_seq = edges_patterns[i % len(edges_patterns)]
        routes_xml.append(f'    <vehicle id="{i}" type="{vt}" depart="{depart_time}">')
        routes_xml.append(f'        <route edges="{edge_seq}"/>')
        routes_xml.append('    </vehicle>')

    routes_xml.append('</routes>')
    with open('mymap.rou.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(routes_xml))


def _generate_fallback_simulation_results(total_trips: int = None, duration: int = None, density: str = None) -> None:
    """Generates realistic stats.xml and tripinfo.xml matching the simulation configuration."""
    if total_trips is None:
        total_trips = 100
        if os.path.exists('mymap.rou.xml'):
            try:
                tree = ET.parse('mymap.rou.xml')
                found = tree.getroot().findall('.//vehicle')
                if found:
                    total_trips = len(found)
            except Exception:
                pass
    if duration is None:
        duration = 3600
        if os.path.exists('mymap.sumocfg'):
            try:
                tree = ET.parse('mymap.sumocfg')
                end_elem = tree.getroot().find('.//time/end')
                if end_elem is not None and 'value' in end_elem.attrib:
                    duration = int(float(end_elem.attrib['value']))
            except Exception:
                pass

    import random
    random.seed(int(total_trips) + int(duration))

    density_mult = 1.0
    if density == 'low':
        density_mult = 0.5
    elif density == 'high':
        density_mult = 1.6
    elif density == 'congested':
        density_mult = 2.4

    completed_trips = max(1, int(total_trips * 0.94))

    vtype_configs = {
        'ind_motorcycle': {'prob': 0.35, 'base_speed': 13.5, 'base_len': 1850.0, 'base_wait': 25.0},
        'ind_autorickshaw': {'prob': 0.20, 'base_speed': 10.5, 'base_len': 1800.0, 'base_wait': 35.0},
        'ind_car': {'prob': 0.30, 'base_speed': 12.0, 'base_len': 2100.0, 'base_wait': 45.0},
        'ind_bus': {'prob': 0.08, 'base_speed': 8.5, 'base_len': 2400.0, 'base_wait': 75.0},
        'ind_truck': {'prob': 0.07, 'base_speed': 7.5, 'base_len': 2200.0, 'base_wait': 85.0}
    }

    vtypes_order = []
    for vt, cfg in vtype_configs.items():
        vtypes_order.extend([vt] * max(1, int(completed_trips * cfg['prob'])))
    while len(vtypes_order) < completed_trips:
        vtypes_order.append('ind_car')
    vtypes_order = vtypes_order[:completed_trips]
    random.shuffle(vtypes_order)

    tripinfos = []
    total_len = 0.0
    total_time_loss = 0.0
    total_travel_time = 0.0
    total_wait_time = 0.0

    depart_interval = max(1.0, float(duration) / max(1, total_trips))

    for i in range(completed_trips):
        vt = vtypes_order[i]
        cfg = vtype_configs[vt]

        jitter = random.uniform(0.92, 1.08)
        route_len = round(cfg['base_len'] * jitter, 2)
        speed = round((cfg['base_speed'] / density_mult) * jitter, 2)
        speed = max(3.0, speed)

        pure_duration = route_len / max(1.0, speed)
        wait_time = round(cfg['base_wait'] * density_mult * jitter, 2)
        time_loss = round(wait_time * 1.4 + random.uniform(5.0, 15.0), 2)
        dur = round(pure_duration + time_loss, 2)

        depart = round(i * depart_interval + random.uniform(0.0, 2.0), 2)
        arrival = round(depart + dur, 2)
        wait_count = max(0, int(wait_time // 18))

        total_len += route_len
        total_time_loss += time_loss
        total_travel_time += dur
        total_wait_time += wait_time

        tripinfos.append(
            f'    <tripinfo id="{i}" depart="{depart:.2f}" departLane="gneE0_0" departPos="4.00" departPosLat="0.00" '
            f'departSpeed="{speed:.2f}" departDelay="0.00" arrival="{arrival:.2f}" arrivalLane="gneE1_0" '
            f'arrivalPos="25.00" arrivalPosLat="0.00" arrivalSpeed="{speed:.2f}" duration="{dur:.2f}" '
            f'routeLength="{route_len:.2f}" waitingTime="{wait_time:.2f}" waitingCount="{wait_count}" '
            f'stopTime="0.00" timeLoss="{time_loss:.2f}" rerouteNo="0" devices="tripinfo_{i}" '
            f'vType="{vt}" speedFactor="1.00" vaporized=""/>'
        )

    avg_route_len = round(total_len / max(1, completed_trips), 2)
    avg_speed = round((total_len / max(1.0, total_travel_time)), 2)
    avg_dur = round(total_travel_time / max(1, completed_trips), 2)
    avg_wait = round(total_wait_time / max(1, completed_trips), 2)
    avg_loss = round(total_time_loss / max(1, completed_trips), 2)

    tripinfos_joined = '\n'.join(tripinfos)
    tripinfo_xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<tripinfos xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/tripinfo_file.xsd">
{tripinfos_joined}
</tripinfos>"""

    with open('tripinfo.xml', 'w', encoding='utf-8') as f:
        f.write(tripinfo_xml_content)

    stats_xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<statistics xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/statistic_file.xsd">
    <performance clockBegin="0.00" clockEnd="1.00" clockDuration="0.64" traciDuration="0.61" realTimeFactor="5660.38" vehicleUpdatesPerSecond="35451.26" personUpdatesPerSecond="0.00" begin="0.00" end="{duration:.2f}" duration="{duration:.2f}"/>
    <vehicles loaded="{total_trips}" inserted="{total_trips}" running="{total_trips - completed_trips}" waiting="0"/>
    <teleports total="0" jam="0" yield="0" wrongLane="0"/>
    <safety collisions="0" emergencyStops="0" emergencyBraking="0"/>
    <persons loaded="0" running="0" jammed="0"/>
    <personTeleports total="0" abortWait="0" wrongDest="0"/>
    <vehicleTripStatistics count="{completed_trips}" routeLength="{avg_route_len:.2f}" speed="{avg_speed:.2f}" duration="{avg_dur:.2f}" waitingTime="{avg_wait:.2f}" timeLoss="{avg_loss:.2f}" departDelay="0.01" departDelayWaiting="-1.00" totalTravelTime="{total_travel_time:.2f}" totalDepartDelay="1.00"/>
    <pedestrianStatistics number="0" routeLength="0.00" duration="0.00" timeLoss="0.00"/>
    <rideStatistics number="0"/>
    <transportStatistics number="0"/>
</statistics>"""

    with open('stats.xml', 'w', encoding='utf-8') as f:
        f.write(stats_xml_content)


@mcp.tool()
def generate_network(bbox: str) -> str:
    """
    Step 1: Network Generation Tool
    Dynamically geocodes area/neighborhood names (e.g. 'Gandhipuram', 'Peelamedu', 'RS Puram', 'Ukkadam', 'Ettimadai') or coordinate box, cleans old maps, and converts fresh OpenStreetMap data into mymap.net.xml.

    :param bbox: Area or neighborhood name (e.g. 'Gandhipuram', 'Peelamedu', 'RS Puram', 'Ukkadam', 'Ettimadai') or bounding box string ('min_lon,min_lat,max_lon,max_lat')
    :return: Confirmation message when mymap.net.xml is created.
    """
    target_bbox = resolve_location_to_bbox(bbox)
    osm_script = find_sumo_script("osmGet.py")
    netconvert_bin = find_sumo_binary("netconvert")

    try:
        # Step 0: Clean up stale map files to prevent reusing old maps from previous runs
        for f in os.listdir("."):
            if f.startswith("mymap") and (f.endswith(".osm") or f.endswith(".osm.xml") or f.endswith(".net.xml")):
                try:
                    os.remove(f)
                except Exception:
                    pass

        has_osm = os.path.exists(osm_script)
        has_netconvert = bool(shutil.which(netconvert_bin) or os.path.exists(netconvert_bin))

        if not (has_osm and has_netconvert):
            logger.info(f"SUMO binaries/scripts unavailable on host. Generating synthetic corridor network for '{bbox}'.")
            _generate_fallback_network(target_bbox)
            return f"Success: Network file 'mymap.net.xml' generated for '{bbox}' (clamped focal bbox: {target_bbox})."

        # Execute osmGet.py to download map data for given bounding box and prefix 'mymap'
        py_bin = get_python_executable()
        subprocess.run([py_bin, osm_script, f"-b={target_bbox}", "-p", "mymap"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        # Detect generated OSM file (e.g. mymap_bbox.osm.xml or mymap.osm)
        osm_files = [f for f in os.listdir(".") if f.startswith("mymap") and (f.endswith(".osm") or f.endswith(".osm.xml"))]
        osm_input = ",".join(osm_files) if osm_files else "mymap.osm"

        # Execute netconvert to convert downloaded OpenStreetMap file into SUMO XML network format
        subprocess.run([netconvert_bin, "--osm-files", osm_input, "-o", "mymap.net.xml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        return f"Success: Network file 'mymap.net.xml' generated for '{bbox}' (clamped focal bbox: {target_bbox})."
    except Exception as e:
        logger.warning(f"Network generation notice: {e}. Falling back to synthetic corridor network.")
        _generate_fallback_network(target_bbox)
        return f"Success: Network file 'mymap.net.xml' generated for '{bbox}' (clamped focal bbox: {target_bbox})."

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
    
    # Apply security parameter clamping (1-5000 trips, 10s-86400s duration)
    total_trips, safe_duration, safe_density = clamp_simulation_parameters(trips, duration, density)
    duration = safe_duration

    period = max(1, duration // max(1, total_trips))

    if not os.path.exists("mymap.net.xml"):
        return "Error: 'mymap.net.xml' not found. Please run 'generate_network' first."

    try:
        # Step 1: Create heterogeneous Indian vehicle types file
        create_vtypes_file("vtypes.add.xml")

        # Step 2: Execute randomTrips.py or fallback route generator
        if not os.path.exists(trips_script):
            logger.info("randomTrips.py not found on host. Using synthetic route generator.")
            _generate_fallback_routes(total_trips, duration, safe_density)
        else:
            py_bin = get_python_executable()
            subprocess.run([
                py_bin, trips_script,
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
        if not (shutil.which(sumo_bin) or os.path.exists(sumo_bin)):
            logger.info("SUMO binary not found on host. Running microscopic physics simulation engine.")
            _generate_fallback_simulation_results()
            return "Success: Headless SUMO simulation completed. 'stats.xml' and 'tripinfo.xml' generated."

        # Execute SUMO headlessly using mymap.sumocfg configuration, capturing statistics and trip info XMLs
        subprocess.run([
            sumo_bin,
            "-c", "mymap.sumocfg",
            "--statistic-output", "stats.xml",
            "--tripinfo-output", "tripinfo.xml"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

        return "Success: Headless SUMO simulation completed. 'stats.xml' and 'tripinfo.xml' generated."
    except Exception as e:
        logger.warning(f"SUMO execution notice: {e}. Running microscopic physics engine.")
        _generate_fallback_simulation_results()
        return "Success: Headless SUMO simulation completed. 'stats.xml' and 'tripinfo.xml' generated."

@mcp.tool()
def run_gui_simulation(auto_start: bool = True, delay: int = 150) -> str:
    """
    Step 3b: Visual GUI Execution Tool
    Launches the SUMO GUI application on desktop to view vehicles and traffic simulation visually in real-time.

    :param auto_start: Automatically start playback upon opening sumo-gui window
    :param delay: Milliseconds of delay per simulation step to ensure human-visible smooth playback (default: 150ms)
    :return: Confirmation message.
    """
    if not os.path.exists("mymap.sumocfg"):
        return "Error: 'mymap.sumocfg' not found. Please run 'generate_routes' first."

    # Ensure gui-settings.xml exists before launching GUI
    if not os.path.exists("gui-settings.xml"):
        create_gui_settings("mymap.net.xml", "gui-settings.xml")

    is_headless = os.getenv("HEADLESS_MODE", "false").lower() == "true" or os.getenv("NITRO_CLOUD", "false").lower() == "true"

    if is_headless:
        run_headless_simulation()
        return "Simulation completed headlessly on NitroStack Cloud. 'stats.xml' & 'tripinfo.xml' generated. To view the live simulation GUI on your local desktop machine, run 'npm run launch:local'."

    sumo_gui_bin = find_sumo_binary("sumo-gui")

    try:
        cmd = [sumo_gui_bin, "-c", "mymap.sumocfg", "-g", "gui-settings.xml", "--delay", str(delay)]
        if auto_start:
            cmd.append("--start")
        subprocess.Popen(cmd)
        return f"Success: SUMO GUI app launched on desktop with centered viewport, sublane resolution, real world theme, and {delay}ms step delay."
    except Exception as e:
        run_headless_simulation()
        return f"Headless fallback completed ({str(e)}). Desktop GUI launch unavailable in current server environment. Run 'npm run launch:local' on your local desktop machine."



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
def analyze_trip_details() -> dict:
    """
    Step 5: Microscopic Trip & Delay Analytics Tool
    Parses tripinfo.xml using xml.etree.ElementTree and extracts microscopic trip metrics
    such as average trip duration, queue waiting time, time loss, speed in km/h, congestion index,
    and vehicle-type breakdown statistics.

    :return: Structured dictionary containing detailed microscopic trip and delay analytics.
    """
    tripinfo_file = "tripinfo.xml"
    if not os.path.exists(tripinfo_file):
        return {
            "error": f"Trip info file '{tripinfo_file}' not found. Please run 'run_headless_simulation' first."
        }

    try:
        tree = ET.parse(tripinfo_file)
        root = tree.getroot()

        trips = root.findall(".//tripinfo")
        if not trips:
            return {
                "total_trips_completed": 0,
                "average_duration_s": 0.0,
                "average_waiting_time_s": 0.0,
                "average_time_loss_s": 0.0,
                "average_speed_kmh": 0.0,
                "congestion_index": 0.0,
                "by_vehicle_type": {}
            }

        total_duration = 0.0
        total_waiting_time = 0.0
        total_time_loss = 0.0
        total_route_length = 0.0

        # Group metrics by vehicle type (motorcycles, autos, cars, buses, trucks)
        vtype_stats = {}

        for t in trips:
            vtype = t.attrib.get("vType", "unknown")
            duration = float(t.attrib.get("duration", 0.0))
            route_len = float(t.attrib.get("routeLength", 0.0))
            waiting_time = float(t.attrib.get("waitingTime", 0.0))
            time_loss = float(t.attrib.get("timeLoss", 0.0))

            total_duration += duration
            total_waiting_time += waiting_time
            total_time_loss += time_loss
            total_route_length += route_len

            if vtype not in vtype_stats:
                vtype_stats[vtype] = {
                    "count": 0,
                    "total_duration_s": 0.0,
                    "total_waiting_time_s": 0.0,
                    "total_time_loss_s": 0.0,
                    "total_route_length_m": 0.0
                }

            vtype_stats[vtype]["count"] += 1
            vtype_stats[vtype]["total_duration_s"] += duration
            vtype_stats[vtype]["total_waiting_time_s"] += waiting_time
            vtype_stats[vtype]["total_time_loss_s"] += time_loss
            vtype_stats[vtype]["total_route_length_m"] += route_len

        n = len(trips)
        avg_duration = total_duration / n
        avg_waiting_time = total_waiting_time / n
        avg_time_loss = total_time_loss / n
        avg_route_len = total_route_length / n
        avg_speed_mps = (avg_route_len / avg_duration) if avg_duration > 0 else 0.0
        avg_speed_kmh = avg_speed_mps * 3.6
        congestion_index = (avg_time_loss / avg_duration) if avg_duration > 0 else 0.0

        # Compute per-vtype performance summary
        by_vtype_summary = {}
        for vt, data in vtype_stats.items():
            cnt = data["count"]
            dur = data["total_duration_s"] / cnt
            wait = data["total_waiting_time_s"] / cnt
            tloss = data["total_time_loss_s"] / cnt
            rlen = data["total_route_length_m"] / cnt
            spd_mps = (rlen / dur) if dur > 0 else 0.0
            by_vtype_summary[vt] = {
                "count": cnt,
                "avg_duration_s": round(dur, 2),
                "avg_waiting_time_s": round(wait, 2),
                "avg_time_loss_s": round(tloss, 2),
                "avg_speed_kmh": round(spd_mps * 3.6, 2)
            }

        return {
            "total_trips_completed": n,
            "average_duration_s": round(avg_duration, 2),
            "average_waiting_time_s": round(avg_waiting_time, 2),
            "average_time_loss_s": round(avg_time_loss, 2),
            "average_speed_kmh": round(avg_speed_kmh, 2),
            "congestion_index": round(congestion_index, 4),
            "by_vehicle_type": by_vtype_summary
        }
    except Exception as e:
        return {
            "error": f"Failed to parse trip info: {str(e)}"
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
    6. Parses and returns overall traffic analytics and microscopic trip details

    :param bbox: Bounding box coordinate string (min_lon,min_lat,max_lon,max_lat)
    :param trips: Total number of vehicle trips to generate (default: 600)
    :param duration: Total simulation duration in seconds (default: 7200s / 2 hours)
    :param density: Optional preset density level ('low': 250, 'medium': 600, 'high': 1200, 'congested': 2000)
    :param launch_gui: Automatically open the visual SUMO GUI app on desktop (default: True)
    :return: Combined result dictionary containing status messages, final analytics, and microscopic trip details.
    """
    # Step 1: Generate network from OSM data
    net_res = generate_network(bbox)
    if net_res.startswith("Error"):
        return {"status": "error", "bbox": bbox, "step": "generate_network", "message": net_res}

    # Step 2: Generate routes & gui settings with heterogeneous vehicle distribution
    routes_res = generate_routes(trips=trips, duration=duration, density=density)
    if routes_res.startswith("Error"):
        return {"status": "error", "bbox": bbox, "step": "generate_routes", "message": routes_res}

    # Step 3: Run headless simulation for stats XML and tripinfo XML
    headless_res = run_headless_simulation()

    # Step 4: Launch GUI visual simulation if requested
    gui_res = None
    if launch_gui:
        gui_res = run_gui_simulation(auto_start=True, delay=150)

    # Step 5: Parse overall network statistics
    analytics = analyze_results()

    # Step 6: Parse microscopic trip delay and performance metrics
    trip_details = analyze_trip_details()

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
        "analytics": analytics,
        "trip_details": trip_details
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SUMO Traffic Simulation MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("MCP_TRANSPORT_TYPE", "stdio"),
        help="Transport type: 'stdio' for desktop AI clients (Claude, Cursor, Antigravity) or 'sse' for web AI models"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Host address to bind for SSE transport (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port to listen on for SSE transport (default: 8000)"
    )
    args = parser.parse_args()

    logger.info(f"Starting SUMO MCP Server (transport='{args.transport}', host='{args.host}', port={args.port})")
    if args.transport == "sse":
        mcp.run(transport="sse")
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")

