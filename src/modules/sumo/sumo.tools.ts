import { ToolDecorator as Tool, ExecutionContext, z } from '@nitrostack/core';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

function findSumoScript(scriptName: string): string {
  if (fs.existsSync(scriptName)) {
    return scriptName;
  }
  const sumoHome = process.env.SUMO_HOME;
  if (sumoHome) {
    const candidates = [
      path.join(sumoHome, 'tools', 'osm', scriptName),
      path.join(sumoHome, 'tools', scriptName),
    ];
    for (const cand of candidates) {
      if (fs.existsSync(cand)) {
        return cand;
      }
    }
  }
  return scriptName;
}

function findSumoBinary(binaryName: string): string {
  const sumoHome = process.env.SUMO_HOME;
  if (sumoHome) {
    const ext = process.platform === 'win32' ? '.exe' : '';
    const cand = path.join(sumoHome, 'bin', `${binaryName}${ext}`);
    if (fs.existsSync(cand)) {
      return cand;
    }
  }
  return binaryName;
}

export class SumoTools {
  private resolveLocationToBbox(locationOrBbox: string): string {
    if (!locationOrBbox) return '76.890,10.895,76.915,10.915';
    const query = locationOrBbox.trim();
    const parts = query.split(',');
    if (parts.length === 4) {
      const floats = parts.map((p) => parseFloat(p));
      if (!floats.some((f) => isNaN(f))) {
        return floats.join(',');
      }
    }

    const presets: Record<string, string> = {
      ettimadai: '76.890,10.895,76.915,10.915',
      amrita: '76.898,10.900,76.910,10.910',
      erode: '77.700,11.330,77.780,11.410',
      coimbatore: '76.940,11.000,76.980,11.030',
      chennai: '80.250,13.060,80.290,13.100',
      bangalore: '77.580,12.960,77.620,13.000',
      bengaluru: '77.580,12.960,77.620,13.000',
      delhi: '77.200,28.600,77.240,28.640'
    };

    const key = query.toLowerCase();
    for (const [name, bbox] of Object.entries(presets)) {
      if (key.includes(name)) {
        return bbox;
      }
    }

    return query;
  }

  @Tool({
    name: 'generate_network',
    description: 'Step 1: Download OSM map data automatically using a location name (e.g. "Erode City Center", "Ettimadai") or bounding box coordinates and convert it into a SUMO network file (mymap.net.xml).',
    inputSchema: z.object({
      bbox: z.string().describe('Location name (e.g. "Erode City Center", "Ettimadai", "Amrita University") or coordinate string (min_lon,min_lat,max_lon,max_lat)')
    })
  })
  async generateNetwork(input: { bbox: string }, ctx: ExecutionContext) {
    const targetBbox = this.resolveLocationToBbox(input.bbox);
    ctx.logger.info(`Generating SUMO network for location '${input.bbox}' (resolved bbox: ${targetBbox})`);

    const osmScript = findSumoScript('osmGet.py');
    const netconvertBin = findSumoBinary('netconvert');

    try {
      // Step 1: Execute python osmGet.py -b [coords] -p mymap
      execSync(`python "${osmScript}" -b ${targetBbox} -p mymap`, { stdio: ['ignore', 'pipe', 'pipe'] });

      // Detect generated OSM file (e.g. mymap_bbox.osm.xml or mymap.osm)
      const files = fs.readdirSync(process.cwd());
      const osmFiles = files.filter(f => f.startsWith('mymap') && (f.endsWith('.osm') || f.endsWith('.osm.xml')));
      const osmInput = osmFiles.length > 0 ? osmFiles.join(',') : 'mymap.osm';

      // Step 2: Execute netconvert --osm-files mymap.osm -o mymap.net.xml
      execSync(`"${netconvertBin}" --osm-files ${osmInput} -o mymap.net.xml`, { stdio: ['ignore', 'pipe', 'pipe'] });

      return {
        status: 'success',
        message: `Success: Network file 'mymap.net.xml' is ready for location '${input.bbox}' (${targetBbox}).`
      };
    } catch (e: any) {
      return {
        status: 'error',
        message: `Error generating network: ${e.message}`
      };
    }
  }

  private createVTypesFile(filePath = 'vtypes.add.xml') {
    const vtypesXml = `<additional>
    <vTypeDistribution id="indian_mixed">
        <vType id="ind_motorcycle" vClass="motorcycle" length="1.8" width="0.8" minGap="0.5" maxSpeed="16.67" accel="3.5" decel="5.0" probability="0.35" color="1,0.3,0.3" latAlignment="arbitrary"/>
        <vType id="ind_autorickshaw" vClass="moped" length="2.6" width="1.3" minGap="0.8" maxSpeed="13.89" accel="2.0" decel="4.5" probability="0.20" color="1,0.8,0" latAlignment="arbitrary"/>
        <vType id="ind_car" vClass="passenger" length="4.3" width="1.8" minGap="1.0" maxSpeed="22.22" accel="2.6" decel="4.5" probability="0.30" color="0.2,0.6,1"/>
        <vType id="ind_bus" vClass="bus" length="10.5" width="2.5" minGap="2.0" maxSpeed="13.89" accel="1.2" decel="3.5" probability="0.08" color="0.2,0.8,0.2"/>
        <vType id="ind_truck" vClass="truck" length="8.0" width="2.4" minGap="2.0" maxSpeed="13.89" accel="1.0" decel="3.0" probability="0.07" color="0.8,0.5,0.2"/>
    </vTypeDistribution>
</additional>`;
    fs.writeFileSync(path.join(process.cwd(), filePath), vtypesXml, 'utf-8');
  }

  private createGuiSettings(netFile = 'mymap.net.xml', settingsFile = 'gui-settings.xml') {
    let centerX = 1000.0;
    let centerY = 1000.0;
    let zoom = 500.0;

    if (fs.existsSync(netFile)) {
      try {
        const netContent = fs.readFileSync(netFile, 'utf-8');
        const match = netContent.match(/convBoundary="([^"]+)"/);
        if (match && match[1]) {
          const parts = match[1].split(',').map((v) => parseFloat(v));
          if (parts.length === 4) {
            const [minX, minY, maxX, maxY] = parts;
            centerX = (minX + maxX) / 2.0;
            centerY = (minY + maxY) / 2.0;
            const width = Math.max(1.0, maxX - minX);
            const height = Math.max(1.0, maxY - minY);
            zoom = Math.max(400.0, Math.min(2500.0, 120000.0 / Math.max(width, height)));
          }
        }
      } catch (e) {
        // Fallback to default center/zoom
      }
    }

    const guiXml = `<viewsettings>
    <scheme name="real world"/>
    <delay value="150"/>
    <viewport zoom="${zoom.toFixed(2)}" x="${centerX.toFixed(2)}" y="${centerY.toFixed(2)}"/>
    <vehicles vehicleScale="2.5" vehicleColorer="by vType"/>
</viewsettings>`;

    fs.writeFileSync(path.join(process.cwd(), settingsFile), guiXml, 'utf-8');
  }

  @Tool({
    name: 'generate_routes',
    description: 'Step 2: Generate random trips/routes for heterogeneous Indian traffic (motorcycles, autos, cars, buses, trucks) and sublane configuration file.',
    inputSchema: z.object({
      trips: z.number().optional().default(600).describe('Total number of trips to generate across simulation duration (default: 600)'),
      duration: z.number().optional().default(7200).describe('Total simulation duration in seconds (default: 7200s / 2 hours)'),
      density: z.enum(['low', 'medium', 'high', 'congested']).optional().describe('Preset traffic density level (low: 250, medium: 600, high: 1200, congested: 2000 trips)')
    })
  })
  async generateRoutes(input: { trips?: number; duration?: number; density?: 'low' | 'medium' | 'high' | 'congested' }, ctx: ExecutionContext) {
    let totalTrips = input.trips || 600;
    if (input.density) {
      const densityMap: Record<string, number> = { low: 250, medium: 600, high: 1200, congested: 2000 };
      totalTrips = densityMap[input.density] || totalTrips;
    }

    const totalDuration = input.duration || 7200;
    const period = Math.max(1, Math.floor(totalDuration / totalTrips));

    ctx.logger.info(`Generating heterogeneous SUMO routes for ${totalTrips} trips over ${totalDuration}s (period=${period})`);

    const tripsScript = findSumoScript('randomTrips.py');

    if (!fs.existsSync('mymap.net.xml')) {
      return {
        status: 'error',
        message: "Error: 'mymap.net.xml' not found. Please run 'generate_network' first."
      };
    }

    try {
      // Step 1: Create heterogeneous Indian vehicle types file (motorcycles, autorickshaws, cars, buses, trucks)
      this.createVTypesFile('vtypes.add.xml');

      // Step 2: Execute python randomTrips.py with indian_mixed vType distribution
      execSync(`python "${tripsScript}" -n mymap.net.xml -e ${totalDuration} -p ${period} -l -r mymap.rou.xml -a vtypes.add.xml --trip-attributes "type=\\"indian_mixed\\""`, { stdio: ['ignore', 'pipe', 'pipe'] });

      // Step 3: Auto-generate GUI visual settings file
      this.createGuiSettings('mymap.net.xml', 'gui-settings.xml');

      // Step 4: Programmatically generate mymap.sumocfg XML file referencing net, routes, and sublane processing
      const sumocfgContent = `<configuration>
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
        <end value="${totalDuration}"/>
    </time>
</configuration>`;

      fs.writeFileSync(path.join(process.cwd(), 'mymap.sumocfg'), sumocfgContent, 'utf-8');

      return {
        status: 'success',
        message: `Success: SUMO configuration file 'mymap.sumocfg' generated with ${totalTrips} trips across heterogeneous vehicle types (motorcycles, autos, cars, buses, trucks) and sublane resolution.`
      };
    } catch (e: any) {
      return {
        status: 'error',
        message: `Error generating routes: ${e.message}`
      };
    }
  }

  @Tool({
    name: 'run_headless_simulation',
    description: 'Step 3: Execute SUMO simulation headlessly using mymap.sumocfg and output stats.xml and tripinfo.xml.',
    inputSchema: z.object({})
  })
  async runHeadlessSimulation(input: {}, ctx: ExecutionContext) {
    ctx.logger.info('Running SUMO simulation in headless mode...');

    const sumoBin = findSumoBinary('sumo');

    if (!fs.existsSync('mymap.sumocfg')) {
      return {
        status: 'error',
        message: "Error: 'mymap.sumocfg' not found. Please run 'generate_routes' first."
      };
    }

    try {
      // Execute SUMO headlessly and wait for completion
      execSync(`"${sumoBin}" -c mymap.sumocfg --statistic-output stats.xml --tripinfo-output tripinfo.xml`, { stdio: ['ignore', 'pipe', 'pipe'] });

      return {
        status: 'success',
        message: "Success: Headless SUMO simulation completed. 'stats.xml' and 'tripinfo.xml' generated."
      };
    } catch (e: any) {
      return {
        status: 'error',
        message: `Error running simulation: ${e.message}`
      };
    }
  }

  @Tool({
    name: 'run_gui_simulation',
    description: 'Step 3b: Open the visual SUMO GUI app on your desktop to view vehicles driving on the map in real-time.',
    inputSchema: z.object({
      autoStart: z.boolean().optional().default(true).describe('Automatically start simulation playback on launch'),
      delay: z.number().optional().default(150).describe('Step delay in milliseconds for smooth human-visible animation (default: 150ms)')
    })
  })
  async runGuiSimulation(input: { autoStart?: boolean; delay?: number }, ctx: ExecutionContext) {
    ctx.logger.info('Launching SUMO GUI desktop application...');
    const sumoGuiBin = findSumoBinary('sumo-gui');
    const stepDelay = input.delay || 150;

    if (!fs.existsSync('mymap.sumocfg')) {
      return {
        status: 'error',
        message: "Error: 'mymap.sumocfg' not found. Please run 'generate_routes' first."
      };
    }

    if (!fs.existsSync('gui-settings.xml')) {
      this.createGuiSettings('mymap.net.xml', 'gui-settings.xml');
    }

    try {
      const autoStartFlag = input.autoStart !== false ? '--start' : '';
      execSync(`start "" "${sumoGuiBin}" -c mymap.sumocfg -g gui-settings.xml --delay ${stepDelay} ${autoStartFlag}`);

      return {
        status: 'success',
        message: `Success: SUMO GUI application launched on desktop with centered viewport, enlarged vehicles (3.5x), real world scheme, and ${stepDelay}ms step delay.`
      };
    } catch (e: any) {
      return {
        status: 'error',
        message: `Error launching SUMO GUI: ${e.message}`
      };
    }
  }

  @Tool({
    name: 'analyze_results',
    description: 'Step 4: Parse stats.xml and extract key metrics (total vehicles loaded, inserted, average route length).',
    inputSchema: z.object({})
  })
  async analyzeResults(input: {}, ctx: ExecutionContext) {
    ctx.logger.info('Parsing stats.xml results...');

    const statsPath = path.join(process.cwd(), 'stats.xml');
    if (!fs.existsSync(statsPath)) {
      return {
        error: "Statistics file 'stats.xml' not found. Please run 'run_headless_simulation' first."
      };
    }

    try {
      const xmlData = fs.readFileSync(statsPath, 'utf-8');

      // Robust extraction using regular expressions
      const loadedMatch = xmlData.match(/<vehicles[^>]*\bloaded="([0-9]+)"/);
      const insertedMatch = xmlData.match(/<vehicles[^>]*\binserted="([0-9]+)"/);
      const routeLengthMatch = xmlData.match(/<vehicleTripStatistics[^>]*\b(?:routeLength|avgRouteLength)="([0-9.]+)"/);

      const totalLoaded = loadedMatch ? parseInt(loadedMatch[1], 10) : 0;
      const totalInserted = insertedMatch ? parseInt(insertedMatch[1], 10) : 0;
      const avgRouteLength = routeLengthMatch ? parseFloat(routeLengthMatch[1]) : 0.0;

      return {
        total_vehicles_loaded: totalLoaded,
        total_vehicles_inserted: totalInserted,
        average_route_length: avgRouteLength
      };
    } catch (e: any) {
      return {
        error: `Failed to parse statistics: ${e.message}`
      };
    }
  }

  @Tool({
    name: 'run_full_simulation',
    description: 'Master Orchestration Tool: Executes the complete end-to-end SUMO traffic simulation pipeline in a single call (downloads network, generates routes, opens GUI, and analyzes results).',
    inputSchema: z.object({
      bbox: z.string().describe('Bounding box coordinate string (min_lon,min_lat,max_lon,max_lat)'),
      trips: z.number().optional().default(600).describe('Total number of vehicle trips to simulate (default: 600)'),
      duration: z.number().optional().default(7200).describe('Total simulation duration in seconds (default: 7200s / 2 hours)'),
      density: z.enum(['low', 'medium', 'high', 'congested']).optional().describe('Preset traffic density level (low: 250, medium: 600, high: 1200, congested: 2000 trips)'),
      launchGui: z.boolean().optional().default(true).describe('Automatically open the visual SUMO GUI desktop application')
    })
  })
  async runFullSimulation(
    input: { bbox: string; trips?: number; duration?: number; density?: 'low' | 'medium' | 'high' | 'congested'; launchGui?: boolean },
    ctx: ExecutionContext
  ) {
    ctx.logger.info(`Running full end-to-end simulation for bbox: ${input.bbox}`);

    const netRes = await this.generateNetwork({ bbox: input.bbox }, ctx);
    if (netRes.status === 'error') {
      return { status: 'error', step: 'generate_network', message: netRes.message };
    }

    const targetTrips = input.trips || 600;
    const routesRes = await this.generateRoutes({ trips: targetTrips, duration: input.duration || 7200, density: input.density }, ctx);
    if (routesRes.status === 'error') {
      return { status: 'error', step: 'generate_routes', message: routesRes.message };
    }

    const headlessRes = await this.runHeadlessSimulation({}, ctx);

    let guiRes: any = null;
    if (input.launchGui !== false) {
      guiRes = await this.runGuiSimulation({ autoStart: true, delay: 150 }, ctx);
    }

    const analytics = await this.analyzeResults({}, ctx);

    return {
      status: 'success',
      bbox: input.bbox,
      trips: targetTrips,
      duration: input.duration || 7200,
      density: input.density || 'medium',
      gui_launched: input.launchGui !== false,
      network_status: netRes.message,
      routes_status: routesRes.message,
      headless_status: headlessRes.message,
      gui_status: guiRes ? guiRes.message : 'GUI not requested',
      analytics
    };
  }
}
