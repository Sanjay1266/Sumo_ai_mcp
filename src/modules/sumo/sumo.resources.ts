import { ResourceDecorator as Resource, ExecutionContext } from '@nitrostack/core';
import * as fs from 'fs';
import * as path from 'path';

export class SumoResources {
  @Resource({
    uri: 'sumo://stats',
    name: 'SUMO Statistics Report',
    description: 'Raw XML statistics report generated from the latest SUMO simulation run.',
    mimeType: 'application/xml'
  })
  async getSimulationStats(ctx: ExecutionContext) {
    const statsPath = path.join(process.cwd(), 'stats.xml');
    if (!fs.existsSync(statsPath)) {
      return '<error>stats.xml file not found. Run simulation first.</error>';
    }
    return fs.readFileSync(statsPath, 'utf-8');
  }

  @Resource({
    uri: 'sumo://tripinfo',
    name: 'SUMO Microscopic Trip Info Report',
    description: 'Raw XML microscopic trip details report generated from the latest SUMO simulation run.',
    mimeType: 'application/xml'
  })
  async getTripInfo(ctx: ExecutionContext) {
    const tripinfoPath = path.join(process.cwd(), 'tripinfo.xml');
    if (!fs.existsSync(tripinfoPath)) {
      return '<error>tripinfo.xml file not found. Run simulation first.</error>';
    }
    return fs.readFileSync(tripinfoPath, 'utf-8');
  }
}
