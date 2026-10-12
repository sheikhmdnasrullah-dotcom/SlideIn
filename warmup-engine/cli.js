#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const db = require('./src/database');
const config = require('./src/config');
const { triggerWarmupCycle, syncAccountsFromFile } = require('./src/scheduler');

const args = process.argv.slice(2);
const command = args[0];

function printHelp() {
  console.log(`
Email Warmup Engine CLI
-----------------------
Usage:
  node cli.js add-account --email <email> --pass <pass> [--provider <gmail|outlook>]
  node cli.js list-accounts
  node cli.js stats
  node cli.js logs [limit]
  node cli.js threads
  node cli.js trigger
  `);
}

function getParam(name) {
  const idx = args.indexOf(name);
  if (idx !== -1 && idx + 1 < args.length) {
    return args[idx + 1];
  }
  return null;
}

async function main() {
  if (!command || command === 'help' || command === '--help' || command === '-h') {
    printHelp();
    process.exit(0);
  }

  if (command === 'add-account') {
    const email = getParam('--email');
    const pass = getParam('--pass') || getParam('--password');
    const provider = getParam('--provider') || (email && email.includes('gmail') ? 'gmail' : 'outlook');

    if (!email || !pass) {
      console.error('Error: --email and --pass are required.');
      process.exit(1);
    }

    const imapHost = provider === 'outlook' ? 'outlook.office365.com' : 'imap.gmail.com';
    const smtpHost = provider === 'outlook' ? 'smtp.office365.com' : 'smtp.gmail.com';

    db.addSeedAccount({
      email,
      provider,
      imap_host: imapHost,
      imap_port: 993,
      imap_user: email,
      imap_pass: pass,
      smtp_host: smtpHost,
      smtp_port: 587,
      smtp_user: email,
      smtp_pass: pass,
      is_active: 1,
      created_at: Date.now(),
    });

    console.log(`✅ Seed account ${email} added/updated successfully!`);
    process.exit(0);
  }

  if (command === 'list-accounts') {
    const accounts = db.getSeedAccounts();
    console.log(`\nRegistered Active Seed Accounts (${accounts.length}):`);
    console.table(
      accounts.map((a) => ({
        Email: a.email,
        Provider: a.provider,
        IMAP: `${a.imap_host}:${a.imap_port}`,
        SMTP: `${a.smtp_host}:${a.smtp_port}`,
        Active: a.is_active ? 'Yes' : 'No',
      }))
    );
    process.exit(0);
  }

  if (command === 'stats') {
    const stats = db.getStats();
    console.log('\n📊 WARMUP ENGINE STATISTICS');
    console.log('============================');
    console.log(`Active Seed Accounts:   ${stats.accountsCount}`);
    console.log(`Active Threads:         ${stats.activeThreads}`);
    console.log(`Total Outbound Sent:    ${stats.totalSent}`);
    console.log(`Total Replies Received: ${stats.totalReplies}`);
    console.log(`Spam Rescued to Inbox:  ${stats.totalRescued}`);
    console.log('============================\n');
    process.exit(0);
  }

  if (command === 'logs') {
    const limit = parseInt(args[1] || '20', 10);
    const logs = db.db.prepare('SELECT * FROM warmup_logs ORDER BY timestamp DESC LIMIT ?').all(limit);
    console.log(`\nRecent Warmup Activity Logs (Last ${logs.length}):`);
    console.table(
      logs.map((l) => ({
        ID: l.id,
        Action: l.action,
        From: l.from_email,
        To: l.to_email,
        Folder: l.folder_detected || '-',
        Rescued: l.moved_to_inbox ? 'YES' : 'NO',
        Time: new Date(l.timestamp).toLocaleTimeString(),
      }))
    );
    process.exit(0);
  }

  if (command === 'threads') {
    const threads = db.db.prepare('SELECT * FROM warmup_threads ORDER BY updated_at DESC LIMIT 20').all();
    console.log(`\nActive Warmup Threads (${threads.length}):`);
    console.table(
      threads.map((t) => ({
        ID: t.id,
        Subject: t.subject,
        From: t.from_email,
        To: t.to_email,
        Turns: t.turn_count,
        Status: t.status,
        Updated: new Date(t.updated_at).toLocaleTimeString(),
      }))
    );
    process.exit(0);
  }

  if (command === 'trigger') {
    console.log('Manually triggering a warmup cycle...');
    await triggerWarmupCycle();
    console.log('Warmup cycle job dispatched to queue!');
    process.exit(0);
  }

  console.error(`Unknown command: ${command}`);
  printHelp();
  process.exit(1);
}

main().catch((err) => {
  console.error('Fatal CLI error:', err);
  process.exit(1);
});
