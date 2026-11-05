/**
 * SUMO AI Web Application – Frontend Controller & Interactive Simulation Engine
 * Version 2.1.0
 * Features:
 * - Leaflet GIS Multi-layer Maps (Dark, Streets, Satellite)
 * - 60 FPS HTML5 Canvas Microscopic 2D Simulation Replay Engine
 * - Digital Twin Scenario Comparison & Before-vs-After Interventions
 * - Environmental Emissions & Carbon Footprint Simulator
 * - Multi-AI Copilot (Gemini, Claude, GPT-4o, Ollama, Built-in)
 * - Server-Sent Events (SSE) Live Progress Streaming
 * - Floating Toast Notifications
 */

// Global App State
let currentTab = 'studio';
let currentDensity = 'normal';
let currentAiModel = 'builtin';
let currentBbox = '76.9550,10.9950,76.9800,11.0200';
let currentCenter = [11.0075, 76.9675];
let lastSimulationData = null;

// Leaflet Map & Layers
let mainMap = null;
let currentTileLayer = null;
let bboxLayer = null;
let centerMarker = null;

let fullscreenMap = null;
let fsBboxLayer = null;
let fsCenterMarker = null;

// Chart.js Instances
let vehicleMixChart = null;
let vehicleSpeedChart = null;

// 2D Canvas Replay Engine State
let replayCanvas = null;
let replayCtx = null;
let replayAnimationId = null;
let isReplayPlaying = false;
let replayTime = 0.0;
let replaySpeed = 1.0;
let replayVehicles = [];
let replayActiveVehicles = [];
let replaySignalPhase = 'GREEN'; // GREEN, AMBER, RED
let replaySignalTimer = 0.0;

// Server-Sent Events
let eventSource = null;

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initLeafletMap();
    initCharts();
    loadPresets();
    loadSystemStatus();
    loadHistory();
    initSseStream();
    loadXmlFile('stats.xml');
    initReplayCanvas();
    loadEmissionsAnalytics();

    // Restore saved API keys from localStorage
    const savedGemini = localStorage.getItem('sumo_gemini_key');
    if (savedGemini && document.getElementById('apiKeyGemini')) {
        document.getElementById('apiKeyGemini').value = savedGemini;
    }
    const savedClaude = localStorage.getItem('sumo_claude_key');
    if (savedClaude && document.getElementById('apiKeyClaude')) {
        document.getElementById('apiKeyClaude').value = savedClaude;
    }
    const savedOpenAi = localStorage.getItem('sumo_openai_key');
    if (savedOpenAi && document.getElementById('apiKeyOpenAi')) {
        document.getElementById('apiKeyOpenAi').value = savedOpenAi;
    }
});

// =============================================================================
// TOAST NOTIFICATIONS
// =============================================================================

function showToast(title, message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');

    toast.innerHTML = `
        <span style="font-size:1.2rem;">${icon}</span>
        <div>
            <div style="font-weight:700; font-size:0.86rem;">${title}</div>
            <div style="font-size:0.78rem; color:var(--text-muted); margin-top:2px;">${message}</div>
        </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 350);
    }, 3500);
}

// =============================================================================
// TAB NAVIGATION
// =============================================================================

function switchTab(tabId) {
    currentTab = tabId;

    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    const activeContent = document.getElementById(`tab-${tabId}`);
    if (activeContent) activeContent.classList.add('active');

    // Invalidate map sizes & canvas dimensions when switching tabs
    setTimeout(() => {
        if (mainMap) mainMap.invalidateSize();
        if (tabId === 'map' && !fullscreenMap) {
            initFullscreenMap();
        } else if (fullscreenMap) {
            fullscreenMap.invalidateSize();
        }
        if (tabId === 'replay') {
            resizeReplayCanvas();
            if (replayVehicles.length === 0) {
                fetchReplayTrajectories();
            }
        }
        if (tabId === 'emissions') {
            loadEmissionsAnalytics();
        }
    }, 150);
}

// =============================================================================
// LEAFLET MAP & MULTI-LAYER TILE SWITCHER
// =============================================================================

function initLeafletMap() {
    const mapElement = document.getElementById('leafletMap');
    if (!mapElement) return;

    mainMap = L.map('leafletMap').setView(currentCenter, 15);
    setMapLayer('dark');
    updateMapBounds(currentBbox);
}

function setMapLayer(layerType) {
    if (!mainMap) return;
    if (currentTileLayer) mainMap.removeLayer(currentTileLayer);

    const tileConfigs = {
        'dark': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        'streets': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'satellite': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    };

    const url = tileConfigs[layerType] || tileConfigs['dark'];
    currentTileLayer = L.tileLayer(url, {
        attribution: '&copy; OpenStreetMap &copy; CARTO / Esri',
        maxZoom: 19
    }).addTo(mainMap);

    showToast('Map Layer Updated', `Switched map view to ${layerType.toUpperCase()}`, 'info');
}

function initFullscreenMap() {
    const mapElement = document.getElementById('fullscreenLeafletMap');
    if (!mapElement) return;

    fullscreenMap = L.map('fullscreenLeafletMap').setView(currentCenter, 15);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        maxZoom: 19
    }).addTo(fullscreenMap);

    updateFullscreenMapBounds(currentBbox);
}

function updateMapBounds(bboxStr) {
    if (!mainMap) return;
    const parts = bboxStr.split(',').map(x => parseFloat(x.trim()));
    if (parts.length !== 4) return;

    const [minLon, minLat, maxLon, maxLat] = parts;
    const bounds = [[minLat, minLon], [maxLat, maxLon]];
    const center = [(minLat + maxLat) / 2.0, (minLon + maxLon) / 2.0];

    if (bboxLayer) mainMap.removeLayer(bboxLayer);
    if (centerMarker) mainMap.removeLayer(centerMarker);

    bboxLayer = L.rectangle(bounds, {
        color: '#38bdf8',
        weight: 2,
        fillColor: '#38bdf8',
        fillOpacity: 0.15,
        dashArray: '4, 4'
    }).addTo(mainMap);

    centerMarker = L.circleMarker(center, {
        radius: 8,
        color: '#38bdf8',
        fillColor: '#818cf8',
        fillOpacity: 0.9
    }).addTo(mainMap).bindPopup(`<b>Simulation Focal Corridor</b><br>${bboxStr}`).openPopup();

    mainMap.fitBounds(bounds, { padding: [20, 20] });

    if (fullscreenMap) {
        updateFullscreenMapBounds(bboxStr);
    }
}

function updateFullscreenMapBounds(bboxStr) {
    if (!fullscreenMap) return;
    const parts = bboxStr.split(',').map(x => parseFloat(x.trim()));
    if (parts.length !== 4) return;

    const [minLat, minLon, maxLat, maxLon] = [parts[1], parts[0], parts[3], parts[2]];
    const bounds = [[minLat, minLon], [maxLat, maxLon]];
    const center = [(minLat + maxLat) / 2.0, (minLon + maxLon) / 2.0];

    if (fsBboxLayer) fullscreenMap.removeLayer(fsBboxLayer);
    if (fsCenterMarker) fullscreenMap.removeLayer(fsCenterMarker);

    fsBboxLayer = L.rectangle(bounds, {
        color: '#38bdf8',
        weight: 2,
        fillColor: '#38bdf8',
        fillOpacity: 0.18,
        dashArray: '4, 4'
    }).addTo(fullscreenMap);

    fsCenterMarker = L.circleMarker(center, {
        radius: 9,
        color: '#38bdf8',
        fillColor: '#a855f7',
        fillOpacity: 0.9
    }).addTo(fullscreenMap).bindPopup(`<b>Corridor Bounding Box</b><br>${bboxStr}`).openPopup();

    fullscreenMap.fitBounds(bounds, { padding: [30, 30] });
}

// =============================================================================
// PRESETS & GEOCODING
// =============================================================================

async function loadPresets() {
    try {
        const res = await fetch('/api/presets');
        const presets = await res.json();
        const container = document.getElementById('presetsContainer');
        if (!container) return;

        container.innerHTML = '';
        presets.forEach(p => {
            const chip = document.createElement('div');
            chip.className = 'preset-chip';
            chip.innerText = `${p.icon} ${p.name.split(' ')[0]}`;
            chip.title = `${p.name} (${p.city})`;
            chip.onclick = () => selectPreset(p, chip);
            container.appendChild(chip);
        });
    } catch (err) {
        console.error('Failed to load corridor presets:', err);
    }
}

function selectPreset(preset, chipEl) {
    document.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
    if (chipEl) chipEl.classList.add('active');

    document.getElementById('simLocation').value = preset.name;
    currentBbox = preset.bbox;
    currentCenter = preset.center;
    updateMapBounds(preset.bbox);
    showToast('Corridor Loaded', `${preset.name} (${preset.city})`, 'info');
}

async function searchAndGeocode() {
    const query = document.getElementById('simLocation').value.trim();
    if (!query) return;

    try {
        const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        currentBbox = data.bbox;
        currentCenter = data.center;
        updateMapBounds(data.bbox);
        showToast('Location Resolved', `Bounds: ${data.bbox}`, 'success');
    } catch (err) {
        showToast('Geocoding Notice', 'Using nearest focal corridor bounds', 'info');
    }
}

// =============================================================================
// FORM & SLIDER CONTROLS
// =============================================================================

function updateSliderVal(sliderId, textId) {
    const val = document.getElementById(sliderId).value;
    document.getElementById(textId).innerText = val;
}

function updateDurationVal() {
    const val = document.getElementById('durSlider').value;
    const hrs = (val / 3600).toFixed(1);
    document.getElementById('durValue').innerText = `${val}s (${hrs} hrs)`;
}

function setDensity(density, el) {
    currentDensity = density;
    document.querySelectorAll('.density-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
}

function updateVehicleMix() {
    const moto = parseInt(document.getElementById('mixMoto').value);
    const auto = parseInt(document.getElementById('mixAuto').value);
    const car = parseInt(document.getElementById('mixCar').value);
    const bus = parseInt(document.getElementById('mixBus').value);
    const truck = parseInt(document.getElementById('mixTruck').value);

    document.getElementById('mixMotoVal').innerText = `${moto}%`;
    document.getElementById('mixAutoVal').innerText = `${auto}%`;
    document.getElementById('mixCarVal').innerText = `${car}%`;
    document.getElementById('mixBusVal').innerText = `${bus}%`;
    document.getElementById('mixTruckVal').innerText = `${truck}%`;

    const total = moto + auto + car + bus + truck;
    if (total > 0) {
        document.getElementById('segMoto').style.width = `${(moto / total) * 100}%`;
        document.getElementById('segAuto').style.width = `${(auto / total) * 100}%`;
        document.getElementById('segCar').style.width = `${(car / total) * 100}%`;
        document.getElementById('segBus').style.width = `${(bus / total) * 100}%`;
        document.getElementById('segTruck').style.width = `${(truck / total) * 100}%`;
    }
}

// =============================================================================
// FULL SIMULATION PIPELINE EXECUTION
// =============================================================================

async function runFullSimulation() {
    const location = document.getElementById('simLocation').value.trim();
    const trips = parseInt(document.getElementById('tripsSlider').value);
    const duration = parseInt(document.getElementById('durSlider').value);
    const launchGui = document.getElementById('launchGuiCheck').checked;
    const btn = document.getElementById('runSimBtn');
    const terminal = document.getElementById('terminalOutput');
    const statusLabel = document.getElementById('execStatus');

    if (!location) {
        showToast('Input Required', 'Please enter a corridor location or bounding box', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span>⏳ Executing Microscopic Simulation...</span>';
    statusLabel.innerText = 'Status: Simulating...';
    terminal.innerText = `[1/5] Geocoding & fetching OpenStreetMap network for '${location}'...\n[2/5] Compiling SUMO mymap.net.xml network...\n[3/5] Synthesizing heterogeneous Indian vehicle routes...\n[4/5] Executing microscopic physics simulation...\n[5/5] Extracting telemetry from stats.xml & tripinfo.xml...`;

    try {
        const res = await fetch('/api/simulation/full', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                bbox: location,
                trips: trips,
                duration: duration,
                density: currentDensity,
                launch_gui: launchGui
            })
        });

        const data = await res.json();
        lastSimulationData = data;

        updateKpiDashboard(data);
        updateCharts(data);
        updateTripsTable(data);

        if (data.bbox) {
            updateMapBounds(data.bbox);
        }

        triggerAiAudit(location, trips, data);
        loadHistory();
        loadXmlFile('stats.xml');
        fetchReplayTrajectories();
        loadEmissionsAnalytics();

        showToast('Simulation Successful', `Completed run for ${location} with ${trips} vehicles (${data.los})`, 'success');

    } catch (err) {
        terminal.innerText += `\n❌ Error during simulation: ${err.message}`;
        statusLabel.innerText = 'Status: Error';
        showToast('Simulation Error', err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>🚀 Run Microscopic Simulation</span>';
    }
}

function updateKpiDashboard(data) {
    const loaded = data.analytics?.total_vehicles_loaded || 0;
    const inserted = data.analytics?.total_vehicles_inserted || 0;
    const rate = loaded > 0 ? ((inserted / loaded) * 100).toFixed(1) : '100.0';
    const speed = data.trip_details?.average_speed_kmh || 0.0;
    const delay = data.trip_details?.average_time_loss_s || 0.0;
    const cong = data.trip_details?.congestion_index || 0.0;

    document.getElementById('kpiInsertion').innerText = `${rate}%`;
    document.getElementById('kpiLoadedSub').innerText = `Loaded: ${loaded} | Inserted: ${inserted}`;
    document.getElementById('kpiSpeed').innerText = `${speed.toFixed(1)} km/h`;
    document.getElementById('kpiDelay').innerText = `${delay.toFixed(1)} s`;
    document.getElementById('kpiCongestion').innerText = `Index: ${cong.toFixed(4)}`;

    let losClass = 'los-b';
    let losText = 'LOS B (Stable Flow)';
    if (delay < 10) { losClass = 'los-a'; losText = 'LOS A (Free Flow)'; }
    else if (delay < 20) { losClass = 'los-b'; losText = 'LOS B (Stable Flow)'; }
    else if (delay < 35) { losClass = 'los-c'; losText = 'LOS C (Fair Flow)'; }
    else if (delay < 55) { losClass = 'los-d'; losText = 'LOS D (Dense Flow)'; }
    else if (delay < 80) { losClass = 'los-e'; losText = 'LOS E (Unstable Flow)'; }
    else { losClass = 'los-f'; losText = 'LOS F (Breakdown)'; }

    const losBadge = document.getElementById('kpiLos');
    losBadge.className = `los-badge ${losClass}`;
    losBadge.innerText = losText;
}

// =============================================================================
// STEP-BY-STEP SIMULATION CONTROLLERS
// =============================================================================

async function runStepNetwork() {
    const location = document.getElementById('simLocation').value.trim() || 'Gandhipuram';
    const terminal = document.getElementById('terminalOutput');
    terminal.innerText += `\n[*] Step 1: Generating network for '${location}'...`;
    try {
        const res = await fetch('/api/simulation/step/network', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bbox: location })
        });
        const data = await res.json();
        terminal.innerText += `\n${data.message}`;
        showToast('Step 1 Complete', 'mymap.net.xml compiled successfully', 'success');
    } catch (e) {
        terminal.innerText += `\n❌ Step 1 Error: ${e.message}`;
    }
}

async function runStepRoutes() {
    const trips = parseInt(document.getElementById('tripsSlider').value);
    const duration = parseInt(document.getElementById('durSlider').value);
    const terminal = document.getElementById('terminalOutput');
    terminal.innerText += `\n[*] Step 2: Generating ${trips} routes over ${duration}s...`;
    try {
        const res = await fetch('/api/simulation/step/routes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trips, duration, density: currentDensity })
        });
        const data = await res.json();
        terminal.innerText += `\n${data.message}`;
        showToast('Step 2 Complete', `${trips} routes synthesized`, 'success');
    } catch (e) {
        terminal.innerText += `\n❌ Step 2 Error: ${e.message}`;
    }
}

async function runStepExecute() {
    const terminal = document.getElementById('terminalOutput');
    terminal.innerText += '\n[*] Step 3: Running headless SUMO simulation...';
    try {
        const res = await fetch('/api/simulation/step/execute', { method: 'POST' });
        const data = await res.json();
        terminal.innerText += `\n${data.message}`;
        showToast('Step 3 Complete', 'Microscopic simulation execution finished', 'success');
        loadXmlFile('stats.xml');
    } catch (e) {
        terminal.innerText += `\n❌ Step 3 Error: ${e.message}`;
    }
}

async function runStepGui() {
    const terminal = document.getElementById('terminalOutput');
    terminal.innerText += '\n[*] Step 3b: Launching Desktop SUMO GUI...';
    try {
        const res = await fetch('/api/simulation/step/gui', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_start: true, delay: 150 })
        });
        const data = await res.json();
        terminal.innerText += `\n${data.message}`;
        showToast('SUMO GUI', 'Desktop visualizer initiated', 'info');
    } catch (e) {
        terminal.innerText += `\n❌ Step 3b Error: ${e.message}`;
    }
}

// =============================================================================
// CHART.JS INTEGRATION
// =============================================================================

function initCharts() {
    const mixCtx = document.getElementById('vehicleMixChart');
    if (mixCtx) {
        vehicleMixChart = new Chart(mixCtx, {
            type: 'doughnut',
            data: {
                labels: ['Motorcycles', 'Autorickshaws', 'Cars', 'Buses', 'Trucks'],
                datasets: [{
                    data: [35, 20, 30, 8, 7],
                    backgroundColor: ['#f87171', '#fbbf24', '#38bdf8', '#34d399', '#c084fc'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#94a3b8', boxWidth: 12 } }
                }
            }
        });
    }

    const speedCtx = document.getElementById('vehicleSpeedChart');
    if (speedCtx) {
        vehicleSpeedChart = new Chart(speedCtx, {
            type: 'bar',
            data: {
                labels: ['Motorcycles', 'Autorickshaws', 'Cars', 'Buses', 'Trucks'],
                datasets: [{
                    label: 'Average Speed (km/h)',
                    data: [36.5, 28.0, 31.5, 21.0, 18.5],
                    backgroundColor: ['#f87171', '#fbbf24', '#38bdf8', '#34d399', '#c084fc'],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                    y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.06)' } }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }
}

function updateCharts(data) {
    if (!data.trip_details || !data.trip_details.by_vehicle_type) return;
    const bvt = data.trip_details.by_vehicle_type;

    const labels = [];
    const counts = [];
    const speeds = [];

    const labelMap = {
        'ind_motorcycle': 'Motorcycles',
        'ind_autorickshaw': 'Autorickshaws',
        'ind_car': 'Cars',
        'ind_bus': 'Buses',
        'ind_truck': 'Trucks'
    };

    for (const [key, val] of Object.entries(bvt)) {
        labels.push(labelMap[key] || key);
        counts.push(val.count || 0);
        speeds.push(val.avg_speed_kmh || 0);
    }

    if (vehicleMixChart) {
        vehicleMixChart.data.labels = labels;
        vehicleMixChart.data.datasets[0].data = counts;
        vehicleMixChart.update();
    }

    if (vehicleSpeedChart) {
        vehicleSpeedChart.data.labels = labels;
        vehicleSpeedChart.data.datasets[0].data = speeds;
        vehicleSpeedChart.update();
    }
}

// =============================================================================
// MICROSCOPIC TRIPS TABLE
// =============================================================================

function updateTripsTable(data) {
    const tbody = document.getElementById('tripsTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';
    const bvt = data.trip_details?.by_vehicle_type || {};

    let index = 1;
    for (const [vtype, stats] of Object.entries(bvt)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>#${index++}</td>
            <td><span class="pill" style="color:var(--accent-cyan); font-weight:700;">${vtype}</span></td>
            <td>${stats.count}</td>
            <td>${stats.avg_speed_kmh?.toFixed(1) || 0} km/h</td>
            <td>${stats.avg_time_loss_s?.toFixed(1) || 0} s</td>
            <td>${stats.avg_waiting_time_s?.toFixed(1) || 0} s</td>
            <td>${stats.avg_duration_s?.toFixed(1) || 0} s</td>
        `;
        tbody.appendChild(tr);
    }
}

// =============================================================================
// 2D CANVAS MICROSCOPIC REPLAY ENGINE
// =============================================================================

function initReplayCanvas() {
    replayCanvas = document.getElementById('replayCanvas');
    if (!replayCanvas) return;
    replayCtx = replayCanvas.getContext('2d');
    resizeReplayCanvas();
    window.addEventListener('resize', resizeReplayCanvas);

    // Click on canvas to inspect vehicle
    replayCanvas.addEventListener('click', handleCanvasClick);
}

function resizeReplayCanvas() {
    if (!replayCanvas) return;
    const rect = replayCanvas.parentElement.getBoundingClientRect();
    replayCanvas.width = rect.width;
    replayCanvas.height = rect.height;
    renderReplayFrame();
}

async function fetchReplayTrajectories() {
    try {
        const res = await fetch('/api/simulation/replay');
        if (!res.ok) return;
        const data = await res.json();
        replayVehicles = data.trajectories || [];
        replayTime = 0.0;
        renderReplayFrame();
    } catch (e) {
        console.error('Failed to load replay trajectories:', e);
    }
}

function toggleReplayPlay() {
    isReplayPlaying = !isReplayPlaying;
    const btn = document.getElementById('replayPlayBtn');
    if (isReplayPlaying) {
        btn.innerHTML = '<span>⏸️ Pause</span>';
        btn.classList.add('active');
        lastTimestamp = performance.now();
        requestAnimationFrame(replayLoop);
    } else {
        btn.innerHTML = '<span>▶️ Play Replay</span>';
        btn.classList.remove('active');
    }
}

let lastTimestamp = 0;

function replayLoop(now) {
    if (!isReplayPlaying) return;
    const dt = (now - lastTimestamp) / 1000.0;
    lastTimestamp = now;

    replayTime += dt * replaySpeed * 2.0; // Scaled time progression
    replaySignalTimer += dt * replaySpeed * 2.0;

    // Dynamic Tuned Signal Phase Cycle
    const cycle = replaySignalTimer % (tunedSignalCycle || 60.0);
    if (cycle < (tunedGreenPhase || 35.0)) {
        replaySignalPhase = 'GREEN';
    } else if (cycle < ((tunedGreenPhase || 35.0) + (tunedAmberPhase || 5.0))) {
        replaySignalPhase = 'AMBER';
    } else {
        replaySignalPhase = 'RED';
    }

    renderReplayFrame();
    requestAnimationFrame(replayLoop);
}

function stepReplayForward() {
    replayTime += 2.0;
    replaySignalTimer += 2.0;
    renderReplayFrame();
}

function resetReplay() {
    replayTime = 0.0;
    replaySignalTimer = 0.0;
    isReplayPlaying = false;
    const btn = document.getElementById('replayPlayBtn');
    if (btn) btn.innerHTML = '<span>▶️ Play Replay</span>';
    renderReplayFrame();
}

function setReplaySpeed(spd, btnEl) {
    replaySpeed = spd;
    document.querySelectorAll('.speed-chip').forEach(c => c.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    showToast('Replay Speed', `Playback set to ${spd}x`, 'info');
}

function renderReplayFrame() {
    if (!replayCtx || !replayCanvas) return;
    const ctx = replayCtx;
    const w = replayCanvas.width;
    const h = replayCanvas.height;

    // Clear Canvas
    ctx.fillStyle = '#090e1a';
    ctx.fillRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const roadWidth = 140;

    // 1. Draw Road Surface
    ctx.fillStyle = '#1e293b';
    // Horizontal corridor
    ctx.fillRect(0, cy - roadWidth / 2, w, roadWidth);
    // Vertical cross arterial
    ctx.fillRect(cx - roadWidth / 2, 0, roadWidth, h);

    // 2. Draw Road Markings
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 2;
    ctx.setLineDash([12, 10]);

    // Horizontal lane dividers
    ctx.beginPath();
    ctx.moveTo(0, cy - roadWidth / 4);
    ctx.lineTo(cx - roadWidth / 2, cy - roadWidth / 4);
    ctx.moveTo(cx + roadWidth / 2, cy - roadWidth / 4);
    ctx.lineTo(w, cy - roadWidth / 4);

    ctx.moveTo(0, cy + roadWidth / 4);
    ctx.lineTo(cx - roadWidth / 2, cy + roadWidth / 4);
    ctx.moveTo(cx + roadWidth / 2, cy + roadWidth / 4);
    ctx.lineTo(w, cy + roadWidth / 4);
    ctx.stroke();

    // Median Barrier
    ctx.strokeStyle = '#fbbf24';
    ctx.lineWidth = 3;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(0, cy);
    ctx.lineTo(cx - roadWidth / 2, cy);
    ctx.moveTo(cx + roadWidth / 2, cy);
    ctx.lineTo(w, cy);
    ctx.stroke();

    // 3. Draw Pedestrian Crosswalks (Zebra)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    const zebraWidth = 12;
    for (let y = cy - roadWidth / 2; y < cy + roadWidth / 2; y += 14) {
        ctx.fillRect(cx - roadWidth / 2 - zebraWidth, y, 8, 8);
        ctx.fillRect(cx + roadWidth / 2 + 4, y, 8, 8);
    }

    // 4. Draw Traffic Signal Lights
    const signalColor = replaySignalPhase === 'GREEN' ? '#22c55e' : (replaySignalPhase === 'AMBER' ? '#f59e0b' : '#ef4444');
    ctx.fillStyle = signalColor;
    ctx.shadowColor = signalColor;
    ctx.shadowBlur = 15;
    ctx.beginPath();
    ctx.arc(cx - roadWidth / 2 - 16, cy - roadWidth / 2 - 12, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + roadWidth / 2 + 16, cy + roadWidth / 2 + 12, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0; // Reset blur

    // Update HUD labels
    document.getElementById('hudTime').innerText = `${replayTime.toFixed(1)}s`;
    document.getElementById('hudSignalPhase').innerText = replaySignalPhase;
    document.getElementById('hudSignalDot').style.background = signalColor;

    // 5. Draw Active Simulated Vehicles
    replayActiveVehicles = [];
    let activeCount = 0;

    replayVehicles.forEach((v, index) => {
        if (replayTime >= v.depart && replayTime <= v.arrival) {
            activeCount++;
            const progress = (replayTime - v.depart) / v.duration;
            const laneOffset = (index % 2 === 0) ? -roadWidth / 4 : roadWidth / 4;

            let vx, vy;
            // Half move West-to-East, half East-to-West
            if (index % 4 < 2) {
                vx = progress * w;
                vy = cy + Math.abs(laneOffset);
            } else {
                vx = w - (progress * w);
                vy = cy - Math.abs(laneOffset);
            }

            // Draw vehicle body
            ctx.fillStyle = v.color || '#38bdf8';
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1;

            let bw = 16, bh = 8;
            if (v.vType === 'ind_motorcycle') { bw = 8; bh = 4; }
            else if (v.vType === 'ind_autorickshaw') { bw = 12; bh = 7; }
            else if (v.vType === 'ind_bus') { bw = 32; bh = 10; }
            else if (v.vType === 'ind_truck') { bw = 28; bh = 10; }

            ctx.fillRect(vx - bw / 2, vy - bh / 2, bw, bh);
            ctx.strokeRect(vx - bw / 2, vy - bh / 2, bw, bh);

            if (selectedVehicleId && v.id === selectedVehicleId) {
                ctx.save();
                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 2.5;
                ctx.shadowColor = '#38bdf8';
                ctx.shadowBlur = 10;
                ctx.beginPath();
                ctx.arc(vx, vy, Math.max(bw, bh) + 6, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            }

            replayActiveVehicles.push({
                x: vx, y: vy, w: bw, h: bh, data: v
            });
        }
    });

    document.getElementById('hudVehicles').innerText = activeCount;
}

let selectedVehicleId = null;
let tunedSignalCycle = 60.0;
let tunedGreenPhase = 35.0;
let tunedAmberPhase = 5.0;

function handleCanvasClick(e) {
    if (!replayCanvas) return;
    const rect = replayCanvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const hit = replayActiveVehicles.find(v => (
        clickX >= v.x - (v.w + 6) && clickX <= v.x + (v.w + 6) &&
        clickY >= v.y - (v.h + 6) && clickY <= v.y + (v.h + 6)
    ));

    const tooltip = document.getElementById('vehicleTooltip');
    if (hit) {
        selectedVehicleId = hit.data.id;
        tooltip.style.left = `${clickX + 15}px`;
        tooltip.style.top = `${clickY}px`;
        tooltip.style.display = 'block';
        tooltip.innerHTML = `
            <div style="font-weight:700; color:#38bdf8; margin-bottom:4px;">🚘 Vehicle #${hit.data.id} (${hit.data.vType})</div>
            <div>Velocity: <b>${hit.data.speed_kmh} km/h</b></div>
            <div>Time Loss: <b>${hit.data.timeLoss}s</b> | Idle: <b>${hit.data.waitingTime}s</b></div>
            <div>Emission Rate: <b>${hit.data.co2_rate_gh || 120} g/h CO2</b></div>
            <div>Status: <span style="color:${hit.data.efficiency === 'Optimal' ? '#34d399' : '#fbbf24'};">${hit.data.efficiency || 'Active'}</span></div>
        `;
    } else {
        selectedVehicleId = null;
        tooltip.style.display = 'none';
    }
}

async function applySignalTuning() {
    const cycle = parseInt(document.getElementById('tuneCycle').value) || 60;
    const split = parseInt(document.getElementById('tuneSplit').value) || 55;
    const amber = parseInt(document.getElementById('tuneAmber').value) || 5;
    const ped = document.getElementById('tunePed')?.checked || false;

    try {
        const res = await fetch('/api/simulation/signals/tune', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cycle_length_s: cycle,
                green_split_pct: split,
                amber_s: amber,
                pedestrian_scramble: ped
            })
        });

        const data = await res.json();
        if (data.status === 'success') {
            tunedSignalCycle = data.cycle_length_s;
            tunedGreenPhase = data.green_phase_s;
            tunedAmberPhase = data.amber_phase_s;

            const badge = document.getElementById('tuneResultBadge');
            if (badge) {
                badge.style.display = 'block';
                badge.innerHTML = `
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px; flex-wrap:wrap; gap:8px;">
                        <span style="color:#34d399; font-weight:700;">▲ Predicted Velocity Gain: +${data.speed_gain_pct}%</span>
                        <span style="color:#38bdf8; font-weight:700;">Capacity: ${data.throughput_capacity_vph} veh/hr</span>
                    </div>
                    <div style="color:#94a3b8; font-size:0.8rem;">${data.recommendation}</div>
                `;
            }
            showToast('Signal Optimization Applied', `Cycle: ${cycle}s | Green: ${data.green_phase_s}s`, 'success');
        }
    } catch (e) {
        console.error('Signal tuning failed:', e);
        showToast('Error', 'Failed to tune signals', 'error');
    }
}

async function testApiEndpoint(url) {
    const out = document.getElementById('apiPlaygroundOutput');
    if (!out) return;
    out.style.display = 'block';
    out.innerText = `Fetching ${url}...`;
    try {
        const res = await fetch(url);
        const data = await res.json();
        out.innerText = JSON.stringify(data, null, 2);
    } catch (e) {
        out.innerText = `Error: ${e.message}`;
    }
}

// =============================================================================
// SCENARIO COMPARISON & DIGITAL TWIN
// =============================================================================

async function selectIntervention(interventionId, btnEl) {
    document.querySelectorAll('.intervention-tab').forEach(t => t.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');

    const location = document.getElementById('simLocation').value || 'Gandhipuram';

    try {
        const res = await fetch('/api/simulation/compare', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                bbox: location,
                intervention: interventionId
            })
        });

        const data = await res.json();
        updateComparisonView(data);
        showToast('Digital Twin Scenario', `Applied: ${data.intervention_name}`, 'success');
    } catch (e) {
        console.error('Failed to compare scenarios:', e);
    }
}

function updateComparisonView(data) {
    document.getElementById('cmpBaseSpeed').innerText = data.baseline.speed_kmh;
    document.getElementById('cmpBaseDelay').innerText = `${data.baseline.delay_s}s`;
    document.getElementById('cmpBaseLos').innerText = data.baseline.los;

    document.getElementById('cmpProposedTitle').innerText = data.intervention_name;
    document.getElementById('cmpProposedSpeed').innerText = data.proposed.speed_kmh;
    document.getElementById('cmpProposedDelay').innerText = `${data.proposed.delay_s}s`;
    document.getElementById('cmpProposedLos').innerText = data.proposed.los;

    document.getElementById('cmpCostTier').innerText = data.cost_tier;
    document.getElementById('cmpRationale').innerText = data.engineering_rationale;

    document.getElementById('cmpDeltaSpeed').innerText = `▲ +${data.deltas.speed_change_pct}% Velocity`;
    document.getElementById('cmpDeltaDelay').innerText = `▼ ${data.deltas.delay_reduction_pct}% Time Loss`;
    document.getElementById('cmpDeltaFuel').innerText = `🌱 -${data.deltas.fuel_savings_pct}% Fuel Loss`;
    document.getElementById('cmpDeltaCo2').innerText = `🍃 -${data.deltas.co2_offset_kg} kg CO2`;
}

// =============================================================================
// ECO & EMISSIONS ANALYTICS
// =============================================================================

async function loadEmissionsAnalytics() {
    try {
        const res = await fetch('/api/analytics/emissions');
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById('ecoCo2Val').innerText = `${data.total_co2_kg} kg`;
        document.getElementById('ecoFuelVal').innerText = `${data.fuel_wasted_liters} L`;
        document.getElementById('ecoScoreBadge').innerText = data.green_score;

        window._lastEmissions = data;
        updateEvProjection();
    } catch (e) {
        console.error('Failed to load emissions analytics:', e);
    }
}

function updateEvProjection() {
    const slider = document.getElementById('evSlider');
    if (!slider) return;
    const pct = parseInt(slider.value);
    document.getElementById('evPercentVal').innerText = `${pct}% EV Adoption`;

    const baseCo2 = window._lastEmissions?.total_co2_kg || 148.2;
    const factor = 1.0 - (pct / 100.0) * 0.90; // EVs reduce ~90% tailpipe emissions
    const projected = (baseCo2 * factor).toFixed(1);
    const saved = (baseCo2 - projected).toFixed(1);

    document.getElementById('evCo2Projected').innerText = `${projected} kg`;
    document.getElementById('evCo2Saved').innerText = `-${saved} kg (-${Math.round((pct * 0.9))}%)`;
}

// =============================================================================
// MULTI-AI COPILOT CHAT
// =============================================================================

function selectAiModel(modelId) {
    currentAiModel = modelId;
    document.querySelectorAll('.ai-tab-chip').forEach(c => c.classList.remove('active'));
    event.currentTarget.classList.add('active');

    const names = {
        'builtin': 'Built-in Traffic Engineering Expert',
        'gemini': 'Google Gemini 1.5/2.0 Flash',
        'claude': 'Anthropic Claude 3.5 Sonnet',
        'gpt4': 'OpenAI GPT-4o',
        'ollama': 'Ollama Local LLM'
    };
    document.getElementById('activeAiModelName').innerText = names[modelId] || modelId;
    showToast('AI Model Selected', names[modelId] || modelId, 'info');
}

function setQuickPrompt(promptText) {
    document.getElementById('chatInput').value = promptText;
    sendAiMessage();
}

async function triggerAiAudit(location, trips, simData) {
    const terminal = document.getElementById('terminalOutput');
    const statusLabel = document.getElementById('execStatus');
    statusLabel.innerText = 'Status: AI Generating Audit...';

    try {
        const apiKey = getApiKeyForModel(currentAiModel);
        const res = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: currentAiModel,
                prompt: `Perform an in-depth urban traffic engineering audit for corridor '${location}' with ${trips} vehicles under Indian mixed traffic conditions.`,
                simulation_data: simData,
                api_key: apiKey
            })
        });

        const data = await res.json();
        terminal.innerText = data.response || JSON.stringify(data, null, 2);
        statusLabel.innerText = 'Status: Complete';

        appendChatMessage('ai', data.response || 'Simulation telemetry audit completed.');
    } catch (err) {
        terminal.innerText += `\n❌ AI Audit error: ${err.message}`;
        statusLabel.innerText = 'Status: Ready';
    }
}

async function sendAiMessage() {
    const input = document.getElementById('chatInput');
    const prompt = input.value.trim();
    if (!prompt) return;

    input.value = '';
    appendChatMessage('user', prompt);

    const thinkingId = appendChatMessage('ai', 'Thinking and inspecting simulation telemetry...');

    try {
        const apiKey = getApiKeyForModel(currentAiModel);
        const res = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: currentAiModel,
                prompt: prompt,
                simulation_data: lastSimulationData,
                api_key: apiKey
            })
        });

        const data = await res.json();
        const thinkingBubble = document.getElementById(thinkingId);
        if (thinkingBubble) {
            thinkingBubble.innerText = data.response || JSON.stringify(data, null, 2);
        }
    } catch (err) {
        const thinkingBubble = document.getElementById(thinkingId);
        if (thinkingBubble) {
            thinkingBubble.innerText = `❌ Error: ${err.message}`;
        }
    }
}

function appendChatMessage(sender, text) {
    const thread = document.getElementById('chatThread');
    if (!thread) return;

    const id = `msg_${Date.now()}_${Math.random()}`;
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${sender}`;
    bubble.id = id;
    bubble.innerText = text;
    thread.appendChild(bubble);
    thread.scrollTop = thread.scrollHeight;
    return id;
}

function getApiKeyForModel(model) {
    if (model === 'gemini') return localStorage.getItem('sumo_gemini_key') || null;
    if (model === 'claude') return localStorage.getItem('sumo_claude_key') || null;
    if (model === 'gpt4') return localStorage.getItem('sumo_openai_key') || null;
    return null;
}

function saveApiKeys() {
    const gemini = document.getElementById('apiKeyGemini').value.trim();
    const claude = document.getElementById('apiKeyClaude').value.trim();
    const openai = document.getElementById('apiKeyOpenAi').value.trim();

    if (gemini) localStorage.setItem('sumo_gemini_key', gemini);
    if (claude) localStorage.setItem('sumo_claude_key', claude);
    if (openai) localStorage.setItem('sumo_openai_key', openai);

    closeModal('apiKeyModal');
    showToast('Credentials Saved', 'API Keys securely stored in local browser storage', 'success');
}

// =============================================================================
// XML FILE INSPECTOR
// =============================================================================

async function loadXmlFile(filename) {
    document.querySelectorAll('.file-tab').forEach(t => t.classList.remove('active'));
    const activeTab = document.querySelector(`.file-tab[data-file="${filename}"]`);
    if (activeTab) activeTab.classList.add('active');

    const viewer = document.getElementById('xmlViewer');
    if (!viewer) return;

    viewer.innerText = `Loading ${filename}...`;

    try {
        const res = await fetch(`/api/analytics/xml/${filename}`);
        if (!res.ok) {
            viewer.innerText = `File '${filename}' has not been generated yet. Run a simulation to create it.`;
            return;
        }
        const data = await res.json();
        viewer.innerText = data.content;
    } catch (err) {
        viewer.innerText = `Error loading file: ${err.message}`;
    }
}

// =============================================================================
// SIMULATION HISTORY
// =============================================================================

async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const runs = await res.json();
        const container = document.getElementById('historyListContainer');
        if (!container) return;

        if (runs.length === 0) {
            container.innerHTML = '<p style="color:var(--text-muted); font-size:0.85rem;">No previous simulation runs yet. Run a simulation above to start your log.</p>';
            return;
        }

        container.innerHTML = '';
        runs.forEach(r => {
            const card = document.createElement('div');
            card.className = 'history-card';
            card.innerHTML = `
                <div class="history-meta">
                    <div class="history-title">${r.location}</div>
                    <div class="history-time">${r.formatted_time || 'Just now'} | ${r.trips} vehicles | ${r.duration}s</div>
                </div>
                <div class="history-kpis">
                    <div class="history-kpi-item">
                        <span class="history-kpi-val" style="color:var(--accent-cyan);">${r.speed_kmh}</span>
                        <span class="history-kpi-lbl">km/h</span>
                    </div>
                    <div class="history-kpi-item">
                        <span class="history-kpi-val" style="color:var(--accent-amber);">${r.time_loss_s}s</span>
                        <span class="history-kpi-lbl">Delay</span>
                    </div>
                    <div class="history-kpi-item">
                        <span class="history-kpi-val">${r.los || 'LOS B'}</span>
                        <span class="history-kpi-lbl">Level of Service</span>
                    </div>
                    <button class="step-btn" onclick="restoreHistoryRun('${r.id}')">View</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        console.error('Failed to load simulation history:', err);
    }
}

function restoreHistoryRun(runId) {
    fetch('/api/history')
        .then(res => res.json())
        .then(runs => {
            const run = runs.find(r => r.id === runId);
            if (run) {
                lastSimulationData = run;
                updateKpiDashboard(run);
                updateCharts(run);
                if (run.bbox) updateMapBounds(run.bbox);
                switchTab('studio');
                showToast('Scenario Restored', `Loaded ${run.location}`, 'info');
            }
        });
}

// =============================================================================
// SYSTEM DIAGNOSTICS & SSE STREAM
// =============================================================================

async function loadSystemStatus() {
    try {
        const res = await fetch('/api/system/status');
        const status = await res.json();
        const badge = document.getElementById('systemStatusBadge');
        if (badge) {
            badge.innerText = status.sumo_engine.mode;
        }
    } catch (err) {
        console.error('Failed to load system status:', err);
    }
}

function initSseStream() {
    if (window.EventSource) {
        eventSource = new EventSource('/api/stream/events');
        eventSource.addEventListener('simulation_event', (e) => {
            const eventData = JSON.parse(e.data);
            console.log('SSE Simulation Event:', eventData);
        });
    }
}

// =============================================================================
// MODALS
// =============================================================================

function openModal(modalId) {
    const m = document.getElementById(modalId);
    if (m) m.classList.add('active');
}

function closeModal(modalId) {
    const m = document.getElementById(modalId);
    if (m) m.classList.remove('active');
}
