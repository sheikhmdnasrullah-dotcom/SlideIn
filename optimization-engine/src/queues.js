const { Queue } = require('bullmq');
const Redis = require('ioredis');
const config = require('./config');

const connection = new Redis(config.redis);
const sendQueue = new Queue('optimized-send-queue', { connection });
const placementQueue = new Queue('placement-check-queue', { connection });

module.exports = { connection, sendQueue, placementQueue };
