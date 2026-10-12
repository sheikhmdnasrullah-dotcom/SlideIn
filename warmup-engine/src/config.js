const fs = require('fs');
const path = require('path');

const configPath = path.resolve(__dirname, '../../deliverability/config.json');
let baseConfig = {};

if (fs.existsSync(configPath)) {
  try {
    baseConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (err) {
    console.error('Error reading deliverability/config.json:', err.message);
  }
}

const config = {
  redis: {
    host: process.env.REDIS_HOST || '127.0.0.1',
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
    maxRetriesPerRequest: null,
  },
  kumo: {
    host: baseConfig.kumo?.host || '127.0.0.1',
    port: parseInt(baseConfig.kumo?.port || '2587', 10),
    user: baseConfig.kumo?.user || 'admin',
    password: baseConfig.kumo?.password || process.env.KUMO_AUTH_PASS || 'local-dev-password',
  },
  profiles: [
    { name: 'Nasrullah Tanim', email: 'hello@nasrullahtanim.me' },
    { name: 'Nasrullah Tanim', email: 'talk@nasrullahtanim.me' },
    { name: 'Nasrullah Tanim', email: 'connect@nasrullahtanim.me' },
    { name: 'Nasrullah Tanim', email: 'hello@tanim.social' },
    { name: 'Nasrullah Tanim', email: 'talk@tanim.social' },
  ],
  warmup: {
    minIntervalMinutes: 5,
    maxIntervalMinutes: 15,
    minReplyDelayMinutes: 5,
    maxReplyDelayMinutes: 30,
    dailyLimitPerProfile: 20,
    rampIncrementPerDay: 2,
    maxDailyLimit: 100,
  },
  dbPath: path.resolve(__dirname, '../warmup.db'),
  accountsFile: path.resolve(__dirname, '../accounts.json'),
};

module.exports = config;
