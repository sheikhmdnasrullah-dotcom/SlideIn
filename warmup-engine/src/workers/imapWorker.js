const { Worker } = require('bullmq');
const { ImapFlow } = require('imapflow');
const config = require('../config');
const db = require('../database');
const { replyQueue, imapQueue, connection } = require('../queues');

async function checkSeedMailbox(job) {
  const { seedEmail, targetMessageId, threadId, senderEmail, topicKey, turnIndex } = job.data;
  console.log(`[ImapWorker] Checking mailbox for ${seedEmail} (Sender: ${senderEmail}, MsgId: ${targetMessageId})...`);

  const accounts = db.getSeedAccounts();
  const account = accounts.find((a) => a.email.toLowerCase() === seedEmail.toLowerCase());

  if (!account) {
    console.warn(`[ImapWorker] No seed account credentials found for ${seedEmail}. Skipping IMAP inspection.`);
    return { status: 'skipped_no_creds' };
  }

  const client = new ImapFlow({
    host: account.imap_host,
    port: account.imap_port || 993,
    secure: account.imap_port !== 143,
    auth: {
      user: account.imap_user,
      pass: account.imap_pass,
    },
    logger: false,
    emitLogs: false,
    // Defaults are 16s greeting / 300s socket — a single hung connection
    // stalls the whole worker (concurrency 2) for minutes.
    greetingTimeout: 10000,
    socketTimeout: 60000,
  });

  let folderDetected = null;
  let movedToInbox = 0;
  let messageFound = false;
  let detectedMessageId = targetMessageId;
  let detectedSubject = '';

  try {
    await client.connect();

    const mailboxes = await client.list();
    const spamBox = mailboxes.find((b) => 
      b.specialUse === '\\Junk' || 
      /spam|junk/i.test(b.name) || 
      /spam|junk/i.test(b.path)
    );
    const inboxBox = mailboxes.find((b) => b.path.toUpperCase() === 'INBOX' || b.name.toUpperCase() === 'INBOX') || { path: 'INBOX' };

    // 1. Check Spam / Junk first
    if (spamBox) {
      const spamLock = await client.getMailboxLock(spamBox.path);
      try {
        const spamUids = await client.search({ all: true }, { uid: true });
        if (spamUids && spamUids.length > 0) {
          const recentSpamUids = spamUids.slice(-20); // check last 20 spam messages
          let matchedUid = null;

          for await (const msg of client.fetch(recentSpamUids.join(','), { uid: true, envelope: true })) {
            const envMsgId = msg.envelope?.messageId ? `<${msg.envelope.messageId.replace(/[<>]/g, '')}>` : '';
            const targetClean = targetMessageId ? `<${targetMessageId.replace(/[<>]/g, '')}>` : '';

            if (envMsgId === targetClean || (!targetMessageId && msg.envelope?.from?.[0]?.address?.toLowerCase() === senderEmail.toLowerCase())) {
              matchedUid = msg.uid;
              detectedSubject = msg.envelope?.subject || '';
              detectedMessageId = envMsgId || targetMessageId;
              break;
            }
          }

          if (matchedUid) {
            messageFound = true;
            folderDetected = spamBox.path;
            console.log(`[ImapWorker] ⚠️ Message found in SPAM (${spamBox.path}) UID: ${matchedUid}! Rescuing to INBOX...`);

            try {
              await client.messageFlagsAdd(`${matchedUid}`, ['\\Seen', '\\Flagged'], { uid: true });
              await client.messageMove(`${matchedUid}`, inboxBox.path, { uid: true });
              movedToInbox = 1;
              console.log(`[ImapWorker] ✅ Rescued message UID ${matchedUid} from SPAM to INBOX.`);
            } catch (rescueErr) {
              console.error(`[ImapWorker] Error moving message to inbox:`, rescueErr.message);
            }
          }
        }
      } finally {
        spamLock.release();
      }
    }

    // 2. Check INBOX if not found in Spam
    if (!messageFound) {
      const inboxLock = await client.getMailboxLock(inboxBox.path);
      try {
        // Search messages from the last 2 hours
        const sinceDate = new Date(Date.now() - 2 * 60 * 60 * 1000);
        const inboxUids = await client.search({ since: sinceDate }, { uid: true });
        if (inboxUids && inboxUids.length > 0) {
          const recentInboxUids = inboxUids.slice(-30);
          let matchedUid = null;

          for await (const msg of client.fetch(recentInboxUids.join(','), { uid: true, envelope: true })) {
            const envMsgId = msg.envelope?.messageId ? `<${msg.envelope.messageId.replace(/[<>]/g, '')}>` : '';
            const targetClean = targetMessageId ? `<${targetMessageId.replace(/[<>]/g, '')}>` : '';

            if (envMsgId === targetClean || (!targetMessageId && msg.envelope?.from?.[0]?.address?.toLowerCase() === senderEmail.toLowerCase())) {
              matchedUid = msg.uid;
              detectedSubject = msg.envelope?.subject || '';
              detectedMessageId = envMsgId || targetMessageId;
              break;
            }
          }

          if (matchedUid) {
            messageFound = true;
            folderDetected = 'INBOX';
            console.log(`[ImapWorker] 🎉 Message found in INBOX UID: ${matchedUid}! Marking as Seen & Starred.`);

            try {
              await client.messageFlagsAdd(`${matchedUid}`, ['\\Seen', '\\Flagged'], { uid: true });
            } catch (flagErr) {
              console.error(`[ImapWorker] Error setting flags:`, flagErr.message);
            }
          }
        }
      } finally {
        inboxLock.release();
      }
    }

    await client.logout();
  } catch (err) {
    console.error(`[ImapWorker] IMAP connection error for ${seedEmail}:`, err.message);
    try { await client.logout(); } catch (_) {}
    throw err;
  }

  // Log the detection result
  const now = Date.now();
  db.logAction({
    thread_id: threadId,
    action: messageFound ? 'detected' : 'check_miss',
    from_email: senderEmail,
    to_email: seedEmail,
    subject: detectedSubject || `Thread ${threadId}`,
    message_id: detectedMessageId,
    folder_detected: folderDetected || 'NOT_FOUND',
    moved_to_inbox: movedToInbox,
    timestamp: now,
    detail: messageFound ? `Detected in ${folderDetected} (rescued: ${movedToInbox})` : 'Message not yet indexed in mailbox',
  });

  // A miss must NOT end the thread. The job "succeeded", so BullMQ's
  // attempts never fire and nothing re-checks — threads died silently this
  // way (live DB showed check_miss > 0, replied = 0). Re-enqueue a delayed
  // re-check with a bounded budget, then abandon loudly.
  if (!messageFound) {
    const MAX_CHECKS = 5;
    const attempt = (job.data.checkAttempt || 0) + 1;
    if (attempt < MAX_CHECKS) {
      const recheckDelay = (Math.floor(Math.random() * 11) + 5) * 60 * 1000; // 5–15 min
      console.log(
        `[ImapWorker] ⏳ Message not found for thread ${threadId} ` +
        `(check ${attempt}/${MAX_CHECKS}); re-checking in ${(recheckDelay / 60000).toFixed(0)} min...`
      );
      await imapQueue.add(
        'check-seed-inbox',
        { ...job.data, checkAttempt: attempt },
        {
          delay: recheckDelay,
          attempts: 3,
          backoff: { type: 'exponential', delay: 30000 },
        }
      );
    } else {
      db.logAction({
        thread_id: threadId,
        action: 'abandoned',
        from_email: senderEmail,
        to_email: seedEmail,
        subject: detectedSubject || `Thread ${threadId}`,
        message_id: detectedMessageId,
        folder_detected: 'NOT_FOUND',
        moved_to_inbox: 0,
        timestamp: now,
        detail: `Message never appeared after ${MAX_CHECKS} checks; thread abandoned`,
      });
      console.error(
        `[ImapWorker] ❌ Abandoning thread ${threadId}: message from ${senderEmail} ` +
        `never appeared in ${seedEmail}'s mailbox after ${MAX_CHECKS} checks.`
      );
    }
  }

  // If message found, schedule authentic reply
  const nextTurnIndex = (turnIndex || 0) + 1;
  if (messageFound && nextTurnIndex <= 3) {
    const minDelayMs = config.warmup.minReplyDelayMinutes * 60 * 1000;
    const maxDelayMs = config.warmup.maxReplyDelayMinutes * 60 * 1000;
    const replyDelay = Math.floor(Math.random() * (maxDelayMs - minDelayMs + 1)) + minDelayMs;

    console.log(`[ImapWorker] 🕒 Scheduling authentic reply from ${seedEmail} in ${(replyDelay / 60000).toFixed(1)} minutes (Turn ${nextTurnIndex})...`);

    await replyQueue.add(
      'send-seed-reply',
      {
        seedEmail,
        senderEmail,
        threadId,
        topicKey,
        turnIndex: nextTurnIndex,
        inReplyTo: detectedMessageId,
        subject: detectedSubject,
      },
      {
        delay: replyDelay,
        attempts: 3,
        backoff: { type: 'exponential', delay: 30000 },
      }
    );
  }

  return { messageFound, folderDetected, movedToInbox };
}

const imapWorker = new Worker('imap-check-queue', checkSeedMailbox, {
  connection,
  concurrency: 2,
});

imapWorker.on('completed', (job, result) => {
  console.log(`[ImapWorker] Job ${job.id} completed. Result:`, result);
});

imapWorker.on('failed', (job, err) => {
  console.error(`[ImapWorker] Job ${job?.id} failed:`, err.message);
});

imapWorker.on('error', (err) => {
  // Without a listener, blocking-connection Redis errors are swallowed
  // silently (BullMQ only re-emits when someone is listening).
  console.error('[ImapWorker] Worker error:', err.message);
});

module.exports = imapWorker;
