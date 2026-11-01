/**
 * SUMO AI Web Application – Frontend Controller & Interactive Engine
 * Handles Leaflet GIS maps, Chart.js telemetry, simulation pipelines, and multi-AI chats.
 */

// Global State
let currentTab = 'studio';
let currentDensity = 'normal';
let currentAiModel = 'builtin';
let currentBbox = '76.9550,10.9950,76.9800,11.0200';
let currentCenter = [11.0075, 76.9675];
let lastSimulationData = null;

// Leaflet Map Instances
let mainMap = null;
let bboxLayer = null;
let centerMarker = null;

let fullscreenMap = null;
let fsBboxLayer = null;
let fsCenterMarker = null;

// Chart.js Instances
let vehicleMixChart = null;
let vehicleSpeedChart = null;

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

    // Load any saved API keys from localStorage
    const savedGemini = localStorage.getItem('sumo_gemini_key');
    if (savedGemini && document.getElementById('apiKeyGemini')) {
        document.getElementById('apiKeyGemini').value = savedGemini;
    }
});

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

    // Invalidate map sizes when switching tabs so Leaflet renders properly
    setTimeout(() => {
        if (mainMap) mainMap.invalidateSize();
        if (tabId === 'map' && !fullscreenMap) {
            initFullscreenMap();
        } else if (fullscreenMap) {
            fullscreenMap.invalidateSize();
        }
    }, 150);
}

// =============================================================================
// LEAFLET MAP INTEGRATION
// =============================================================================

function initLeafletMap() {
    const mapElement = document.getElementById('leafletMap');
    if (!mapElement) return;

    mainMap = L.map('leafletMap').setView(currentCenter, 15);

    // Dark cartographic tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(mainMap);

    updateMapBounds(currentBbox);
}

function initFullscreenMap() {
    const mapElement = document.getElementById('fullscreenLeafletMap');
    if (!mapElement) return;

    fullscreenMap = L.map('fullscreenLeafletMap').setView(currentCenter, 15);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        subdomains: 'abcd',
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
    } catch (err) {
        console.error('Geocoding error:', err);
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
        alert('Please enter a corridor location or bounding box');
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

        // Update KPIs
        updateKpiDashboard(data);

        // Update Charts
        updateCharts(data);

        // Update Trips Table
        updateTripsTable(data);

        // Update Bounding Box on Map
        if (data.bbox) {
            updateMapBounds(data.bbox);
        }

        // Trigger AI Audit automatically
        triggerAiAudit(location, trips, data);

        // Refresh History
        loadHistory();
        loadXmlFile('stats.xml');

    } catch (err) {
        terminal.innerText += `\n❌ Error during simulation: ${err.message}`;
        statusLabel.innerText = 'Status: Error';
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
    const routeLen = data.analytics?.average_route_length || 0.0;

    document.getElementById('kpiInsertion').innerText = `${rate}%`;
    document.getElementById('kpiLoadedSub').innerText = `Loaded: ${loaded} | Inserted: ${inserted}`;
    document.getElementById('kpiSpeed').innerText = `${speed.toFixed(1)} km/h`;
    document.getElementById('kpiDelay').innerText = `${delay.toFixed(1)} s`;
    document.getElementById('kpiCongestion').innerText = `Index: ${cong.toFixed(4)}`;

    // Level of Service (LOS) calculation
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
    alert('API Keys saved securely to local browser storage!');
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
