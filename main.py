"""
Unified Server Launcher & Auto-Discovery Engine for SUMO AI MCP
Combines FastMCP SSE, OAuth 2.1 Redirect Gateway, and Multi-AI Studio into a single command.
"""

import os
import sys
import shutil
import argparse
import logging
from typing import Dict, Any

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
from auth_server import app as fastapi_app
import web_app

# =============================================================================
# ENVIRONMENT & CAPABILITY AUTO-DISCOVERY
# =============================================================================

def run_auto_discovery() -> Dict[str, Any]:
    """Inspects environment, verifies SUMO binaries, and registers available AI models."""
    sumo_home = os.environ.get("SUMO_HOME", "")
    sumo_bin = sumo_server.find_sumo_binary("sumo")
    sumo_gui_bin = sumo_server.find_sumo_binary("sumo-gui")
    netconvert_bin = sumo_server.find_sumo_binary("netconvert")
    python_bin = sumo_server.get_python_executable()

    keys_status = {
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "claude": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "ollama": True,  # Local
        "builtin": True  # Always active
    }

    return {
        "sumo_home": sumo_home,
        "sumo_found": bool(shutil.which(sumo_bin) or os.path.exists(sumo_bin)),
        "sumo_gui_found": bool(shutil.which(sumo_gui_bin) or os.path.exists(sumo_gui_bin)),
        "netconvert_found": bool(shutil.which(netconvert_bin) or os.path.exists(netconvert_bin)),
        "python_bin": python_bin,
        "ai_keys": keys_status
    }


def print_banner(host: str, port: int, mode: str, disco: Dict[str, Any]):
    print("=" * 70)
    print("   TRAFFIC SIMULATION & MULTI-AI MODEL MCP SERVER")
    print(f"   Mode: {mode.upper()} | Python: {sys.version.split()[0]}")
    print("=" * 70)
    print("System Diagnostics & Capability Auto-Discovery:")
    print(f"  [+] SUMO Engine      : {'Available' if disco['sumo_found'] else 'Using Fallback / Cloud'}")
    print(f"  [+] SUMO Desktop GUI : {'Available' if disco['sumo_gui_found'] else 'Headless Mode'}")
    print(f"  [+] Netconvert       : {'Available' if disco['netconvert_found'] else 'Not Found'}")
    print(f"  [+] Python Runtime   : {disco['python_bin']}")

    ai_configured = [k.capitalize() for k, v in disco['ai_keys'].items() if v]
    print(f"  [+] Ready AI Models  : {', '.join(ai_configured)}")
    print("-" * 70)
    if mode in ["web", "all"]:
        print("Web Application Endpoints:")
        print(f"  [*] Web Application Interface : http://{host}:{port}/")
        print(f"  [*] Multi-AI Simulation Studio: http://{host}:{port}/")
        print(f"  [*] Interactive Telemetry & GIS: http://{host}:{port}/#analytics")
        print(f"  [*] API Documentation (Swagger): http://{host}:{port}/docs")
        print(f"  [*] OAuth 2.1 Redirect Portal : http://{host}:{port}/auth/portal")
        print(f"  [*] FastMCP SSE Stream Endpoint: http://{host}:{port}/sse")
        print(f"  [*] MCP Discovery Manifest    : http://{host}:{port}/.well-known/mcp")
    elif mode == "auth":
        print("Auth Gateway Endpoints:")
        print(f"  [*] OAuth 2.1 Redirect Portal  : http://{host}:{port}/auth/portal")
        print(f"  [*] Supported AI Models API    : http://{host}:{port}/auth/models")
    elif mode == "stdio":
        print("FastMCP Running in STDIO Mode:")
        print("  [*] Connected to stdin/stdout for Claude Desktop, Cursor, and Antigravity IDE.")
    print("=" * 70)
    print()


# =============================================================================
# UNIFIED LAUNCHER ENTRYPOINT
# =============================================================================

def start_unified_server():
    parser = argparse.ArgumentParser(description="SUMO AI Web Application & MCP Unified Server Launcher")
    parser.add_argument(
        "--mode",
        choices=["web", "all", "stdio", "sse", "auth"],
        default="web",
        help="Execution mode: 'web' (Full Web Application, default), 'all' (unified Web App + MCP), 'stdio' (Claude/Cursor), 'sse' (FastMCP SSE only), 'auth' (Auth Portal only)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Host address to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port to listen on (default: 8000)"
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Automatically open Web Application in browser upon launch"
    )
    args = parser.parse_args()

    disco = run_auto_discovery()
    print_banner(args.host, args.port, args.mode, disco)

    if args.mode == "stdio":
        sumo_server.mcp.run(transport="stdio")
    elif args.mode == "sse":
        sumo_server.mcp.run(transport="sse")
    else:
        # Web / Unified mode: Run web_app.app
        if args.open_browser:
            def _open():
                import time
                import webbrowser
                time.sleep(1.2)
                webbrowser.open(f"http://{args.host}:{args.port}/")
            import threading
            threading.Thread(target=_open, daemon=True).start()

        import uvicorn
        target_app = web_app.app if args.mode in ["web", "all"] else fastapi_app
        uvicorn.run(target_app, host=args.host, port=args.port)


if __name__ == "__main__":
    start_unified_server()
