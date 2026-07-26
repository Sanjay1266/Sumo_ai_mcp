import os
import sys
import time
import xml.etree.ElementTree as ET
from mcp.server.fastmcp import FastMCP
import sumo_server

# Initialize FastMCP server instance for SUMO Simulation Test Suite
mcp = FastMCP("SUMO Traffic Simulation Test Server")


@mcp.tool()
def test_geocoder(locations: list[str] = None) -> dict:
    """
    Test Tool 1: Geocoder Validation
    Tests place-name geocoding, preset lookups, coordinate bounding box clamping, and numerical format.

    :param locations: Optional list of location names to test.
    :return: Test results dictionary containing status, details, and pass/fail summary.
    """
    test_locations = locations or ["Erode City Center", "Ettimadai", "Salem", "Coimbatore", "Chennai", "Gandhipuram", "Peelamedu", "RS Puram", "Ukkadam", "Amrita"]
    results = []
    passed = 0
    failed = 0

    for loc in test_locations:
        try:
            bbox = sumo_server.resolve_location_to_bbox(loc)
            parts = bbox.split(',')
            if len(parts) != 4:
                raise ValueError(f"Expected 4 comma-separated values, got: {bbox}")
            floats = [float(p) for p in parts]
            # Ensure min_lon < max_lon and min_lat < max_lat
            if floats[0] >= floats[2] or floats[1] >= floats[3]:
                raise ValueError(f"Invalid coordinate bounds in bbox: {bbox}")
            
            results.append({
                "location": loc,
                "resolved_bbox": bbox,
                "status": "PASSED"
            })
            passed += 1
        except Exception as e:
            results.append({
                "location": loc,
                "error": str(e),
                "status": "FAILED"
            })
            failed += 1

    return {
        "test_name": "Geocoder Validation Test",
        "total_tests": len(test_locations),
        "passed": passed,
        "failed": failed,
        "overall_status": "PASSED" if failed == 0 else "FAILED",
        "details": results
    }


@mcp.tool()
def test_network_generation(location: str = "Salem") -> dict:
    """
    Test Tool 2: Network Generation Test
    Validates map retrieval from OSM and netconvert compilation into mymap.net.xml.

    :param location: Location or bounding box to test network generation for (default: 'Salem')
    :return: Test results dictionary.
    """
    start_time = time.time()
    res_msg = sumo_server.generate_network(location)
    elapsed = time.time() - start_time

    net_exists = os.path.exists("mymap.net.xml")
    net_size = os.path.getsize("mymap.net.xml") if net_exists else 0
    is_valid = net_exists and net_size > 0 and not res_msg.startswith("Error")

    return {
        "test_name": "Network Generation Test",
        "location": location,
        "net_file_exists": net_exists,
        "net_file_size_bytes": net_size,
        "execution_time_seconds": round(elapsed, 2),
        "server_response": res_msg,
        "overall_status": "PASSED" if is_valid else "FAILED"
    }


@mcp.tool()
def test_route_generation(trips: int = 100, duration: int = 3600) -> dict:
    """
    Test Tool 3: Route Generation Test
    Validates randomTrips.py execution, vehicle type distribution (vtypes.add.xml), sublane config, and mymap.sumocfg generation.

    :param trips: Total trips to generate (default: 100)
    :param duration: Total simulation duration in seconds (default: 3600)
    :return: Test results dictionary.
    """
    if not os.path.exists("mymap.net.xml"):
        return {
            "test_name": "Route Generation Test",
            "overall_status": "FAILED",
            "error": "'mymap.net.xml' is missing. Please run test_network_generation first."
        }

    start_time = time.time()
    res_msg = sumo_server.generate_routes(trips=trips, duration=duration)
    elapsed = time.time() - start_time

    rou_exists = os.path.exists("mymap.rou.xml")
    vtypes_exists = os.path.exists("vtypes.add.xml")
    cfg_exists = os.path.exists("mymap.sumocfg")
    gui_settings_exists = os.path.exists("gui-settings.xml")

    is_valid = rou_exists and vtypes_exists and cfg_exists and gui_settings_exists and not res_msg.startswith("Error")

    return {
        "test_name": "Route Generation Test",
        "trips": trips,
        "duration": duration,
        "rou_file_exists": rou_exists,
        "vtypes_file_exists": vtypes_exists,
        "sumocfg_file_exists": cfg_exists,
        "gui_settings_exists": gui_settings_exists,
        "execution_time_seconds": round(elapsed, 2),
        "server_response": res_msg,
        "overall_status": "PASSED" if is_valid else "FAILED"
    }


@mcp.tool()
def test_simulation_execution() -> dict:
    """
    Test Tool 4: Headless Simulation Execution Test
    Executes headless SUMO simulation and verifies output reports stats.xml and tripinfo.xml.

    :return: Test results dictionary.
    """
    if not os.path.exists("mymap.sumocfg"):
        return {
            "test_name": "Headless Simulation Execution Test",
            "overall_status": "FAILED",
            "error": "'mymap.sumocfg' is missing. Please run test_route_generation first."
        }

    start_time = time.time()
    res_msg = sumo_server.run_headless_simulation()
    elapsed = time.time() - start_time

    stats_exists = os.path.exists("stats.xml")
    tripinfo_exists = os.path.exists("tripinfo.xml")
    is_valid = stats_exists and tripinfo_exists and not res_msg.startswith("Error")

    return {
        "test_name": "Headless Simulation Execution Test",
        "stats_file_exists": stats_exists,
        "tripinfo_file_exists": tripinfo_exists,
        "execution_time_seconds": round(elapsed, 2),
        "server_response": res_msg,
        "overall_status": "PASSED" if is_valid else "FAILED"
    }


@mcp.tool()
def test_analytics_truthfulness() -> dict:
    """
    Test Tool 5: Analytics Truthfulness Audit Test
    Parses stats.xml independently and cross-checks loaded, inserted, and avg route length metrics against analyze_results().

    :return: Test results dictionary with metric verification details.
    """
    stats_file = "stats.xml"
    if not os.path.exists(stats_file):
        return {
            "test_name": "Analytics Truthfulness Audit Test",
            "overall_status": "FAILED",
            "error": f"Statistics file '{stats_file}' missing. Please run test_simulation_execution first."
        }

    reported = sumo_server.analyze_results()
    if "error" in reported:
        return {
            "test_name": "Analytics Truthfulness Audit Test",
            "overall_status": "FAILED",
            "error": reported["error"]
        }

    try:
        tree = ET.parse(stats_file)
        root = tree.getroot()
        vehicles_elem = root.find(".//vehicles")
        trip_stats_elem = root.find(".//vehicleTripStatistics")

        actual_loaded = int(vehicles_elem.attrib.get("loaded", 0)) if vehicles_elem is not None else 0
        actual_inserted = int(vehicles_elem.attrib.get("inserted", 0)) if vehicles_elem is not None else 0
        
        actual_route_length = 0.0
        if trip_stats_elem is not None:
            if "routeLength" in trip_stats_elem.attrib:
                actual_route_length = float(trip_stats_elem.attrib["routeLength"])
            elif "avgRouteLength" in trip_stats_elem.attrib:
                actual_route_length = float(trip_stats_elem.attrib["avgRouteLength"])

        loaded_match = (actual_loaded == reported.get("total_vehicles_loaded"))
        inserted_match = (actual_inserted == reported.get("total_vehicles_inserted"))
        length_match = (abs(actual_route_length - reported.get("average_route_length", 0.0)) < 0.01)

        all_passed = loaded_match and inserted_match and length_match

        return {
            "test_name": "Analytics Truthfulness Audit Test",
            "metrics": {
                "total_vehicles_loaded": {
                    "actual_xml": actual_loaded,
                    "tool_reported": reported.get("total_vehicles_loaded"),
                    "match": loaded_match
                },
                "total_vehicles_inserted": {
                    "actual_xml": actual_inserted,
                    "tool_reported": reported.get("total_vehicles_inserted"),
                    "match": inserted_match
                },
                "average_route_length": {
                    "actual_xml": round(actual_route_length, 2),
                    "tool_reported": round(reported.get("average_route_length", 0.0), 2),
                    "match": length_match
                }
            },
            "overall_status": "PASSED" if all_passed else "FAILED"
        }
    except Exception as e:
        return {
            "test_name": "Analytics Truthfulness Audit Test",
            "overall_status": "FAILED",
            "error": str(e)
        }


@mcp.tool()
def run_all_test_cases(location: str = "Salem", trips: int = 100, duration: int = 3600) -> dict:
    """
    Master Test Suite Tool
    Executes all 5 test cases end-to-end (Geocoder, Network Gen, Route Gen, Simulation Execution, Analytics Truthfulness Audit) and returns a complete test summary report.

    :param location: Location or bounding box to test (default: 'Salem')
    :param trips: Total trips to simulate during test (default: 100)
    :param duration: Total duration in seconds (default: 3600)
    :return: Comprehensive test suite results.
    """
    suite_start = time.time()

    geo_res = test_geocoder()
    net_res = test_network_generation(location=location)
    route_res = test_route_generation(trips=trips, duration=duration)
    sim_res = test_simulation_execution()
    audit_res = test_analytics_truthfulness()

    total_suite_time = round(time.time() - suite_start, 2)

    all_tests = [geo_res, net_res, route_res, sim_res, audit_res]
    total_count = len(all_tests)
    passed_count = sum(1 for t in all_tests if t.get("overall_status") == "PASSED")
    failed_count = total_count - passed_count

    return {
        "suite_name": "SUMO Simulation Master Test Suite",
        "total_test_cases": total_count,
        "passed_test_cases": passed_count,
        "failed_test_cases": failed_count,
        "total_execution_time_seconds": total_suite_time,
        "overall_suite_status": "PASSED" if failed_count == 0 else "FAILED",
        "test_case_results": {
            "geocoder_test": geo_res,
            "network_generation_test": net_res,
            "route_generation_test": route_res,
            "simulation_execution_test": sim_res,
            "analytics_truthfulness_test": audit_res
        }
    }


if __name__ == "__main__":
    mcp.run()
