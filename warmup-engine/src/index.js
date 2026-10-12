const config = require('./config');
const db = require('./database');
const { connection } = require('./queues');
const senderWorker = require('./workers/senderWorker');
const imapWorker = require('./workers/imapWorker');
const replyWorker = require('./workers/replyWorker');
const { startScheduler, stopScheduler } = require('./scheduler');

console.log('====================================================');
console.log('🚀 24/7 AUTOMATED EMAIL WARMUP ENGINE IS STARTING');
console.log(`Redis Host: ${config.redis.host}:${config.redis.port}`);
console.log(`KumoMTA ESMTP: ${config.kumo.host}:${config.kumo.port}`);
console.log(`Configured Profiles: ${config.profiles.map((p) => p.email).join(', ')}`);
console.log('====================================================');

startScheduler();

async function shutdown() {
  console.log('\n[Warmup Engine] Shutting down gracefully...');
  stopScheduler();
  await senderWorker.close();
  await imapWorker.close();
  await replyWorker.close();
  await connection.quit();
  process.exit(0);
}

process.on('SIGINT', () => {
  shutdown().catch((err) => {
    console.error('[Warmup Engine] Shutdown failed:', err);
    process.exit(1);
  });
});
process.on('SIGTERM', () => {
  shutdown().catch((err) => {
    console.error('[Warmup Engine] Shutdown failed:', err);
    process.exit(1);
  });
});
// Failsafe: never hang forever in shutdown (e.g. Redis already gone and
// connection.quit() stalls). unref() so this cannot keep the process alive.
setTimeout(() => process.exit(0), 10000).unref();

// Process-level guards: log loudly and exit non-zero so pm2's autorestart
// restarts a clean process instead of leaving a half-broken one running.
process.on('unhandledRejection', (reason) => {
  console.error('[Warmup Engine] Unhandled promise rejection:', reason);
  process.exit(1);
});
process.on('uncaughtException', (err) => {
  console.error('[Warmup Engine] Uncaught exception:', err);
  process.exit(1);
});
