const Database = require('better-sqlite3');
const config = require('./config');

const db = new Database(config.dbPath);
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS warmup_threads (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    from_email TEXT NOT NULL,
    to_email TEXT NOT NULL,
    last_message_id TEXT NOT NULL,
    turn_count INTEGER DEFAULT 1,
    topic_key TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    status TEXT DEFAULT 'active'
  );

  CREATE TABLE IF NOT EXISTS warmup_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT,
    action TEXT NOT NULL,
    from_email TEXT NOT NULL,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    message_id TEXT,
    folder_detected TEXT,
    moved_to_inbox INTEGER DEFAULT 0,
    timestamp INTEGER NOT NULL,
    detail TEXT
  );

  CREATE TABLE IF NOT EXISTS seed_accounts (
    email TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    imap_host TEXT NOT NULL,
    imap_port INTEGER DEFAULT 993,
    imap_user TEXT NOT NULL,
    imap_pass TEXT NOT NULL,
    smtp_host TEXT,
    smtp_port INTEGER DEFAULT 587,
    smtp_user TEXT,
    smtp_pass TEXT,
    is_active INTEGER DEFAULT 1,
    created_at INTEGER NOT NULL
  );
`);

module.exports = {
  db,
  createThread(thread) {
    const stmt = db.prepare(`
      INSERT INTO warmup_threads (id, subject, from_email, to_email, last_message_id, turn_count, topic_key, created_at, updated_at, status)
      VALUES (@id, @subject, @from_email, @to_email, @last_message_id, @turn_count, @topic_key, @created_at, @updated_at, @status)
    `);
    return stmt.run(thread);
  },
  getThread(id) {
    return db.prepare('SELECT * FROM warmup_threads WHERE id = ?').get(id);
  },
  getThreadByMessageId(messageId) {
    return db.prepare('SELECT * FROM warmup_threads WHERE last_message_id = ?').get(messageId);
  },
  updateThread(id, updates) {
    const stmt = db.prepare(`
      UPDATE warmup_threads 
      SET last_message_id = @last_message_id, turn_count = turn_count + 1, updated_at = @updated_at, status = @status
      WHERE id = @id
    `);
    return stmt.run({ id, ...updates });
  },
  logAction(log) {
    const stmt = db.prepare(`
      INSERT INTO warmup_logs (thread_id, action, from_email, to_email, subject, message_id, folder_detected, moved_to_inbox, timestamp, detail)
      VALUES (@thread_id, @action, @from_email, @to_email, @subject, @message_id, @folder_detected, @moved_to_inbox, @timestamp, @detail)
    `);
    return stmt.run(log);
  },
  getSeedAccounts() {
    return db.prepare('SELECT * FROM seed_accounts WHERE is_active = 1').all();
  },
  addSeedAccount(account) {
    const stmt = db.prepare(`
      INSERT OR REPLACE INTO seed_accounts (email, provider, imap_host, imap_port, imap_user, imap_pass, smtp_host, smtp_port, smtp_user, smtp_pass, is_active, created_at)
      VALUES (@email, @provider, @imap_host, @imap_port, @imap_user, @imap_pass, @smtp_host, @smtp_port, @smtp_user, @smtp_pass, @is_active, @created_at)
    `);
    return stmt.run(account);
  },
  getStats() {
    const totalSent = db.prepare("SELECT COUNT(*) as count FROM warmup_logs WHERE action = 'sent'").get().count;
    const totalReplies = db.prepare("SELECT COUNT(*) as count FROM warmup_logs WHERE action = 'replied'").get().count;
    const totalRescued = db.prepare("SELECT COUNT(*) as count FROM warmup_logs WHERE moved_to_inbox = 1").get().count;
    const activeThreads = db.prepare("SELECT COUNT(*) as count FROM warmup_threads WHERE status = 'active'").get().count;
    const accountsCount = db.prepare("SELECT COUNT(*) as count FROM seed_accounts WHERE is_active = 1").get().count;
    return { totalSent, totalReplies, totalRescued, activeThreads, accountsCount };
  }
};
