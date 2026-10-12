const { Worker } = require('bullmq');
const nodemailer = require('nodemailer');
const crypto = require('crypto');
const config = require('../config');
const db = require('../database');
const { getTopicByKey, getRandomTopic } = require('../topics');
const { imapQueue, connection } = require('../queues');

const transporter = nodemailer.createTransport({
  host: config.kumo.host,
  port: config.kumo.port,
  secure: false,
  auth: {
    user: config.kumo.user,
    pass: config.kumo.password,
  },
  tls: {
    rejectUnauthorized: false,
  },
  // Nodemailer defaults (120s connect / 600s socket) let two hung
  // connections stall this worker for minutes.
  connectionTimeout: 15000,
  socketTimeout: 60000,
});

async function processSendJob(job) {
  const { profile, seedEmail, threadId, topicKey, turnIndex = 0, inReplyTo, references } = job.data;
  console.log(`[SenderWorker] Processing send job to ${seedEmail} from ${profile.email} (turn ${turnIndex})...`);

  const topic = topicKey ? getTopicByKey(topicKey) : getRandomTopic();
  const currentTurn = topic.turns[turnIndex] || topic.turns[0];

  const domain = profile.email.split('@')[1];
  const uniqueId = crypto.randomUUID();
  const messageId = `<${uniqueId}@${domain}>`;
  const subject = turnIndex === 0 ? topic.subject : (job.data.subject?.startsWith('Re:') ? job.data.subject : `Re: ${topic.subject}`);

  const mailOptions = {
    from: `"${profile.name}" <${profile.email}>`,
    to: seedEmail,
    subject: subject,
    text: currentTurn.body,
    messageId: messageId,
    headers: {
      'Auto-Submitted': 'no',
      'X-Mailer': 'Apple Mail (2.3654.120.0.1)',
    },
  };

  if (inReplyTo) {
    mailOptions.inReplyTo = inReplyTo;
    mailOptions.references = references || inReplyTo;
  }

  const sendResult = await transporter.sendMail(mailOptions);
  const now = Date.now();
  const activeThreadId = threadId || `th_${uniqueId.substring(0, 12)}`;

  if (turnIndex === 0) {
    db.createThread({
      id: activeThreadId,
      subject: topic.subject,
      from_email: profile.email,
      to_email: seedEmail,
      last_message_id: messageId,
      turn_count: 1,
      topic_key: topic.key,
      created_at: now,
      updated_at: now,
      status: 'active',
    });
  } else {
    db.updateThread(activeThreadId, {
      last_message_id: messageId,
      updated_at: now,
      status: 'active',
    });
  }

  db.logAction({
    thread_id: activeThreadId,
    action: 'sent',
    from_email: profile.email,
    to_email: seedEmail,
    subject: subject,
    message_id: messageId,
    folder_detected: null,
    moved_to_inbox: 0,
    timestamp: now,
    detail: `Sent via KumoMTA: ${sendResult.response || 'OK'}`,
  });

  console.log(`[SenderWorker] ✅ Email sent to ${seedEmail} (Thread: ${activeThreadId}, MsgId: ${messageId})`);

  // Enqueue IMAP verification on the seed account after 20 seconds
  await imapQueue.add(
    'check-seed-inbox',
    {
      seedEmail,
      targetMessageId: messageId,
      threadId: activeThreadId,
      senderEmail: profile.email,
      topicKey: topic.key,
      turnIndex: turnIndex,
    },
    {
      delay: 20000, // 20s delay
      attempts: 3,
      backoff: { type: 'exponential', delay: 10000 },
    }
  );

  return { threadId: activeThreadId, messageId };
}

const senderWorker = new Worker('warmup-send-queue', processSendJob, {
  connection,
  concurrency: 2,
});

senderWorker.on('completed', (job, result) => {
  console.log(`[SenderWorker] Job ${job.id} completed. Thread: ${result?.threadId}`);
});

senderWorker.on('failed', (job, err) => {
  console.error(`[SenderWorker] Job ${job?.id} failed:`, err.message);
});

senderWorker.on('error', (err) => {
  console.error('[SenderWorker] Worker error:', err.message);
});

module.exports = senderWorker;
