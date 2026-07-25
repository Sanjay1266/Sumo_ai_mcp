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


@mcp.tool()
def generate_network(bbox: str) -> str:
    """
    Step 1: Network Generation Tool
    Downloads OpenStreetMap data using a bounding box and converts it into a SUMO network file (.net.xml).

    :param bbox: Bounding box coordinate string, e.g. '13.37,52.51,13.38,52.52' (min_lon,min_lat,max_lon,max_lat)
    :return: Confirmation message when mymap.net.xml is created.
    """
    osm_script = find_sumo_script("osmGet.py")
    netconvert_bin = find_sumo_binary("netconvert")

    try:
        # Execute osmGet.py to download map data for given bounding box and prefix 'mymap'
        subprocess.run([sys.executable, osm_script, "-b", bbox, "-p", "mymap"], check=True)

        # Detect generated OSM file (e.g. mymap_bbox.osm.xml or mymap.osm)
        osm_files = [f for f in os.listdir(".") if f.startswith("mymap") and (f.endswith(".osm") or f.endswith(".osm.xml"))]
        osm_input = ",".join(osm_files) if osm_files else "mymap.osm"

        # Execute netconvert to convert downloaded OpenStreetMap file into SUMO XML network format
        subprocess.run([netconvert_bin, "--osm-files", osm_input, "-o", "mymap.net.xml"], check=True)

        return "Success: Network file 'mymap.net.xml' is ready."
    except subprocess.CalledProcessError as e:
        return f"Error generating network: Subprocess exited with code {e.returncode}"
    except Exception as e:
        return f"Error generating network: {str(e)}"


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
    <vehicles vehicleScale="3.5"/>
</viewsettings>"""

    with open(gui_settings_file, "w", encoding="utf-8") as f:
        f.write(gui_xml)


@mcp.tool()
def generate_routes(trips: int = 200, duration: int = 7200) -> str:
    """
    Step 2: Route Generation Tool
    Generates random trip routes for the SUMO network and programmatically creates the sumocfg file.

    :param trips: Total number of vehicles/trips to generate across the simulation duration
    :param duration: Total simulation duration in seconds (default: 7200 seconds / 2 hours)
    :return: Confirmation message when mymap.sumocfg is created.
    """
    trips_script = find_sumo_script("randomTrips.py")
    period = max(1, duration // max(1, trips))

    if not os.path.exists("mymap.net.xml"):
        return "Error: 'mymap.net.xml' not found. Please run 'generate_network' first."

    try:
        # Execute randomTrips.py to generate random routes on the network over specified duration
        subprocess.run([
            sys.executable, trips_script,
            "-n", "mymap.net.xml",
            "-e", str(duration),
            "-p", str(period),
            "-l",
            "-r", "mymap.rou.xml"
        ], check=True)

        # Generate GUI visual enhancement settings file
        create_gui_settings("mymap.net.xml", "gui-settings.xml")

        # Programmatically create mymap.sumocfg XML file referencing network, route, and gui-settings files
        sumocfg_content = f"""<configuration>
    <input>
        <net-file value="mymap.net.xml"/>
        <route-files value="mymap.rou.xml"/>
        <gui-settings-file value="gui-settings.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="{duration}"/>
    </time>
</configuration>"""

        with open("mymap.sumocfg", "w", encoding="utf-8") as f:
            f.write(sumocfg_content)

        return "Success: SUMO configuration file 'mymap.sumocfg' and visual 'gui-settings.xml' are ready."
    except subprocess.CalledProcessError as e:
        return f"Error generating routes: Subprocess exited with code {e.returncode}"
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
        ], check=True)

        return "Success: Headless SUMO simulation completed. 'stats.xml' and 'tripinfo.xml' generated."
    except subprocess.CalledProcessError as e:
        return f"Error running simulation: Subprocess exited with code {e.returncode}"
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


if __name__ == "__main__":
    mcp.run()
