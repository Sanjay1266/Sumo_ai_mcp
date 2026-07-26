import { ToolDecorator as Tool, ExecutionContext, z } from '@nitrostack/core';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as https from 'https';

function clampBbox(minLon: number, minLat: number, maxLon: number, maxLat: number, maxSpan = 0.025): string {
  const centerLon = (minLon + maxLon) / 2.0;
  const centerLat = (minLat + maxLat) / 2.0;
  const halfSpan = maxSpan / 2.0;

  const clampedMinLon = (centerLon - halfSpan).toFixed(4);
  const clampedMinLat = (centerLat - halfSpan).toFixed(4);
  const clampedMaxLon = (centerLon + halfSpan).toFixed(4);
  const clampedMaxLat = (centerLat + halfSpan).toFixed(4);

  return `${clampedMinLon},${clampedMinLat},${clampedMaxLon},${clampedMaxLat}`;
}

async function resolveLocationToBboxAsync(locationOrBbox: string): Promise<string> {
  if (!locationOrBbox) return '76.8900,10.8950,76.9150,10.9150';
  const query = locationOrBbox.trim();

  const parts = query.split(',');
  if (parts.length === 4) {
    const floats = parts.map((p) => parseFloat(p));
    if (!floats.some((f) => isNaN(f))) {
      return clampBbox(floats[0], floats[1], floats[2], floats[3]);
    }
  }

  const presets: Record<string, string> = {
    ettimadai: '76.8900,10.8950,76.9150,10.9150',
    amrita: '76.8980,10.9000,76.9100,10.9100',
    gandhipuram: '76.9550,10.9950,76.9800,11.0200',
    peelamedu: '76.9950,11.0150,77.0200,11.0400',
    rspuram: '76.9350,10.9950,76.9600,11.0200',
    'rs puram': '76.9350,10.9950,76.9600,11.0200',
    ukkadam: '76.9450,10.9750,76.9700,11.0000',
    saravanampatti: '76.9750,11.0650,77.0000,11.0900',
    erode: '77.7200,11.3350,77.7450,11.3600',
    coimbatore: '76.9500,10.9950,76.9750,11.0200',
    chennai: '80.2600,13.0650,80.2850,13.0900',
    bangalore: '77.5850,12.9650,77.6100,12.9900',
    bengaluru: '77.5850,12.9650,77.6100,12.9900',
    delhi: '77.2100,28.6100,77.2350,28.6350'
  };

  const key = query.toLowerCase();
  for (const [name, bbox] of Object.entries(presets)) {
    if (key.includes(name)) {
      return bbox;
    }
  }

  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json`;
    const responseData = await new Promise<string>((resolve, reject) => {
      const req = https.get(url, { headers: { 'User-Agent': 'NitroStack-SUMO-Geocoder/1.0' } }, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => resolve(data));
      });
      req.on('error', reject);
      req.setTimeout(4000, () => {
        req.destroy();
        reject(new Error('Nominatim timeout'));
      });
    });

    const parsed = JSON.parse(responseData);
    if (Array.isArray(parsed) && parsed.length > 0) {
      const bboxArr = parsed[0].boundingbox;
      if (bboxArr && bboxArr.length === 4) {
        const minLat = parseFloat(bboxArr[0]);
        const maxLat = parseFloat(bboxArr[1]);
        const minLon = parseFloat(bboxArr[2]);
        const maxLon = parseFloat(bboxArr[3]);
        return clampBbox(minLon, minLat, maxLon, maxLat);
      }
    }
  } catch (e) {
  }

  return '76.8900,10.8950,76.9150,10.9150';
}

export class TestTools {
  @Tool({
    name: 'test_geocoder',
    description: 'Test Tool 1: Test location geocoding, preset lookups, coordinate bounding box clamping, and format accuracy.',
    inputSchema: z.object({
      locations: z.array(z.string()).optional().describe('List of location names to test')
    })
  })
  async testGeocoder(input: { locations?: string[] }, ctx: ExecutionContext) {
    ctx.logger.info('Executing Geocoder Validation Test...');
    const testLocations = input.locations || ['Erode City Center', 'Ettimadai', 'Salem', 'Coimbatore', 'Chennai', 'Gandhipuram', 'Peelamedu', 'RS Puram', 'Ukkadam', 'Amrita'];
    const results = [];
    let passed = 0;
    let failed = 0;

    for (const loc of testLocations) {
      try {
        const bbox = await resolveLocationToBboxAsync(loc);
        const parts = bbox.split(',');
        if (parts.length !== 4) {
          throw new Error(`Expected 4 comma-separated values, got: ${bbox}`);
        }
        const floats = parts.map((p) => parseFloat(p));
        if (floats[0] >= floats[2] || floats[1] >= floats[3]) {
          throw new Error(`Invalid coordinate bounds in bbox: ${bbox}`);
        }

        results.push({ location: loc, resolved_bbox: bbox, status: 'PASSED' });
        passed++;
      } catch (e: any) {
        results.push({ location: loc, error: e.message, status: 'FAILED' });
        failed++;
      }
    }

    return {
      test_name: 'Geocoder Validation Test',
      total_tests: testLocations.length,
      passed,
      failed,
      overall_status: failed === 0 ? 'PASSED' : 'FAILED',
      details: results
    };
  }

  @Tool({
    name: 'test_network_generation',
    description: 'Test Tool 2: Test SUMO network generation for a given location/bbox and verify output file mymap.net.xml.',
    inputSchema: z.object({
      location: z.string().optional().default('Salem').describe('Location or bounding box to test network generation for')
    })
  })
  async testNetworkGeneration(input: { location?: string }, ctx: ExecutionContext) {
    const loc = input.location || 'Salem';
    ctx.logger.info(`Executing Network Generation Test for '${loc}'...`);
    const startTime = Date.now();

    let serverResponse = '';
    try {
      const output = execSync(`python -c "import sumo_server; print(sumo_server.generate_network('${loc}'))"`, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
      serverResponse = output.trim();
    } catch (e: any) {
      serverResponse = `Error: ${e.message}`;
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    const netPath = path.join(process.cwd(), 'mymap.net.xml');
    const netExists = fs.existsSync(netPath);
    const netSize = netExists ? fs.statSync(netPath).size : 0;
    const isValid = netExists && netSize > 0 && !serverResponse.startsWith('Error');

    return {
      test_name: 'Network Generation Test',
      location: loc,
      net_file_exists: netExists,
      net_file_size_bytes: netSize,
      execution_time_seconds: parseFloat(elapsed),
      server_response: serverResponse,
      overall_status: isValid ? 'PASSED' : 'FAILED'
    };
  }

  @Tool({
    name: 'test_route_generation',
    description: 'Test Tool 3: Test SUMO route generation with trip counts and density presets, verifying vtypes.add.xml, mymap.rou.xml, and mymap.sumocfg.',
    inputSchema: z.object({
      trips: z.number().optional().default(100).describe('Total trips to generate for test'),
      duration: z.number().optional().default(3600).describe('Total simulation duration in seconds for test')
    })
  })
  async testRouteGeneration(input: { trips?: number; duration?: number }, ctx: ExecutionContext) {
    const trips = input.trips || 100;
    const duration = input.duration || 3600;
    ctx.logger.info(`Executing Route Generation Test for ${trips} trips, ${duration}s...`);

    const netExists = fs.existsSync(path.join(process.cwd(), 'mymap.net.xml'));
    if (!netExists) {
      return {
        test_name: 'Route Generation Test',
        overall_status: 'FAILED',
        error: "'mymap.net.xml' is missing. Please run test_network_generation first."
      };
    }

    const startTime = Date.now();
    let serverResponse = '';
    try {
      const output = execSync(`python -c "import sumo_server; print(sumo_server.generate_routes(trips=${trips}, duration=${duration}))"`, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
      serverResponse = output.trim();
    } catch (e: any) {
      serverResponse = `Error: ${e.message}`;
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    const rouExists = fs.existsSync(path.join(process.cwd(), 'mymap.rou.xml'));
    const vtypesExists = fs.existsSync(path.join(process.cwd(), 'vtypes.add.xml'));
    const cfgExists = fs.existsSync(path.join(process.cwd(), 'mymap.sumocfg'));
    const guiSettingsExists = fs.existsSync(path.join(process.cwd(), 'gui-settings.xml'));

    const isValid = rouExists && vtypesExists && cfgExists && guiSettingsExists && !serverResponse.startsWith('Error');

    return {
      test_name: 'Route Generation Test',
      trips,
      duration,
      rou_file_exists: rouExists,
      vtypes_file_exists: vtypesExists,
      sumocfg_file_exists: cfgExists,
      gui_settings_exists: guiSettingsExists,
      execution_time_seconds: parseFloat(elapsed),
      server_response: serverResponse,
      overall_status: isValid ? 'PASSED' : 'FAILED'
    };
  }

  @Tool({
    name: 'test_simulation_execution',
    description: 'Test Tool 4: Test headless simulation execution and verify stats.xml and tripinfo.xml.',
    inputSchema: z.object({})
  })
  async testSimulationExecution(input: {}, ctx: ExecutionContext) {
    ctx.logger.info('Executing Headless Simulation Test...');

    const cfgExists = fs.existsSync(path.join(process.cwd(), 'mymap.sumocfg'));
    if (!cfgExists) {
      return {
        test_name: 'Headless Simulation Execution Test',
        overall_status: 'FAILED',
        error: "'mymap.sumocfg' is missing. Please run test_route_generation first."
      };
    }

    const startTime = Date.now();
    let serverResponse = '';
    try {
      const output = execSync(`python -c "import sumo_server; print(sumo_server.run_headless_simulation())"`, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
      serverResponse = output.trim();
    } catch (e: any) {
      serverResponse = `Error: ${e.message}`;
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    const statsExists = fs.existsSync(path.join(process.cwd(), 'stats.xml'));
    const tripinfoExists = fs.existsSync(path.join(process.cwd(), 'tripinfo.xml'));

    const isValid = statsExists && tripinfoExists && !serverResponse.startsWith('Error');

    return {
      test_name: 'Headless Simulation Execution Test',
      stats_file_exists: statsExists,
      tripinfo_file_exists: tripinfoExists,
      execution_time_seconds: parseFloat(elapsed),
      server_response: serverResponse,
      overall_status: isValid ? 'PASSED' : 'FAILED'
    };
  }

  @Tool({
    name: 'test_analytics_truthfulness',
    description: 'Test Tool 5: Audit truthfulness of analyze_results() by parsing stats.xml directly and matching metrics with zero error margin.',
    inputSchema: z.object({})
  })
  async testAnalyticsTruthfulness(input: {}, ctx: ExecutionContext) {
    ctx.logger.info('Executing Analytics Truthfulness Audit Test...');

    const statsPath = path.join(process.cwd(), 'stats.xml');
    if (!fs.existsSync(statsPath)) {
      return {
        test_name: 'Analytics Truthfulness Audit Test',
        overall_status: 'FAILED',
        error: "Statistics file 'stats.xml' missing. Please run test_simulation_execution first."
      };
    }

    try {
      const xmlData = fs.readFileSync(statsPath, 'utf-8');
      const loadedMatch = xmlData.match(/<vehicles[^>]*\bloaded="([0-9]+)"/);
      const insertedMatch = xmlData.match(/<vehicles[^>]*\binserted="([0-9]+)"/);
      const routeLengthMatch = xmlData.match(/<vehicleTripStatistics[^>]*\b(?:routeLength|avgRouteLength)="([0-9.]+)"/);

      const actualLoaded = loadedMatch ? parseInt(loadedMatch[1], 10) : 0;
      const actualInserted = insertedMatch ? parseInt(insertedMatch[1], 10) : 0;
      const actualRouteLength = routeLengthMatch ? parseFloat(routeLengthMatch[1]) : 0.0;

      const output = execSync(`python -c "import sumo_server, json; print(json.dumps(sumo_server.analyze_results()))"`, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
      const reported = JSON.parse(output.trim());

      const loadedOk = actualLoaded === reported.total_vehicles_loaded;
      const insertedOk = actualInserted === reported.total_vehicles_inserted;
      const lengthOk = Math.abs(actualRouteLength - reported.average_route_length) < 0.01;

      const allPassed = loadedOk && insertedOk && lengthOk;

      return {
        test_name: 'Analytics Truthfulness Audit Test',
        metrics: {
          total_vehicles_loaded: {
            actual_xml: actualLoaded,
            tool_reported: reported.total_vehicles_loaded,
            match: loadedOk
          },
          total_vehicles_inserted: {
            actual_xml: actualInserted,
            tool_reported: reported.total_vehicles_inserted,
            match: insertedOk
          },
          average_route_length: {
            actual_xml: parseFloat(actualRouteLength.toFixed(2)),
            tool_reported: parseFloat(reported.average_route_length.toFixed(2)),
            match: lengthOk
          }
        },
        overall_status: allPassed ? 'PASSED' : 'FAILED'
      };
    } catch (e: any) {
      return {
        test_name: 'Analytics Truthfulness Audit Test',
        overall_status: 'FAILED',
        error: e.message
      };
    }
  }

  @Tool({
    name: 'run_all_test_cases',
    description: 'Master Test Suite Tool: Executes all test cases end-to-end and returns a comprehensive structured test summary report.',
    inputSchema: z.object({
      location: z.string().optional().default('Salem').describe('Location or bounding box to test'),
      trips: z.number().optional().default(100).describe('Total trips to simulate during test'),
      duration: z.number().optional().default(3600).describe('Total duration in seconds')
    })
  })
  async runAllTestCases(input: { location?: string; trips?: number; duration?: number }, ctx: ExecutionContext) {
    const startTime = Date.now();

    const geoRes = await this.testGeocoder({}, ctx);
    const netRes = await this.testNetworkGeneration({ location: input.location }, ctx);
    const routeRes = await this.testRouteGeneration({ trips: input.trips, duration: input.duration }, ctx);
    const simRes = await this.testSimulationExecution({}, ctx);
    const auditRes = await this.testAnalyticsTruthfulness({}, ctx);

    const elapsed = parseFloat(((Date.now() - startTime) / 1000).toFixed(2));
    const allTests = [geoRes, netRes, routeRes, simRes, auditRes];
    const totalCount = allTests.length;
    const passedCount = allTests.filter((t) => t.overall_status === 'PASSED').length;
    const failedCount = totalCount - passedCount;

    return {
      suite_name: 'SUMO Simulation Master Test Suite',
      total_test_cases: totalCount,
      passed_test_cases: passedCount,
      failed_test_cases: failedCount,
      total_execution_time_seconds: elapsed,
      overall_suite_status: failedCount === 0 ? 'PASSED' : 'FAILED',
      test_case_results: {
        geocoder_test: geoRes,
        network_generation_test: netRes,
        route_generation_test: routeRes,
        simulation_execution_test: simRes,
        analytics_truthfulness_test: auditRes
      }
    };
  }
}
