const fs = require('fs');
const config = require('./config');
const db = require('./database');
const { getRandomTopic } = require('./topics');
const { sendQueue } = require('./queues');

let schedulerInterval = null;
let initialRunTimer = null;
let profileIndex = 0;

function syncAccountsFromFile() {
  if (!fs.existsSync(config.accountsFile)) return;
  try {
    const raw = fs.readFileSync(config.accountsFile, 'utf8');
    const accounts = JSON.parse(raw);
    if (Array.isArray(accounts)) {
      for (const acc of accounts) {
        if (!acc.imap_pass || acc.imap_pass.includes('FILL_IN') || acc.imap_pass.includes('PLACEHOLDER')) {
          continue; // skip unconfigured accounts
        }
        db.addSeedAccount({
          email: acc.email,
          provider: acc.provider || (acc.email.includes('gmail') ? 'gmail' : 'outlook'),
          imap_host: acc.imap_host || (acc.provider === 'outlook' ? 'outlook.office365.com' : 'imap.gmail.com'),
          imap_port: acc.imap_port || 993,
          imap_user: acc.imap_user || acc.email,
          imap_pass: acc.imap_pass || acc.password,
          smtp_host: acc.smtp_host || (acc.provider === 'outlook' ? 'smtp.office365.com' : 'smtp.gmail.com'),
          smtp_port: acc.smtp_port || 587,
          smtp_user: acc.smtp_user || acc.email,
          smtp_pass: acc.smtp_pass || acc.password,
          is_active: acc.is_active !== undefined ? (acc.is_active ? 1 : 0) : 1,
          created_at: Date.now(),
        });
      }
    }
  } catch (err) {
    console.error('[Scheduler] Error syncing accounts from file:', err.message);
  }
}

async function triggerWarmupCycle() {
  syncAccountsFromFile();

  const seedAccounts = db.getSeedAccounts();
  if (!seedAccounts || seedAccounts.length === 0) {
    console.log('[Scheduler] No active seed accounts available. Waiting for accounts to be added...');
    return null;
  }

  // Rotate profiles evenly
  const profile = config.profiles[profileIndex % config.profiles.length];
  profileIndex++;

  // Pick a random seed account
  const seedAccount = seedAccounts[Math.floor(Math.random() * seedAccounts.length)];
  const topic = getRandomTopic();

  console.log(`[Scheduler] 🚀 Initiating warmup thread: ${profile.email} -> ${seedAccount.email} (Topic: ${topic.key})`);

  const job = await sendQueue.add('send-warmup-email', {
    profile,
    seedEmail: seedAccount.email,
    topicKey: topic.key,
    turnIndex: 0,
  }, {
    // Same retry policy as every other enqueue site: without attempts the
    // first send of a thread had zero retries and one transient SMTP error
    // silently killed the thread.
    attempts: 3,
    backoff: { type: 'exponential', delay: 10000 },
  });

  return job;
}

function startScheduler() {
  syncAccountsFromFile();
  console.log('[Scheduler] Warmup scheduler started.');

  // Immediate first run check after 5s. The async callback is guarded: an
  // unhandled rejection here crashes Node (no catch, no re-arm).
  initialRunTimer = setTimeout(async () => {
    try {
      const seedAccounts = db.getSeedAccounts();
      if (seedAccounts.length > 0) {
        await triggerWarmupCycle();
      }
    } catch (err) {
      console.error('[Scheduler] Error during initial warmup cycle:', err.message);
    }
  }, 5000);

  // Recurring scheduler loop with randomized intervals
  const scheduleNext = () => {
    const minMs = config.warmup.minIntervalMinutes * 60 * 1000;
    const maxMs = config.warmup.maxIntervalMinutes * 60 * 1000;
    const intervalMs = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;

    schedulerInterval = setTimeout(async () => {
      try {
        await triggerWarmupCycle();
      } catch (err) {
        console.error('[Scheduler] Error during warmup cycle:', err.message);
      } finally {
        // Re-arm even if the cycle failed, so one bad tick can't freeze
        // the loop (finally also covers throws from console.error paths).
        scheduleNext();
      }
    }, intervalMs);
  };

  scheduleNext();
}

function stopScheduler() {
  if (initialRunTimer) {
    clearTimeout(initialRunTimer);
    initialRunTimer = null;
  }
  if (schedulerInterval) {
    clearTimeout(schedulerInterval);
    schedulerInterval = null;
    console.log('[Scheduler] Warmup scheduler stopped.');
  }
}

module.exports = {
  syncAccountsFromFile,
  triggerWarmupCycle,
  startScheduler,
  stopScheduler,
};
