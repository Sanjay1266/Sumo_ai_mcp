# 🚦 SUMO MCP – AI-Powered Traffic Simulation Platform

SUMO MCP is an intelligent traffic simulation platform that integrates **SUMO (Simulation of Urban Mobility)** with the **Model Context Protocol (MCP)**. Instead of manually configuring simulation files, users can interact with the simulator through natural language while the MCP server orchestrates the complete workflow.

The project automates the entire simulation pipeline including network generation, route creation, simulation execution, visualization, and traffic analytics.

---

# Features

- Automatic OpenStreetMap network generation
- Random traffic route generation
- Indian heterogeneous vehicle simulation
- Headless and GUI simulation modes
- Traffic statistics and analytics
- MCP Tools, Resources, and Prompts support
- AI-assisted traffic simulation workflow
- Location-based and coordinate-based simulations

---

# Project Architecture

```
                User
                  │
                  ▼
          AI Assistant (LLM)
                  │
                  ▼
             MCP Prompt
                  │
                  ▼
          MCP Tool Execution
                  │
 ┌────────────────┼────────────────┐
 │                │                │
 ▼                ▼                ▼
Generate      Generate         Run SUMO
Network        Routes          Simulation
 │                │                │
 └────────────────┼────────────────┘
                  ▼
         Traffic Analytics
                  │
                  ▼
           XML Resources
                  │
                  ▼
             AI Response
```

---

# Project Structure

```
SUMO_mcp/

├── src/
│   ├── sumo.tools.ts
│   ├── sumo.prompts.ts
│   ├── sumo.resources.ts
│   └── sumo.module.ts
│
├── mymap.net.xml
├── mymap.rou.xml
├── mymap.sumocfg
├── gui-settings.xml
├── stats.xml
├── tripinfo.xml
│
├── README.md
└── package.json
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/username/SUMO_mcp.git

cd SUMO_mcp
```

## Install Dependencies

```bash
npm install
```

## Install Python Dependencies

```bash
pip install sumolib
pip install traci
```

## Install SUMO

Download SUMO

https://sumo.dlr.de

Verify installation

```bash
sumo --version
```

---

# Environment Setup

Create a `.env` file.

```env
SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo
PATH=%SUMO_HOME%\bin
```

Verify

```bash
echo %SUMO_HOME%
```

---

# Usage

## Generate Network

```
Generate network for Coimbatore
```

or

```
Generate network for Ettimadai
```

---

## Generate Routes

```
Generate 1200 trips
```

---

## Run Headless Simulation

```
Run simulation
```

---

## Launch GUI

```
Open simulation GUI
```

---

## Analyze Results

```
Analyze latest traffic simulation
```

---

## Run Complete Pipeline

```
Run complete simulation for Coimbatore with 800 trips
```

---

# Available MCP Tools

| Tool | Description |
|------|-------------|
| generate_network | Downloads OSM data and builds SUMO network |
| generate_routes | Generates heterogeneous traffic routes |
| run_headless_simulation | Executes simulation in CLI |
| run_gui_simulation | Opens SUMO GUI |
| analyze_results | Extracts traffic statistics |
| run_full_simulation | Executes the complete workflow |

---

# Available Resources

| Resource | Description |
|-----------|-------------|
| sumo://stats | Latest simulation statistics |
| sumo://tripinfo | Vehicle trip information |
| sumo://network | Generated road network |
| sumo://config | SUMO configuration |

---

# Example AI Prompts

```
Run simulation for Bangalore
```

```
Generate heavy traffic in Coimbatore
```

```
Analyze congestion
```

```
Launch GUI simulation
```

```
Generate routes for 2000 vehicles
```

---

# Output Files

- mymap.net.xml
- mymap.rou.xml
- mymap.sumocfg
- stats.xml
- tripinfo.xml
- gui-settings.xml

---

# Future Enhancements

- Traffic signal optimization
- Heatmap visualization
- Emergency vehicle routing
- AI congestion prediction
- Smart city digital twin integration