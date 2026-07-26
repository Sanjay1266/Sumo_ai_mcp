import { Module } from '@nitrostack/core';
import { TestTools } from './test.tools.js';

@Module({
  name: 'test',
  description: 'SUMO Traffic Simulation Dedicated Test Tools Suite Module',
  controllers: [TestTools]
})
export class TestModule {}
