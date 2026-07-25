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
  @Tool({
    name: 'generate_network',
    description: 'Step 1: Download OSM map data for a bounding box and convert it into a SUMO network file (mymap.net.xml).',
    inputSchema: z.object({
      bbox: z.string().describe('Bounding box coordinate string (min_lon,min_lat,max_lon,max_lat), e.g. "13.37,52.51,13.38,52.52"')
    })
  })
  async generateNetwork(input: { bbox: string }, ctx: ExecutionContext) {
    ctx.logger.info(`Generating SUMO network for bbox: ${input.bbox}`);

    const osmScript = findSumoScript('osmGet.py');
    const netconvertBin = findSumoBinary('netconvert');

    try {
      // Step 1: Execute python osmGet.py -b [coords] -p mymap
      execSync(`python "${osmScript}" -b ${input.bbox} -p mymap`, { stdio: 'inherit' });

      // Detect generated OSM file (e.g. mymap_bbox.osm.xml or mymap.osm)
      const files = fs.readdirSync(process.cwd());
      const osmFiles = files.filter(f => f.startsWith('mymap') && (f.endsWith('.osm') || f.endsWith('.osm.xml')));
      const osmInput = osmFiles.length > 0 ? osmFiles.join(',') : 'mymap.osm';

      // Step 2: Execute netconvert --osm-files mymap.osm -o mymap.net.xml
      execSync(`"${netconvertBin}" --osm-files ${osmInput} -o mymap.net.xml`, { stdio: 'inherit' });

      return {
        status: 'success',
        message: "Success: Network file 'mymap.net.xml' is ready."
      };
    } catch (e: any) {
      return {
        status: 'error',
        message: `Error generating network: ${e.message}`
      };
    }
  }

  @Tool({
    name: 'generate_routes',
    description: 'Step 2: Generate random trips/routes for the network and create the mymap.sumocfg XML configuration file.',
    inputSchema: z.object({
      trips: z.number().optional().default(200).describe('Total number of trips to generate across simulation duration'),
      duration: z.number().optional().default(7200).describe('Total simulation duration in seconds (default: 7200s / 2 hours)')
    })
  })
  async generateRoutes(input: { trips?: number; duration?: number }, ctx: ExecutionContext) {
    const totalTrips = input.trips || 200;
    const totalDuration = input.duration || 7200;
    const period = Math.max(1, Math.floor(totalDuration / totalTrips));

    ctx.logger.info(`Generating SUMO routes for ${totalTrips} trips over ${totalDuration}s (period=${period})`);

    const tripsScript = findSumoScript('randomTrips.py');

    if (!fs.existsSync('mymap.net.xml')) {
      return {
        status: 'error',
        message: "Error: 'mymap.net.xml' not found. Please run 'generate_network' first."
      };
    }

    try {
      // Step 1: Execute python randomTrips.py -n mymap.net.xml -e [duration] -p [period] -l -r mymap.rou.xml
      execSync(`python "${tripsScript}" -n mymap.net.xml -e ${totalDuration} -p ${period} -l -r mymap.rou.xml`, { stdio: 'inherit' });

      // Step 2: Programmatically generate mymap.sumocfg XML file
      const sumocfgContent = `<configuration>
    <input>
        <net-file value="mymap.net.xml"/>
        <route-files value="mymap.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="${totalDuration}"/>
    </time>
</configuration>`;

      fs.writeFileSync(path.join(process.cwd(), 'mymap.sumocfg'), sumocfgContent, 'utf-8');

      return {
        status: 'success',
        message: "Success: SUMO configuration file 'mymap.sumocfg' is ready."
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
      execSync(`"${sumoBin}" -c mymap.sumocfg --statistic-output stats.xml --tripinfo-output tripinfo.xml`, { stdio: 'inherit' });

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

    try {
      const autoStartFlag = input.autoStart !== false ? '--start' : '';
      execSync(`start "" "${sumoGuiBin}" -c mymap.sumocfg --delay ${stepDelay} ${autoStartFlag}`);

      return {
        status: 'success',
        message: `Success: SUMO GUI application launched on desktop with ${stepDelay}ms step delay.`
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
}
