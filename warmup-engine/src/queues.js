const { Queue } = require('bullmq');
const Redis = require('ioredis');
const config = require('./config');

const connection = new Redis(config.redis);

connection.on('error', (err) => {
  console.error('[Redis Error]', err.message);
});

const sendQueue = new Queue('warmup-send-queue', { connection });
const replyQueue = new Queue('warmup-reply-queue', { connection });
const imapQueue = new Queue('imap-check-queue', { connection });

module.exports = {
  connection,
  sendQueue,
  replyQueue,
  imapQueue,
};
