const Database = require('better-sqlite3');
const config = require('./config');

const db = new Database(config.dbPath || '/opt/optimization-engine/optimization.db');
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS email_queue (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    profile TEXT NOT NULL,
    subject TEXT,
    content_score REAL,
    status TEXT DEFAULT 'pending',
    created_at REAL NOT NULL,
    sent_at REAL
  );
  CREATE TABLE IF NOT EXISTS placement_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    inbox_pct REAL,
    promotions_pct REAL,
    spam_pct REAL,
    overall_score REAL,
    timestamp REAL NOT NULL
  );
`);

module.exports = db;
