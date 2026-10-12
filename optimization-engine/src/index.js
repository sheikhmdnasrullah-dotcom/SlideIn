const config = require('./config');
const db = require('./database');
const { connection } = require('./queues');
const senderWorker = require('./workers/senderWorker');
const imapWorker = require('./workers/imapWorker');
const { startScheduler, stopScheduler } = require('./scheduler');

console.log('====================================================');
console.log('🚀 INBOX PLACEMENT OPTIMIZATION ENGINE');
console.log(`Redis Host: ${config.redis.host}:${config.redis.port}`);
console.log(`KumoMTA ESMTP: ${config.kumo.host}:${config.kumo.port}`);
console.log(`Optimization Engine: ACTIVE`);
console.log(`Content Optimizer: ACTIVE`);
console.log(`Engagement Tracker: ACTIVE`);
console.log(`Warmup Engine: ACTIVE`);
console.log(`Placement Optimizer: ACTIVE`);
console.log(`Unsubscribe Manager: ACTIVE`);
console.log('====================================================');

startScheduler();

process.on('SIGINT', () => {
  console.log('\n[Optimizer] Shutting down...');
  stopScheduler();
  process.exit(0);
});
