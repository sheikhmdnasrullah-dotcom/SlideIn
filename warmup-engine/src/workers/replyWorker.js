const { Worker } = require('bullmq');
const nodemailer = require('nodemailer');
const crypto = require('crypto');
const config = require('../config');
const db = require('../database');
const { getTopicByKey } = require('../topics');
const { sendQueue, connection } = require('../queues');

async function processReplyJob(job) {
  const { seedEmail, senderEmail, threadId, topicKey, turnIndex, inReplyTo, subject } = job.data;
  console.log(`[ReplyWorker] Sending authentic reply from ${seedEmail} to ${senderEmail} (Turn ${turnIndex})...`);

  const accounts = db.getSeedAccounts();
  const account = accounts.find((a) => a.email.toLowerCase() === seedEmail.toLowerCase());

  if (!account) {
    console.warn(`[ReplyWorker] No account credentials for ${seedEmail}. Skipping reply.`);
    return { status: 'skipped_no_creds' };
  }

  const topic = getTopicByKey(topicKey);
  const currentTurn = topic.turns[turnIndex] || topic.turns[1];

  const smtpHost = account.smtp_host || (account.provider === 'gmail' ? 'smtp.gmail.com' : account.provider === 'outlook' ? 'smtp.office365.com' : 'smtp.gmail.com');
  const smtpPort = account.smtp_port || 587;
  const smtpUser = account.smtp_user || account.imap_user;
  const smtpPass = account.smtp_pass || account.imap_pass;

  const transporter = nodemailer.createTransport({
    host: smtpHost,
    port: smtpPort,
    secure: smtpPort === 465,
    auth: {
      user: smtpUser,
      pass: smtpPass,
    },
    tls: {
      rejectUnauthorized: false,
    },
    connectionTimeout: 15000,
    socketTimeout: 60000,
  });

  const domain = seedEmail.split('@')[1];
  const uniqueId = crypto.randomUUID();
  const messageId = `<${uniqueId}@${domain}>`;
  const replySubject = (subject || '').startsWith('Re:') ? subject : `Re: ${subject || ''}`;

  const mailOptions = {
    from: seedEmail,
    to: senderEmail,
    subject: replySubject,
    text: currentTurn.body,
    messageId: messageId,
    inReplyTo: inReplyTo,
    references: inReplyTo,
    headers: {
      'Auto-Submitted': 'no',
    },
  };

  const sendResult = await transporter.sendMail(mailOptions);
  const now = Date.now();

  db.updateThread(threadId, {
    last_message_id: messageId,
    updated_at: now,
    status: turnIndex >= topic.turns.length - 1 ? 'completed' : 'active',
  });

  db.logAction({
    thread_id: threadId,
    action: 'replied',
    from_email: seedEmail,
    to_email: senderEmail,
    subject: replySubject,
    message_id: messageId,
    folder_detected: null,
    moved_to_inbox: 0,
    timestamp: now,
    detail: `Replied via ${smtpHost}: ${sendResult.response || 'OK'}`,
  });

  console.log(`[ReplyWorker] ✅ Authentic reply delivered to ${senderEmail} (MsgId: ${messageId})`);

  // If there's a subsequent turn for our profile (turn 2)
  const nextTurnIndex = turnIndex + 1;
  if (nextTurnIndex < topic.turns.length && topic.turns[nextTurnIndex].role === 'sender') {
    const profile = config.profiles.find((p) => p.email.toLowerCase() === senderEmail.toLowerCase()) || {
      name: 'Nasrullah Tanim',
      email: senderEmail,
    };

    const minDelayMs = config.warmup.minIntervalMinutes * 60 * 1000;
    const maxDelayMs = config.warmup.maxIntervalMinutes * 60 * 1000;
    const followUpDelay = Math.floor(Math.random() * (maxDelayMs - minDelayMs + 1)) + minDelayMs;

    console.log(`[ReplyWorker] 🕒 Scheduling follow-up turn ${nextTurnIndex} from ${profile.email} in ${(followUpDelay / 60000).toFixed(1)} minutes...`);

    await sendQueue.add(
      'send-warmup-email',
      {
        profile,
        seedEmail,
        threadId,
        topicKey: topic.key,
        turnIndex: nextTurnIndex,
        inReplyTo: messageId,
        references: inReplyTo ? `${inReplyTo} ${messageId}` : messageId,
        subject: replySubject,
      },
      {
        delay: followUpDelay,
        attempts: 3,
        backoff: { type: 'exponential', delay: 30000 },
      }
    );
  }

  return { threadId, messageId };
}

const replyWorker = new Worker('warmup-reply-queue', processReplyJob, {
  connection,
  concurrency: 2,
});

replyWorker.on('completed', (job, result) => {
  console.log(`[ReplyWorker] Job ${job.id} completed. Thread: ${result?.threadId}`);
});

replyWorker.on('failed', (job, err) => {
  console.error(`[ReplyWorker] Job ${job?.id} failed:`, err.message);
});

module.exports = replyWorker;
